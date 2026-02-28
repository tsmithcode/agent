from __future__ import annotations

import re
import time
import uuid

from ..data.env import get_openai_api_key, load_project_dotenv
from ..data.memory import LongTermMemory
from ..data.paths import Paths
from ..safety.executor import Executor, PolicyViolation
from ..safety.policy import Policy
from .common import finish_event, limits_summary, memory_context, save_memory
from .llm import LLM
from .policy_insight import policy_violation_insight
from cg_utils import cap_chars, truncate_for_display


def _step_preview(step) -> str:
    step_type = str(getattr(step, "type", "") or "note")
    if step_type == "write":
        return f"write: {getattr(step, 'path', '') or '(missing path)'}"
    if step_type == "cmd":
        return f"cmd: {getattr(step, 'value', '')}"
    return f"note: {getattr(step, 'value', '')}"


def _requires_confirmation(prompt: str, actionable_steps: list) -> bool:
    text = (prompt or "").lower()
    apply_words = {
        "apply",
        "delete",
        "rename",
        "rewrite",
        "sanitize",
        "normalize",
        "move",
        "modify",
        "update",
    }
    wants_apply = any(w in text for w in apply_words)
    has_action = any(str(getattr(s, "type", "")) in {"cmd", "write"} for s in actionable_steps)
    return wants_apply and has_action and not re.search(r"\bconfirm\s*[:=]\s*yes\b", text)


def _execute_step(
    executor: Executor,
    step,
    *,
    timeout_s: int,
    full_output: bool,
    max_output_chars: int,
    stdout_line_cap: int,
    stderr_line_cap: int,
    print_section,
    print_status_line,
    console,
) -> bool:
    if step.type == "write":
        if not step.path:
            raise PolicyViolation("write step missing path", rule="allowed_write_roots")
        out = executor.write_file(step.path, step.value)
        print_section(console, title="Write", body=f"WROTE {out}")
        return True

    if step.type == "cmd":
        res = executor.run(step.value, timeout_s=timeout_s)
        print_section(console, title="Command", body=f"CMD {res.command}\nstatus={'OK' if res.ok else 'FAIL'}")
        show_output = full_output or (not res.ok)
        if show_output and res.stdout.strip():
            out, was_truncated = truncate_for_display(res.stdout, max_chars=max_output_chars, max_lines=stdout_line_cap, full_output=full_output)
            print_section(console, title="stdout", body=out)
            if was_truncated:
                print_status_line(console, "stdout truncated. Use --full for full output.", tone="warning")
        if show_output and res.stderr.strip():
            err, was_truncated = truncate_for_display(res.stderr, max_chars=max_output_chars, max_lines=stderr_line_cap, full_output=full_output)
            print_section(console, title="stderr", body=err)
            if was_truncated:
                print_status_line(console, "stderr truncated. Use --full for full output.", tone="warning")
        return bool(res.ok)

    return True


def run_once(
    *,
    prompt: str,
    full_output: bool,
    console,
    print_session_boundary,
    print_kv_table,
    print_section,
    print_status_line,
    print_answer_path,
    print_cli_notice,
    print_runtime_error,
    session_id: str,
    llm_cls=LLM,
    memory_cls=LongTermMemory,
) -> None:
    started = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command="run", run_id=run_id, phase="start")
    load_project_dotenv()

    paths = Paths.resolve()
    policy = Policy.load(str((paths.home / "agent" / "config" / "policy.json").resolve()))
    api_key = get_openai_api_key()
    llm_used = False
    executed_steps = 0

    def _finish(outcome: str, *, error_type: str = "", error_message: str = "") -> None:
        finish_event(
            paths=paths,
            started=started,
            session_id=session_id,
            command="run",
            route_mode="llm",
            outcome=outcome,
            llm_used=llm_used,
            executed_steps=executed_steps,
            error_type=error_type,
            error_message=error_message,
        )
        print_session_boundary(console, command="run", run_id=run_id, phase="end")

    if not api_key:
        print_cli_notice(
            console,
            title="LLM Required",
            level="warning",
            message="OPENAI_API_KEY is not set.",
            help_line="Set OPENAI_API_KEY and retry.",
        )
        _finish("llm_required")
        return

    memory = memory_cls(chroma_dir=str(paths.chroma_dir), collection_name="cg_memory", openai_api_key=api_key)
    memory_text, memory_count = memory_context(memory, prompt, policy)
    print_kv_table(
        console,
        title="CAD Guardian Agent",
        rows=[
            ("Prompt", prompt),
            ("Mode", "llm-only"),
            ("Memory", f"retrieved={memory_count}"),
            ("Runtime", limits_summary(policy)),
        ],
    )

    llm = llm_cls(api_key=api_key)
    try:
        llm_used = True
        reply = llm.ask(
            prompt,
            memory_text,
            model=policy.llm_model(),
            max_completion_tokens=max(64, policy.max_completion_tokens()),
            task_mode="run",
        )
    except Exception as e:
        print_runtime_error(console, "LLM Error", e, "Check API key, network, and model availability.")
        _finish("llm_error", error_type=type(e).__name__, error_message=str(e))
        return

    if len(reply.plan) > policy.max_steps_per_plan():
        reply.plan = reply.plan[: policy.max_steps_per_plan()]
        print_status_line(console, f"Plan truncated to {policy.max_steps_per_plan()} step(s).", tone="warning")

    answer, truncated = truncate_for_display(
        reply.answer,
        max_chars=policy.max_answer_chars(),
        max_lines=policy.max_answer_lines(),
        full_output=full_output,
    )
    print_section(console, title="Answer", body=answer)
    if truncated:
        print_status_line(console, "Answer truncated. Use --full to expand.", tone="warning")

    plan_lines = [f"{i}. {_step_preview(step)}" for i, step in enumerate(reply.plan, 1)] or ["(no plan steps)"]
    print_section(console, title="Execution Plan", body="\n".join(plan_lines))

    save_memory(memory, user_text=prompt, assistant_text=reply.answer, mode="run")

    actionable = [x for x in reply.plan if str(getattr(x, "type", "")) in {"cmd", "write"}]
    if not actionable:
        print_cli_notice(
            console,
            title="No Actionable Steps",
            level="warning",
            message="The model returned notes only.",
            help_line='Try a direct action request, for example: cg run "create a status summary file"',
        )
        print_answer_path(console, "llm", "LLM returned advisory content only.")
        _finish("no_actionable")
        return

    if _requires_confirmation(prompt, actionable):
        print_cli_notice(
            console,
            title="Confirmation Required",
            level="warning",
            message="Apply-style request detected; no changes executed.",
            help_line="Re-run with confirm:yes to execute steps.",
            example_line='cg run "rename files to snake_case confirm:yes"',
        )
        print_answer_path(console, "llm", "Execution blocked until explicit confirmation token.")
        _finish("confirmation_required")
        return

    mode = policy.execution_mode()
    limit = 1 if mode == "single_step" else min(policy.max_actions_per_run(), len(actionable))
    selected = actionable[: max(1, limit)]
    if mode == "single_step" and len(actionable) > 1:
        print_status_line(console, "Single-step mode: executing first actionable step only.", tone="info")

    executor = Executor(policy=policy, workspace=paths.workspace)
    outcome = "success"
    detail = ""
    for i, step in enumerate(selected, 1):
        print_status_line(console, f"Executing step {i}/{len(selected)}: {_step_preview(step)}", tone="info")
        try:
            executed_steps += 1
            ok = _execute_step(
                executor,
                step,
                timeout_s=policy.max_runtime_seconds(),
                full_output=full_output,
                max_output_chars=policy.max_output_chars(),
                stdout_line_cap=max(1, policy.max_stdout_lines()),
                stderr_line_cap=max(1, policy.max_stderr_lines()),
                print_section=print_section,
                print_status_line=print_status_line,
                console=console,
            )
            if not ok:
                outcome = "command_failed"
                break
        except PolicyViolation as e:
            outcome = "policy_violation"
            detail = str(e)
            rule = getattr(e, "rule", "") or "unknown_policy_rule"
            insight = policy_violation_insight(rule=rule, message=str(e), attempted_action=_step_preview(step))
            print_cli_notice(
                console,
                title="Policy Violation",
                level="error",
                message=str(e),
                help_line=insight["help_line"],
                example_line=insight["example_line"],
            )
            print_section(console, title="Policy Change Insight", body=insight["body"])
            break
        except Exception as e:
            outcome = "execution_error"
            detail = str(e)
            print_runtime_error(console, "Execution Error", e, "Re-run with --full for diagnostics.")
            break

    print_answer_path(console, "both", f"LLM planned actions; executor ran {executed_steps} step(s).")
    save_memory(memory, user_text=prompt, assistant_text=f"run_outcome={outcome} executed_steps={executed_steps}", mode="run", kind="task_result")
    _finish(outcome, error_message=cap_chars(detail, 300))
