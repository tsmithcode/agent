from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any, Callable, Optional

from .env import get_openai_api_key, load_project_dotenv
from .executor import Executor, PolicyViolation
from .llm import LLM
from .memory import LongTermMemory
from .paths import Paths
from .policy import Policy
from .router import decide_route
from .runtime_common import finish_event, limits_summary, memory_context, print_run_summary, save_memory
from .tool_registry import DeterministicContext, execute_tool
from cg_utils import cap_chars, truncate_for_display


def _run_with_spinner(console, message: str, fn):
    done = threading.Event()
    result: dict[str, Any] = {}
    error: dict[str, Exception] = {}

    def _worker() -> None:
        try:
            result["value"] = fn()
        except Exception as e:
            error["value"] = e
        finally:
            done.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    with console.status(f"[bold #a78bfa]{message}[/]", spinner="dots"):
        while not done.wait(0.1):
            pass
    if "value" in error:
        raise error["value"]
    return result.get("value")


def _step_preview_text(step: Any) -> str:
    step_type = getattr(step, "type", "") or "unknown"
    if step_type == "write":
        path = getattr(step, "path", None) or "(missing path)"
        return f"write: {path}"
    if step_type == "cmd":
        return f"cmd: {getattr(step, 'value', '')}"
    return f"note: {getattr(step, 'value', '')}"


def _actionable_steps(reply_plan: list[Any]) -> list[Any]:
    return [s for s in reply_plan if getattr(s, "type", None) in {"cmd", "write"}]


def _has_confirm_token(prompt: str) -> bool:
    p = (prompt or "").lower()
    return bool(re.search(r"\bconfirm\s*[:=]\s*yes\b", p))


def _requires_apply_confirmation(prompt: str, actionable_steps: list[Any]) -> bool:
    p = (prompt or "").lower()
    apply_intent = any(
        k in p
        for k in (
            "apply",
            "rename",
            "rewrite",
            "sanitize",
            "normalize",
            "batch",
            "delete",
            "move",
            "modify",
            "update",
        )
    )
    has_risky_action = any(getattr(s, "type", "") in {"cmd", "write"} for s in actionable_steps)
    return apply_intent and has_risky_action


def _execute_step(
    executor: Executor,
    step: Any,
    *,
    max_runtime_seconds: int,
    max_output_chars: int,
    stdout_line_cap: int,
    stderr_line_cap: int,
    full_output: bool,
    print_section,
    print_status_line,
    console,
) -> bool:
    if step.type == "write":
        if not step.path:
            raise PolicyViolation("write step missing path")
        out_path = executor.write_file(step.path, step.value)
        print_section(console, title="Write", body=f"WROTE {out_path}\nRun complete executed=write")
        return True

    if step.type == "cmd":
        res = executor.run(step.value, timeout_s=max_runtime_seconds)
        print_section(console, title="Command", body=f"CMD {res.command}\nstatus={'OK' if res.ok else 'FAIL'}")
        show_output = full_output or (not res.ok)
        if show_output and res.stdout.strip():
            out, truncated = truncate_for_display(
                res.stdout,
                max_chars=max_output_chars,
                max_lines=stdout_line_cap,
                full_output=full_output,
            )
            print_section(console, title="stdout", body=out)
            if truncated:
                print_status_line(console, "stdout truncated. Use --full to view full output.", tone="warning")
        if show_output and res.stderr.strip():
            err, truncated = truncate_for_display(
                res.stderr,
                max_chars=max_output_chars,
                max_lines=stderr_line_cap,
                full_output=full_output,
            )
            print_section(console, title="stderr", body=err)
            if truncated:
                print_status_line(console, "stderr truncated. Use --full to view full output.", tone="warning")
        print_section(console, title="Command Result", body=f"Run complete executed=cmd ok={res.ok} exit_code={res.exit_code}")
        return res.ok

    return True


def run_once(
    *,
    prompt: str,
    full_output: bool,
    console,
    print_session_boundary,
    print_kv_table,
    print_route_decision,
    print_section,
    print_status_line,
    print_answer_path,
    print_cli_notice,
    print_runtime_error,
    session_id: str,
    workspace_once,
    outputs_once,
    structure_once,
    extract_depth,
    snapshot_runner: Optional[Callable[..., None]] = None,
    llm_cls=LLM,
    memory_cls=LongTermMemory,
) -> None:
    started = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command="run", run_id=run_id, phase="start")
    load_project_dotenv()

    paths = Paths.resolve()
    policy_path = (paths.home / "agent" / "config" / "policy.json").resolve()
    policy = Policy.load(str(policy_path))

    max_runtime_seconds = policy.max_runtime_seconds()
    max_output_chars = policy.max_output_chars()
    max_steps_per_plan = policy.max_steps_per_plan()
    max_response_chars = policy.max_answer_chars()
    max_summary_lines = policy.max_answer_lines()
    max_completion_tokens = max(64, policy.max_completion_tokens())
    stdout_line_cap = max(1, policy.max_stdout_lines())
    stderr_line_cap = max(1, policy.max_stderr_lines())

    api_key = get_openai_api_key()
    route_mode = "llm"
    handler_id = ""
    llm_used = False
    actionable_steps = 0
    executed_steps = 0

    def _finish(outcome: str, *, error_type: str = "", error_message: str = "") -> None:
        finish_event(
            paths=paths,
            started=started,
            session_id=session_id,
            command="run",
            route_mode=route_mode,
            handler_id=handler_id,
            outcome=outcome,
            llm_used=llm_used,
            actionable_steps=actionable_steps,
            executed_steps=executed_steps,
            error_type=error_type,
            error_message=error_message,
        )
        print_session_boundary(console, command="run", run_id=run_id, phase="end")

    memory = memory_cls(chroma_dir=str(paths.chroma_dir), collection_name="cg_openclaw_memory", openai_api_key=api_key)

    decision = decide_route(prompt, policy)
    if decision.mode == "deterministic" and decision.handler_id:
        route_mode = "deterministic"
        handler_id = decision.handler_id
        print_route_decision(console, decision)
        ctx = DeterministicContext(
            workspace_once=workspace_once,
            outputs_once=outputs_once,
            structure_once=structure_once,
            extract_depth=extract_depth,
            snapshot_runner=snapshot_runner,
        )
        ok, detail = execute_tool(decision.handler_id, prompt, ctx)
        print_answer_path(console, "command", f"deterministic handler executed: {decision.handler_id}")
        save_memory(memory, user_text=prompt, assistant_text=f"deterministic handler={decision.handler_id} detail={detail}", mode="run", kind_override="task_result", extra_metadata={"route_mode": "deterministic", "handler_id": decision.handler_id})
        if not ok:
            print_cli_notice(console, title="Deterministic Handler Failed", level="error", message=detail, help_line="Rephrase the request or fall back to an LLM-planned run.")
            print_run_summary(print_section, console, route_mode=route_mode, decision_reason=decision.reason, outcome="handler_failed", llm_used=False, handler_id=handler_id)
            _finish("handler_failed", error_type="deterministic_handler", error_message=detail)
            raise SystemExit(1)
        print_run_summary(print_section, console, route_mode=route_mode, decision_reason=decision.reason, outcome="success", llm_used=False, handler_id=handler_id)
        _finish("success")
        return

    if not api_key:
        print_cli_notice(console, title="LLM Required", level="warning", message="No deterministic route matched and OPENAI_API_KEY is not set.", help_line="Set OPENAI_API_KEY or use an obvious deterministic request like 'show workspace files'.")
        print_run_summary(print_section, console, route_mode=route_mode, decision_reason=decision.reason, outcome="llm_required", llm_used=False)
        _finish("llm_required")
        return

    retrieved_text, retrieved_count = memory_context(memory, prompt, policy)
    print_kv_table(console, title="CAD Guardian Agent", rows=[("Prompt", prompt), ("Memory", f"retrieved={retrieved_count} | sent_chars={len(retrieved_text)}"), ("Runtime", limits_summary(policy))])
    print_route_decision(console, decision)

    llm = llm_cls(api_key=api_key)
    try:
        llm_used = True
        reply = llm.ask(prompt, retrieved_text, model=policy.llm_model(), max_completion_tokens=max_completion_tokens)
    except Exception as e:
        print_runtime_error(console, "LLM Error", e, "Check OPENAI_API_KEY, internet/DNS, and policy allow_domains settings.")
        print_run_summary(print_section, console, route_mode=route_mode, decision_reason=decision.reason, outcome="llm_error", llm_used=True)
        _finish("llm_error", error_type=type(e).__name__, error_message=str(e))
        return

    if len(reply.plan) > max_steps_per_plan:
        reply.plan = reply.plan[:max_steps_per_plan]
        print_status_line(console, f"Plan truncated to {max_steps_per_plan} steps.", tone="warning")

    step_lines = [f"{i}. {_step_preview_text(s)}" for i, s in enumerate(reply.plan, 1)] or ["(no plan steps returned)"]
    print_section(console, title="Execution Plan", body="\n".join(step_lines))

    answer_display, answer_truncated = truncate_for_display(reply.answer, max_chars=max_response_chars, max_lines=max_summary_lines, full_output=full_output)
    print_section(console, title="Answer", body=answer_display)
    if answer_truncated:
        print_status_line(console, "Answer truncated. Use --full or raise answer limits in policy.", tone="warning")

    save_memory(memory, user_text=prompt, assistant_text=reply.answer, mode="run", extra_metadata={"route_mode": "llm"})

    actionable = _actionable_steps(reply.plan)
    actionable_steps = len(actionable)
    if not actionable:
        print_answer_path(console, "llm", "LLM answer returned notes only; no executable actions in plan")
        save_memory(memory, user_text=prompt, assistant_text="run_outcome=no_actionable executed_steps=0 actionable_steps=0", mode="run", kind_override="task_result", extra_metadata={"route_mode": "llm"})
        print_cli_notice(console, title="No Actionable Steps", level="warning", message="The model returned notes only; nothing can be executed.", help_line='Try a direct action request, e.g. cg run "list files in workspace".', example_line='cg ask "What command should I run to inspect current files?"')
        print_run_summary(print_section, console, route_mode=route_mode, decision_reason=decision.reason, outcome="no_actionable", llm_used=True)
        _finish("no_actionable")
        return

    mode = policy.execution_mode()
    max_actions = max(1, policy.max_actions_per_run())
    selected = actionable[:1] if mode == "single_step" else actionable[:max_actions]

    if _requires_apply_confirmation(prompt, selected) and not _has_confirm_token(prompt):
        print_cli_notice(console, title="Confirmation Required", level="warning", message="Apply-style request detected. No changes were executed.", help_line="Re-run with confirm:yes to apply the proposed actions.", example_line='cg run "rename files to snake_case in workspace confirm:yes"')
        print_answer_path(console, "llm", "LLM generated an apply plan; execution blocked until explicit confirmation")
        save_memory(memory, user_text=prompt, assistant_text="run_outcome=confirmation_required executed_steps=0", mode="run", kind_override="task_result", extra_metadata={"route_mode": "llm"})
        print_run_summary(print_section, console, route_mode=route_mode, decision_reason=decision.reason, outcome="confirmation_required", llm_used=True)
        _finish("confirmation_required")
        return

    if mode == "continue_until_done" and len(actionable) > len(selected):
        print_status_line(console, f"Execution capped actionable_steps={len(actionable)} -> executing={len(selected)} (max_actions_per_run={max_actions})", tone="warning")

    executor = Executor(policy=policy, workspace=paths.workspace)
    outcome = "completed"
    outcome_detail = ""
    for i, step in enumerate(selected, 1):
        print_status_line(console, f"Executing step {i}/{len(selected)} {_step_preview_text(step)}", tone="info")
        try:
            executed_steps += 1
            ok = _execute_step(executor, step, max_runtime_seconds=max_runtime_seconds, max_output_chars=max_output_chars, stdout_line_cap=stdout_line_cap, stderr_line_cap=stderr_line_cap, full_output=full_output, print_section=print_section, print_status_line=print_status_line, console=console)
            if not ok:
                outcome = "command_failed"
                print_cli_notice(console, title="Execution Stopped", level="warning", message="A command failed; stopping remaining steps.", help_line="Re-run with --full to inspect stdout/stderr, then retry.")
                break
        except PolicyViolation as e:
            outcome = "policy_violation"
            rule = getattr(e, "rule", "") or "unknown_policy_rule"
            outcome_detail = f"{str(e)} (rule={rule})"
            print_cli_notice(console, title="Policy Violation", level="error", message=str(e), help_line=f"Violated policy: {rule} (config/policy.json).", example_line="cg doctor --verbose")
            break
        except Exception as e:
            outcome = "execution_error"
            outcome_detail = str(e)
            print_runtime_error(console, "Execution Error", e, "Re-run with --full and inspect command/output details.")
            break

    if mode == "single_step" and len(actionable) > 1:
        print_status_line(console, "Stopped after 1 actionable step (policy: execution_mode=single_step).", tone="info")

    print_answer_path(console, "both", f"LLM planned actions; executor ran {executed_steps} step(s) under policy")
    task_result = f"run_outcome={outcome} executed_steps={executed_steps}/{len(selected)} actionable_steps={len(actionable)} execution_mode={mode}"
    if outcome_detail:
        task_result += f" detail={cap_chars(outcome_detail, 300)}"
    save_memory(memory, user_text=prompt, assistant_text=task_result, mode="run", kind_override="task_result", extra_metadata={"route_mode": "llm"})
    print_run_summary(print_section, console, route_mode=route_mode, decision_reason=decision.reason, outcome="success" if outcome == "completed" else outcome, llm_used=True, handler_id=handler_id)
    _finish("success" if outcome == "completed" else outcome, error_message=outcome_detail)
