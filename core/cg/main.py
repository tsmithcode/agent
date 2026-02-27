from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click
import typer
from dotenv import load_dotenv
from rich.console import Console

from .cli_ui import (
    print_answer_path,
    print_cli_notice,
    print_full_help,
    print_kv_table,
    print_route_decision,
    print_runtime_error,
    print_section,
    print_session_boundary,
    print_status_line,
)
from .doctor import doctor_once
from .executor import Executor, PolicyViolation
from .inspect_ops import (
    extract_depth,
    open_for_review,
    open_target,
    outputs_once,
    structure_once,
    workspace_once,
)
from .llm import LLM
from .memory import LongTermMemory
from .paths import Paths
from .policy import Policy
from .router import decide_route
from .telemetry import append_event, read_events, summarize_events, write_summary_csv, write_summary_json
from cg_utils import cap_chars, truncate_for_display

app = typer.Typer(add_completion=False)
inspect_app = typer.Typer(help="Inspect project structure, workspace files, and output folders.")
dev_app = typer.Typer(help="Developer-only maintenance and QA commands.")
console = Console()
SESSION_ID = str(uuid.uuid4())

app.add_typer(inspect_app, name="inspect")
app.add_typer(dev_app, name="dev")


# Backward-compatible wrappers kept for tests and external imports.
def _print_cli_notice(
    *,
    title: str,
    level: str,
    message: str,
    usage_line: Optional[str] = None,
    help_line: Optional[str] = None,
    example_line: Optional[str] = None,
) -> None:
    print_cli_notice(
        console,
        title=title,
        level=level,
        message=message,
        usage_line=usage_line,
        help_line=help_line,
        example_line=example_line,
    )


def _print_runtime_error(title: str, error: Exception, hint: str) -> None:
    print_runtime_error(console, title, error, hint)


def _print_full_help() -> None:
    print_full_help(console)


def _start_end_session(command_name: str):
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command=command_name, run_id=run_id, phase="start")
    return run_id


def _limits_summary(policy: Policy) -> str:
    return (
        f"mode={policy.execution_mode()} | "
        f"max_tokens={policy.max_completion_tokens()} | "
        f"max_steps={policy.max_steps_per_plan()} | "
        f"max_output_chars={policy.max_output_chars()}"
    )


def _print_run_summary(
    *,
    route_mode: str,
    decision_reason: str,
    outcome: str,
    llm_used: bool,
    handler_id: str = "",
) -> None:
    lines = [
        f"outcome={outcome}",
        f"route={route_mode}",
        f"handler={handler_id or 'n/a'}",
        f"llm_used={llm_used}",
        f"reason={decision_reason or 'n/a'}",
    ]
    print_section(
        console,
        title="Run Summary",
        body="\n".join(lines),
    )


def _log_event(paths: Paths, event: dict[str, Any]) -> None:
    try:
        payload = dict(event)
        payload.setdefault("session_id", SESSION_ID)
        payload.setdefault("run_id", str(uuid.uuid4()))
        append_event(paths.logs_dir, payload)
    except Exception:
        return



def _execute_deterministic_handler(handler_id: str, prompt: str) -> tuple[bool, str]:
    try:
        if handler_id == "inspect_workspace":
            workspace_once(console, extract_depth(prompt, default=4))
            return True, "executed inspect workspace"
        if handler_id == "inspect_outputs":
            outputs_once(console, extract_depth(prompt, default=3))
            return True, "executed inspect outputs"
        if handler_id == "inspect_structure":
            structure_once(console, extract_depth(prompt, default=4))
            return True, "executed inspect structure"
        if handler_id == "dev_snaps":
            _run_snapshot_tests(log_event=False)
            return True, "executed dev snaps"
        return False, f"unknown handler: {handler_id}"
    except SystemExit as e:
        code = int(getattr(e, "code", 1) or 1)
        return code == 0, f"handler exited with code {code}"
    except Exception as e:
        return False, str(e)


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


def _collect_paths(root: Path, *, max_files: int) -> list[str]:
    out: list[str] = []
    skip_dirs = {".git", "venv", "__pycache__", ".logs", ".pytest_cache"}
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            p = (Path(cur) / name)
            try:
                out.append(str(p.relative_to(root)))
            except Exception:
                out.append(str(p))
            if len(out) >= max_files:
                return out
    return out


def _ask_workspace_file_count(question: str, workspace: Path) -> tuple[bool, str]:
    q = (question or "").strip().lower()
    m = re.search(r"\bhow many\s+([a-z0-9._-]+)\s+files?\b", q)
    if not m:
        return False, ""
    target = m.group(1).strip()
    if not target:
        return False, ""

    count = 0
    samples: list[str] = []
    for cur, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".pytest_cache"}]
        for name in files:
            name_l = name.lower()
            matched = name_l == target
            if target.startswith("."):
                matched = name_l.endswith(target)
            if matched:
                count += 1
                if len(samples) < 5:
                    p = (Path(cur) / name)
                    samples.append(str(p.relative_to(workspace)))

    sample_line = f"\nSample paths:\n- " + "\n- ".join(samples) if samples else ""
    answer = f'Found {count} file(s) matching "{target}" in workspace: {workspace}{sample_line}'
    return True, answer


def _collect_runtime_snapshot(paths: Paths, policy: Policy) -> str:
    max_files = max(20, policy.max_context_files())
    max_chars = max(1500, policy.max_context_chars())

    tree_lines = _collect_paths(paths.agent_root, max_files=max_files)
    blocks = ["Project file sample:\n" + "\n".join(f"- {p}" for p in tree_lines)]

    if policy.include_git_status():
        try:
            proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(paths.agent_root),
                capture_output=True,
                text=True,
                timeout=2,
            )
            status = (proc.stdout or proc.stderr or "").strip() or "(clean or unavailable)"
            blocks.append("Git status:\n" + cap_chars(status, 1200))
        except Exception:
            pass

    return cap_chars("\n\n".join(blocks), max_chars)


def _execute_step(
    executor: Executor,
    step: Any,
    *,
    max_runtime_seconds: int,
    max_output_chars: int,
    stdout_line_cap: int,
    stderr_line_cap: int,
    full_output: bool,
) -> bool:
    if step.type == "write":
        if not step.path:
            raise PolicyViolation("write step missing path")
        out_path = executor.write_file(step.path, step.value)
        print_section(
            console,
            title="Write",
            body=f"WROTE {out_path}\nRun complete executed=write",
        )
        return True

    if step.type == "cmd":
        res = executor.run(step.value, timeout_s=max_runtime_seconds)
        print_section(
            console,
            title="Command",
            body=f"CMD {res.command}\nstatus={'OK' if res.ok else 'FAIL'}",
        )
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
        print_section(
            console,
            title="Command Result",
            body=f"Run complete executed=cmd ok={res.ok} exit_code={res.exit_code}",
        )
        return res.ok

    return True


def _memory_context(memory: LongTermMemory, prompt: str, policy: Policy) -> tuple[str, int]:
    max_memory_items = max(1, policy.max_memory_items())
    max_memory_chars = policy.max_memory_chars()
    retrieved_items = memory.query(prompt, n_results=max_memory_items)
    retrieved_text_full = "\n\n".join(
        [f"- {it.text} (kind={str((it.metadata or {}).get('kind', ''))})" for it in retrieved_items]
    ) or "(none)"
    return cap_chars(retrieved_text_full, max_memory_chars), len(retrieved_items)


def _infer_memory_kind(user_text: str, *, mode: str) -> str:
    t = (user_text or "").strip().lower()
    if any(k in t for k in ["prefer ", "i prefer", "always ", "never ", "by default", "do not"]):
        return "preferences"
    if any(k in t for k in ["my name is", "i am ", "i'm ", "about me"]):
        return "user_profile"
    if mode == "run" and any(k in t for k in ["workflow", "pipeline", "scan", "propose", "confirm", "apply", "log"]):
        return "workflow_pattern"
    return "interaction"


def _save_memory(
    memory: LongTermMemory,
    *,
    user_text: str,
    assistant_text: str,
    mode: str,
    kind_override: Optional[str] = None,
    extra_metadata: Optional[dict[str, str]] = None,
) -> None:
    kind = kind_override or _infer_memory_kind(user_text, mode=mode)
    metadata = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "mode": mode,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    try:
        memory.add(
            mem_id=str(uuid.uuid4()),
            text=cap_chars(f"USER: {user_text}\nASSISTANT: {assistant_text}", 4000),
            metadata=metadata,
        )
    except Exception:
        # Memory should improve quality, but must never break core task execution.
        return


def _ask_capability_brief(policy: Policy) -> str:
    allow = ", ".join(sorted(policy.command_allowlist))
    deny = ", ".join(sorted(policy.command_denylist))
    allow_domains = ", ".join(policy.allow_domains())
    return (
        "Agent profile:\n"
        "- Product: CAD Guardian CLI\n"
        "- Modes: run, ask, doctor, inspect, dev\n"
        f"- Execution mode: {policy.execution_mode()} (max_actions_per_run={policy.max_actions_per_run()})\n"
        f"- Limits: max_completion_tokens={policy.max_completion_tokens()}, max_steps_per_plan={policy.max_steps_per_plan()}, "
        f"max_runtime_seconds={policy.max_runtime_seconds()}\n"
        f"- Allowed commands: {allow}\n"
        f"- Denied commands: {deny}\n"
        f"- Allowed HTTP domains: {allow_domains}\n"
        "- Source of truth for architecture: README.md, docs/README.md, core/cg/*.py, config/policy.json\n"
    )


def _run_once(prompt: str, *, full_output: bool = False) -> None:
    started = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command="run", run_id=run_id, phase="start")
    load_dotenv()

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

    api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    route_mode = "llm"
    handler_id = ""
    llm_used = False
    actionable_steps = 0
    executed_steps = 0

    def _finish(outcome: str, *, error_type: str = "", error_message: str = "") -> None:
        _log_event(
            paths,
            {
                "command": "run",
                "route_mode": route_mode,
                "handler_id": handler_id,
                "outcome": outcome,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "llm_used": llm_used,
                "actionable_steps": actionable_steps,
                "executed_steps": executed_steps,
                "error_type": error_type,
                "error_message": cap_chars(error_message or "", 400),
            },
        )
        print_session_boundary(console, command="run", run_id=run_id, phase="end")

    memory = LongTermMemory(
        chroma_dir=str(paths.chroma_dir),
        collection_name="cg_openclaw_memory",
        openai_api_key=api_key,
    )

    decision = decide_route(prompt, policy)
    if decision.mode == "deterministic" and decision.handler_id:
        route_mode = "deterministic"
        handler_id = decision.handler_id
        print_route_decision(console, decision)
        ok, detail = _execute_deterministic_handler(decision.handler_id, prompt)
        print_answer_path(console, "command", f"deterministic handler executed: {decision.handler_id}")
        _save_memory(
            memory,
            user_text=prompt,
            assistant_text=f"deterministic handler={decision.handler_id} detail={detail}",
            mode="run",
            kind_override="task_result",
            extra_metadata={"route_mode": "deterministic", "handler_id": decision.handler_id},
        )
        if not ok:
            print_cli_notice(
                console,
                title="Deterministic Handler Failed",
                level="error",
                message=detail,
                help_line="Rephrase the request or fall back to an LLM-planned run.",
            )
            _print_run_summary(
                route_mode=route_mode,
                decision_reason=decision.reason,
                outcome="handler_failed",
                llm_used=False,
                handler_id=handler_id,
            )
            _finish("handler_failed", error_type="deterministic_handler", error_message=detail)
            raise SystemExit(1)
        _print_run_summary(
            route_mode=route_mode,
            decision_reason=decision.reason,
            outcome="success",
            llm_used=False,
            handler_id=handler_id,
        )
        _finish("success")
        return

    if not api_key:
        route_mode = "llm"
        print_cli_notice(
            console,
            title="LLM Required",
            level="warning",
            message="No deterministic route matched and OPENAI_API_KEY is not set.",
            help_line="Set OPENAI_API_KEY or use an obvious deterministic request like 'show workspace files'.",
        )
        _print_run_summary(
            route_mode=route_mode,
            decision_reason=decision.reason,
            outcome="llm_required",
            llm_used=False,
        )
        _finish("llm_required")
        return

    retrieved_text, retrieved_count = _memory_context(memory, prompt, policy)

    print_kv_table(
        console,
        title="CAD Guardian Agent",
        rows=[
            ("Prompt", prompt),
            ("Memory", f"retrieved={retrieved_count} | sent_chars={len(retrieved_text)}"),
            ("Runtime", _limits_summary(policy)),
        ],
    )
    print_route_decision(console, decision)

    llm = LLM(api_key=api_key)
    try:
        llm_used = True
        reply = llm.ask(prompt, retrieved_text, max_completion_tokens=max_completion_tokens)
    except Exception as e:
        print_runtime_error(
            console,
            "LLM Error",
            e,
            "Check OPENAI_API_KEY, internet/DNS, and policy allow_domains settings.",
        )
        _print_run_summary(
            route_mode=route_mode,
            decision_reason=decision.reason,
            outcome="llm_error",
            llm_used=True,
        )
        _finish("llm_error", error_type=type(e).__name__, error_message=str(e))
        return

    if len(reply.plan) > max_steps_per_plan:
        reply.plan = reply.plan[:max_steps_per_plan]
        print_status_line(console, f"Plan truncated to {max_steps_per_plan} steps.", tone="warning")

    step_lines = [f"{i}. {_step_preview_text(s)}" for i, s in enumerate(reply.plan, 1)] or ["(no plan steps returned)"]
    print_section(console, title="Execution Plan", body="\n".join(step_lines))

    answer_display, answer_truncated = truncate_for_display(
        reply.answer,
        max_chars=max_response_chars,
        max_lines=max_summary_lines,
        full_output=full_output,
    )
    print_section(console, title="Answer", body=answer_display)
    if answer_truncated:
        print_status_line(console, "Answer truncated. Use --full or raise answer limits in policy.", tone="warning")

    _save_memory(
        memory,
        user_text=prompt,
        assistant_text=reply.answer,
        mode="run",
        extra_metadata={"route_mode": "llm"},
    )

    actionable = _actionable_steps(reply.plan)
    actionable_steps = len(actionable)
    if not actionable:
        print_answer_path(console, "llm", "LLM answer returned notes only; no executable actions in plan")
        _save_memory(
            memory,
            user_text=prompt,
            assistant_text="run_outcome=no_actionable executed_steps=0 actionable_steps=0",
            mode="run",
            kind_override="task_result",
            extra_metadata={"route_mode": "llm"},
        )
        print_cli_notice(
            console,
            title="No Actionable Steps",
            level="warning",
            message="The model returned notes only; nothing can be executed.",
            help_line='Try a direct action request, e.g. cg run "list files in workspace".',
            example_line='cg ask "What command should I run to inspect current files?"',
        )
        _print_run_summary(
            route_mode=route_mode,
            decision_reason=decision.reason,
            outcome="no_actionable",
            llm_used=True,
        )
        _finish("no_actionable")
        return

    mode = policy.execution_mode()
    max_actions = max(1, policy.max_actions_per_run())
    if mode == "single_step":
        selected = actionable[:1]
    else:
        selected = actionable[:max_actions]

    if _requires_apply_confirmation(prompt, selected) and not _has_confirm_token(prompt):
        print_cli_notice(
            console,
            title="Confirmation Required",
            level="warning",
            message="Apply-style request detected. No changes were executed.",
            help_line="Re-run with confirm:yes to apply the proposed actions.",
            example_line='cg run "rename files to snake_case in workspace confirm:yes"',
        )
        print_answer_path(console, "llm", "LLM generated an apply plan; execution blocked until explicit confirmation")
        _save_memory(
            memory,
            user_text=prompt,
            assistant_text="run_outcome=confirmation_required executed_steps=0",
            mode="run",
            kind_override="task_result",
            extra_metadata={"route_mode": "llm"},
        )
        _print_run_summary(
            route_mode=route_mode,
            decision_reason=decision.reason,
            outcome="confirmation_required",
            llm_used=True,
        )
        _finish("confirmation_required")
        return

    if mode == "continue_until_done" and len(actionable) > len(selected):
        print_status_line(
            console,
            f"Execution capped actionable_steps={len(actionable)} -> executing={len(selected)} (max_actions_per_run={max_actions})",
            tone="warning",
        )

    executor = Executor(policy=policy, workspace=paths.workspace)
    executed_steps = 0
    outcome = "completed"
    outcome_detail = ""
    for i, step in enumerate(selected, 1):
        print_status_line(console, f"Executing step {i}/{len(selected)} {_step_preview_text(step)}", tone="info")
        try:
            executed_steps += 1
            ok = _execute_step(
                executor,
                step,
                max_runtime_seconds=max_runtime_seconds,
                max_output_chars=max_output_chars,
                stdout_line_cap=stdout_line_cap,
                stderr_line_cap=stderr_line_cap,
                full_output=full_output,
            )
            if not ok:
                outcome = "command_failed"
                print_cli_notice(
                    console,
                    title="Execution Stopped",
                    level="warning",
                    message="A command failed; stopping remaining steps.",
                    help_line="Re-run with --full to inspect stdout/stderr, then retry.",
                )
                break
        except PolicyViolation as e:
            outcome = "policy_violation"
            rule = getattr(e, "rule", "") or "unknown_policy_rule"
            outcome_detail = f"{str(e)} (rule={rule})"
            print_cli_notice(
                console,
                title="Policy Violation",
                level="error",
                message=str(e),
                help_line=f"Violated policy: {rule} (config/policy.json).",
                example_line="cg doctor --verbose",
            )
            break
        except Exception as e:
            outcome = "execution_error"
            outcome_detail = str(e)
            print_runtime_error(console, "Execution Error", e, "Re-run with --full and inspect command/output details.")
            break

    if mode == "single_step" and len(actionable) > 1:
        print_status_line(console, "Stopped after 1 actionable step (policy: execution_mode=single_step).", tone="info")

    print_answer_path(console, "both", f"LLM planned actions; executor ran {executed_steps} step(s) under policy")

    task_result = (
        f"run_outcome={outcome} executed_steps={executed_steps}/{len(selected)} "
        f"actionable_steps={len(actionable)} execution_mode={mode}"
    )
    if outcome_detail:
        task_result += f" detail={cap_chars(outcome_detail, 300)}"
    _save_memory(
        memory,
        user_text=prompt,
        assistant_text=task_result,
        mode="run",
        kind_override="task_result",
        extra_metadata={"route_mode": "llm"},
    )
    _print_run_summary(
        route_mode=route_mode,
        decision_reason=decision.reason,
        outcome="success" if outcome == "completed" else outcome,
        llm_used=True,
        handler_id=handler_id,
    )
    _finish("success" if outcome == "completed" else outcome, error_message=outcome_detail)


def _ask_once(question: str, *, full_output: bool = False, context: bool = False) -> None:
    started = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command="ask", run_id=run_id, phase="start")
    load_dotenv()

    paths = Paths.resolve()
    policy_path = (paths.home / "agent" / "config" / "policy.json").resolve()
    policy = Policy.load(str(policy_path))

    max_response_chars = policy.max_answer_chars()
    max_summary_lines = policy.max_answer_lines()
    max_completion_tokens = max(64, policy.max_completion_tokens())
    llm_used = False
    ask_route_mode = "llm"
    ask_handler_id = ""

    def _finish(outcome: str, *, error_type: str = "", error_message: str = "") -> None:
        _log_event(
            paths,
            {
                "command": "ask",
                "route_mode": ask_route_mode,
                "handler_id": ask_handler_id,
                "outcome": outcome,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "llm_used": llm_used,
                "actionable_steps": 0,
                "executed_steps": 0,
                "error_type": error_type,
                "error_message": cap_chars(error_message or "", 400),
            },
        )
        print_session_boundary(console, command="ask", run_id=run_id, phase="end")

    matched_count, count_answer = _ask_workspace_file_count(question, paths.workspace)
    if matched_count:
        ask_route_mode = "deterministic"
        ask_handler_id = "count_files_by_name"
        print_kv_table(
            console,
            title="CAD Guardian Insight",
            rows=[
                ("Question", question),
                ("Context", "deterministic_workspace_scan=true"),
                ("Runtime", _limits_summary(policy)),
            ],
        )
        answer_display, answer_truncated = truncate_for_display(
            count_answer,
            max_chars=max_response_chars,
            max_lines=max_summary_lines,
            full_output=full_output,
        )
        print_section(console, title="Insight Answer", body=answer_display)
        print_answer_path(console, "command", "deterministic ask handler scanned workspace files")
        if answer_truncated:
            print_status_line(console, "Insight answer truncated. Use --full for full response.", tone="warning")
        _save_memory(
            LongTermMemory(
                chroma_dir=str(paths.chroma_dir),
                collection_name="cg_openclaw_memory",
                openai_api_key=(os.getenv("OPENAI_API_KEY", "").strip() or None),
            ),
            user_text=question,
            assistant_text=count_answer,
            mode="ask",
            kind_override="task_result",
            extra_metadata={"route_mode": "deterministic", "handler_id": "count_files_by_name"},
        )
        _finish("success")
        return

    api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    if not api_key:
        print_status_line(console, "OPENAI_API_KEY not set. LLM call skipped.", tone="warning")
        _finish("llm_required")
        return

    memory = LongTermMemory(
        chroma_dir=str(paths.chroma_dir),
        collection_name="cg_openclaw_memory",
        openai_api_key=api_key,
    )

    # Ask mode is source-first: keep memory as light, secondary context.
    ask_memory_items = min(2, max(1, policy.max_memory_items()))
    ask_memory_chars = min(800, policy.max_memory_chars())
    retrieved_items = memory.query(question, n_results=ask_memory_items)
    retrieved_count = len(retrieved_items)
    retrieved_text_full = "\n\n".join(
        [f"- {it.text} (kind={str((it.metadata or {}).get('kind', ''))})" for it in retrieved_items]
    ) or "(none)"
    retrieved_text = cap_chars(retrieved_text_full, ask_memory_chars)
    snapshot_text = _collect_runtime_snapshot(paths, policy)
    capability_text = _ask_capability_brief(policy)
    context_text = (
        f"{capability_text}\n"
        f"Runtime/source snapshot (primary):\n{snapshot_text}\n\n"
        f"Memory context (secondary):\n{retrieved_text}"
    )

    if context:
        preview = cap_chars(context_text, 12000, full_output=full_output)
        print_section(console, title="Ask Context", body=preview)

    print_kv_table(
        console,
        title="CAD Guardian Insight",
        rows=[
            ("Question", question),
            ("Context", f"memory_items={retrieved_count} (secondary) | context_chars={len(context_text)}"),
            ("Runtime", _limits_summary(policy)),
        ],
    )

    llm = LLM(api_key=api_key)
    try:
        llm_used = True
        reply = llm.ask(
            question,
            context_text,
            max_completion_tokens=max_completion_tokens,
            task_mode="ask",
        )
    except Exception as e:
        print_runtime_error(
            console,
            "LLM Error",
            e,
            "Check OPENAI_API_KEY, internet/DNS, and policy allow_domains settings.",
        )
        _finish("llm_error", error_type=type(e).__name__, error_message=str(e))
        return

    answer_display, answer_truncated = truncate_for_display(
        reply.answer,
        max_chars=max_response_chars,
        max_lines=max_summary_lines,
        full_output=full_output,
    )
    print_section(console, title="Insight Answer", body=answer_display)
    print_answer_path(console, "llm", "ask mode is read-only and uses LLM over runtime snapshot context")
    if answer_truncated:
        print_status_line(console, "Insight answer truncated. Use --full for full response.", tone="warning")

    _save_memory(
        memory,
        user_text=question,
        assistant_text=reply.answer,
        mode="ask",
    )
    _finish("success")


def _run_snapshot_tests(*, log_event: bool = True) -> None:
    started = time.perf_counter()
    paths = Paths.resolve()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = (paths.workspace / "reports" / "ui-snapshots" / run_id).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "snapshot-test-report.txt"

    cmd = [sys.executable, "-m", "unittest", "-v", "tests.test_cli_snapshots"]
    proc = subprocess.run(
        cmd,
        cwd=str((paths.agent_root / "core").resolve()),
        capture_output=True,
        text=True,
    )

    body = [
        f"CAD Guardian Snapshot Test Report",
        f"timestamp={datetime.now(timezone.utc).isoformat()}",
        f"command={' '.join(cmd)}",
        f"exit_code={proc.returncode}",
        "",
        "=== STDOUT ===",
        proc.stdout or "(empty)",
        "",
        "=== STDERR ===",
        proc.stderr or "(empty)",
    ]
    report_file.write_text("\n".join(body), encoding="utf-8")

    level = "success" if proc.returncode == 0 else "error"
    title = "Snapshot Tests Passed" if proc.returncode == 0 else "Snapshot Tests Failed"
    print_cli_notice(
        console,
        title=title,
        level=level,
        message=f"Report saved: {report_file}",
        help_line="Review the report for exact screen snapshots and assertion details.",
    )

    opened = open_for_review(report_file)
    if not opened:
        preview = cap_chars(report_file.read_text(encoding="utf-8", errors="ignore"), 3000)
        print_section(console, title="Report Preview (open unavailable)", body=preview)

    if log_event:
        _log_event(
            paths,
            {
                "command": "dev_snaps",
                "route_mode": "deterministic",
                "handler_id": "dev_snaps",
                "outcome": "success" if proc.returncode == 0 else "error",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "llm_used": False,
                "actionable_steps": 1,
                "executed_steps": 1,
                "error_type": "" if proc.returncode == 0 else "snapshot_tests_failed",
                "error_message": "" if proc.returncode == 0 else "unittest exit_code != 0",
            },
        )

    if proc.returncode != 0:
        raise SystemExit(1)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """CAD Guardian CLI."""
    if ctx.invoked_subcommand is not None:
        return
    print_cli_notice(
        console,
        title="Command Required",
        level="warning",
        message="Select a command to continue.",
        usage_line='cg run "<prompt>" [--full]  (or: cg ask "<question>")',
        help_line="Run cg --help to see available commands and options.",
        example_line='cg run "summarize workspace"',
    )
    raise SystemExit(1)


@app.command("run")
def run(
    prompt: str = typer.Argument(..., help="Prompt to run."),
    full_output: bool = typer.Option(False, "--full", help="Disable output truncation for answer/stdout/stderr."),
):
    """Run CAD Guardian Agent with a prompt."""
    _run_once(prompt, full_output=full_output)


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="Question about the current project state."),
    full_output: bool = typer.Option(False, "--full", help="Disable answer truncation."),
    context: bool = typer.Option(False, "--ctx", help="Show the context payload sent to the model."),
):
    """Read-only Q&A over current source/workspace state."""
    _ask_once(question, full_output=full_output, context=context)


@app.command("doctor")
def doctor(
    verbose: bool = typer.Option(False, "--verbose", help="Show full path inventory and expanded diagnostics."),
):
    """Run onboarding diagnostics and environment checks."""
    run_id = _start_end_session("doctor")
    started = time.perf_counter()
    outcome = "success"
    err_type = ""
    err_msg = ""
    summary: dict[str, int] = {"checks": 0, "pass": 0, "warn": 0, "fail": 0}
    try:
        summary = doctor_once(console, verbose=verbose)
        if summary.get("fail", 0) > 0:
            outcome = "fail"
        elif summary.get("warn", 0) > 0:
            outcome = "warn"
    except Exception as e:
        outcome = "error"
        err_type = type(e).__name__
        err_msg = str(e)
        raise
    finally:
        try:
            paths = Paths.resolve()
            _log_event(
                paths,
                {
                    "command": "doctor",
                    "route_mode": "n/a",
                    "handler_id": "",
                    "outcome": outcome,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "llm_used": False,
                    "actionable_steps": 0,
                    "executed_steps": 0,
                    "error_type": err_type,
                    "error_message": cap_chars(err_msg, 400),
                    "doctor_warn": int(summary.get("warn", 0)),
                    "doctor_fail": int(summary.get("fail", 0)),
                    "doctor_checks": int(summary.get("checks", 0)),
                    "verbose": bool(verbose),
                },
            )
        except Exception:
            pass
        print_session_boundary(console, command="doctor", run_id=run_id, phase="end")


@dev_app.command("snaps")
def dev_snaps():
    """Run CLI snapshot tests, save report in workspace, and open it."""
    run_id = _start_end_session("dev.snaps")
    try:
        _run_snapshot_tests()
    finally:
        print_session_boundary(console, command="dev.snaps", run_id=run_id, phase="end")


@dev_app.command("metrics")
def dev_metrics(
    fmt: str = typer.Option("json", "--format", help="Summary report format: json or csv."),
    limit: int = typer.Option(0, "--limit", min=0, help="Optional tail limit of events (0 = all)."),
):
    """Aggregate JSONL telemetry into BI-ready summary report files."""
    f = (fmt or "json").strip().lower()
    if f not in {"json", "csv"}:
        print_cli_notice(
            console,
            title="Invalid Format",
            level="error",
            message=f"Unsupported format: {fmt}",
            help_line="Use --format json or --format csv.",
        )
        raise SystemExit(2)

    paths = Paths.resolve()
    events = read_events(paths.logs_dir, limit=(limit or None))
    summary = summarize_events(events)

    report_run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = (paths.workspace / "reports" / "metrics" / report_run_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"metrics-summary.{f}"

    if f == "json":
        write_summary_json(out_file, summary)
    else:
        write_summary_csv(out_file, summary)

    print_cli_notice(
        console,
        title="Metrics Report Ready",
        level="success",
        message=f"Saved: {out_file}",
        help_line=f"events_total={summary.get('events_total', 0)} | llm_used_rate={summary.get('llm_used_rate', 0.0)}",
    )


@dev_app.command("dashboard")
def dev_dashboard(
    live: bool = typer.Option(True, "--live", help="Enable auto-refresh while dashboard is open."),
    refresh_seconds: int = typer.Option(5, "--refresh-seconds", min=1, max=60, help="Auto-refresh interval."),
    port: int = typer.Option(8501, "--port", min=1024, max=65535, help="Dashboard port."),
    event_limit: int = typer.Option(5000, "--event-limit", min=100, max=50000, help="Max telemetry events loaded."),
):
    """Launch a live Streamlit dashboard for full environment reporting."""
    run_id = _start_end_session("dev.dashboard")
    try:
        paths = Paths.resolve()
        try:
            import streamlit  # noqa: F401
        except Exception:
            print_cli_notice(
                console,
                title="Missing Dependency",
                level="error",
                message="Streamlit is not installed.",
                help_line="Install with: pip install streamlit",
            )
            raise SystemExit(1)

        app_path = (paths.agent_root / "core" / "cg" / "dashboard_app.py").resolve()
        policy_path = (paths.agent_root / "config" / "policy.json").resolve()
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.headless",
            "true",
            "--server.port",
            str(port),
            "--",
            "--workspace",
            str(paths.workspace),
            "--logs-dir",
            str(paths.logs_dir),
            "--chroma-dir",
            str(paths.chroma_dir),
            "--policy",
            str(policy_path),
            "--live",
            "1" if live else "0",
            "--refresh-seconds",
            str(refresh_seconds),
            "--event-limit",
            str(event_limit),
        ]
        subprocess.Popen(cmd, cwd=str(paths.agent_root))
        url = f"http://127.0.0.1:{port}"
        open_target(url)
        print_cli_notice(
            console,
            title="Dashboard Started",
            level="success",
            message=f"Live dashboard available at {url}",
            help_line=f"live={live} refresh_seconds={refresh_seconds} event_limit={event_limit}",
        )
    finally:
        print_session_boundary(console, command="dev.dashboard", run_id=run_id, phase="end")


@inspect_app.command("structure")
def inspect_structure(
    depth: int = typer.Option(4, "-d", min=1, max=10, help="Tree depth (default: 4)."),
):
    """Show solution structure from home path."""
    structure_once(console, depth)


@inspect_app.command("workspace")
def inspect_workspace(
    depth: Optional[int] = typer.Option(None, "-d", min=1, max=10, help="Optional tree depth limit."),
):
    """Show all files under workspace."""
    workspace_once(console, depth)


@inspect_app.command("outputs")
def inspect_outputs(
    depth: Optional[int] = typer.Option(None, "-d", min=1, max=10, help="Optional tree depth limit."),
):
    """Show output folders (reports, logs, artifacts)."""
    outputs_once(console, depth)


def cli() -> None:
    if len(sys.argv) == 2 and sys.argv[1] in {"--help", "-h"}:
        print_full_help(console)
        return
    try:
        app(standalone_mode=False)
    except click.exceptions.UsageError as e:
        msg = str(e)
        m = re.search(r"No such command '([^']+)'\.", msg)
        if m:
            cmd = m.group(1)
            print_cli_notice(
                console,
                title=f"Unknown Command: {cmd}",
                level="error",
                message=msg,
                help_line="Run cg --help to see available commands and options.",
                example_line='cg run "summarize workspace"',
            )
            raise SystemExit(2)
        print_cli_notice(
            console,
            title="Command Usage Error",
            level="error",
            message=msg,
            help_line="CLI argument parsing error (no policy rule evaluated). Run cg --help for valid syntax.",
        )
        raise SystemExit(2)
    except click.exceptions.Exit as e:
        raise SystemExit(e.exit_code)


if __name__ == "__main__":
    cli()
