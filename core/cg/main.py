from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .executor import Executor, PolicyViolation
from .llm import LLM
from .memory import LongTermMemory
from .paths import Paths
from .policy import Policy

app = typer.Typer(add_completion=False)
console = Console()


def _print_cli_notice(
    *,
    title: str,
    level: str,
    message: str,
    usage_line: Optional[str] = None,
    help_line: Optional[str] = None,
    example_line: Optional[str] = None,
) -> None:
    border_style = {"warning": "yellow", "error": "red", "success": "green"}.get(level, "cyan")
    status = f"[{border_style}][{level}][/{border_style}]"
    lines = [f"{status} {message}"]
    if usage_line:
        lines.append(f"  [cyan]Usage:[/cyan] {usage_line}")
    if help_line:
        lines.append(f"  [cyan]Help:[/cyan] {help_line}")
    if example_line:
        lines.append(f"  [green][success][/green] Example: [bold]{example_line}[/bold]")
    console.print(Panel("\n".join(lines), title=title, expand=False, border_style=border_style))


def _limits_summary(policy: Policy) -> str:
    return (
        f"mode={policy.execution_mode()} | "
        f"max_tokens={policy.max_completion_tokens()} | "
        f"max_steps={policy.max_steps_per_plan()} | "
        f"max_output_chars={policy.max_output_chars()}"
    )


def _print_runtime_error(title: str, error: Exception, hint: str) -> None:
    _print_cli_notice(
        title=title,
        level="error",
        message=str(error),
        help_line=hint,
    )


def _print_full_help() -> None:
    console.print(
        Panel(
            "CAD Guardian CLI\n"
            "Policy-controlled AI agent for execution, read-only insight, diagnostics, and UI snapshot QA.",
            title="Help",
            expand=False,
        )
    )

    table = Table(title="Commands and Flags")
    table.add_column("Command", style="cyan", no_wrap=True)
    table.add_column("Arguments", no_wrap=True)
    table.add_column("Flags", overflow="fold")
    table.add_column("Purpose", overflow="fold")

    table.add_row(
        "cg run",
        "PROMPT",
        "--full-output",
        "Run agent plan and execute actionable steps under policy.",
    )
    table.add_row(
        "cg ask",
        "QUESTION",
        "--full-output, --context",
        "Read-only Q&A using source/workspace snapshot and memory.",
    )
    table.add_row(
        "cg doctor",
        "(none)",
        "(none)",
        "Run onboarding and environment diagnostics.",
    )
    table.add_row(
        "cg snapshot-tests",
        "(none)",
        "(none)",
        "Run CLI snapshot tests, save report to workspace, open/preview report.",
    )
    table.add_row(
        "cg --help",
        "(none)",
        "(none)",
        "Show this expanded help view.",
    )

    console.print(table)
    console.print(
        Panel(
            "Examples:\n"
            "  cg run \"List files in workspace\"\n"
            "  cg run \"Run tests\" --full-output\n"
            "  cg ask \"What does this app do?\" --context\n"
            "  cg doctor\n"
            "  cg snapshot-tests",
            title="Quick Examples",
            expand=False,
        )
    )


def _open_for_review(path: Path) -> bool:
    cmds: list[list[str]] = []
    if sys.platform.startswith("darwin"):
        cmds.append(["open", str(path)])
    elif os.name == "nt":
        cmds.append(["cmd", "/c", "start", "", str(path)])
    else:
        cmds.append(["xdg-open", str(path)])

    for cmd in cmds:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    return False


def _cap_chars(s: str, max_chars: int, *, full_output: bool = False) -> str:
    if full_output or max_chars <= 0 or len(s) <= max_chars:
        return s
    return s[:max_chars] + "...(truncated)"


def _cap_lines(text: str, max_lines: int, *, full_output: bool = False) -> str:
    if full_output or max_lines <= 0:
        return text
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n...(truncated lines)"


def _truncate_for_display(
    text: str,
    *,
    max_chars: int,
    max_lines: int,
    full_output: bool,
) -> tuple[str, bool]:
    capped_chars = _cap_chars(text, max_chars, full_output=full_output)
    out = _cap_lines(capped_chars, max_lines, full_output=full_output)
    truncated = (not full_output) and (out != text)
    return out, truncated


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
    skip_dirs = {".git", "venv", "__pycache__", ".logs", "reports", ".pytest_cache"}
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


def _read_preview(path: Path, *, max_chars: int) -> str:
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "(unreadable)"
    return txt if len(txt) <= max_chars else txt[:max_chars] + "...(truncated)"


def _collect_runtime_snapshot(paths: Paths, policy: Policy) -> str:
    max_files = max(20, policy.max_context_files())
    per_file_chars = max(200, policy.max_context_file_chars())
    max_chars = max(1500, policy.max_context_chars())

    tree_lines = _collect_paths(paths.agent_root, max_files=max_files)
    blocks = ["Project file sample:\n" + "\n".join(f"- {p}" for p in tree_lines)]

    key_files = [
        paths.agent_root / "README.md",
        paths.agent_root / "docs" / "README.md",
        paths.agent_root / "config" / "policy.json",
        paths.agent_root / "core" / "cg" / "main.py",
        paths.agent_root / "core" / "cg" / "policy.py",
        paths.agent_root / "core" / "cg" / "executor.py",
    ]
    for fp in key_files:
        if fp.exists():
            blocks.append(f"File preview: {fp}\n{_read_preview(fp, max_chars=per_file_chars)}")

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
            blocks.append("Git status:\n" + _cap_chars(status, 1200))
        except Exception:
            pass

    return _cap_chars("\n\n".join(blocks), max_chars)


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
        console.print(f"[green]WROTE[/green] {out_path}")
        console.print("[green]Run complete[/green] executed=write")
        return True

    if step.type == "cmd":
        res = executor.run(step.value, timeout_s=max_runtime_seconds)
        console.print(f"[cyan]CMD[/cyan] {res.command}  [bold]{'OK' if res.ok else 'FAIL'}[/bold]")
        show_output = full_output or (not res.ok)
        if show_output and res.stdout.strip():
            out, truncated = _truncate_for_display(
                res.stdout,
                max_chars=max_output_chars,
                max_lines=stdout_line_cap,
                full_output=full_output,
            )
            console.print(Panel(out, title="stdout", expand=False))
            if truncated:
                console.print("[yellow]stdout truncated[/yellow] Use [bold]--full-output[/bold] to view full output.")
        if show_output and res.stderr.strip():
            err, truncated = _truncate_for_display(
                res.stderr,
                max_chars=max_output_chars,
                max_lines=stderr_line_cap,
                full_output=full_output,
            )
            console.print(Panel(err, title="stderr", expand=False))
            if truncated:
                console.print("[yellow]stderr truncated[/yellow] Use [bold]--full-output[/bold] to view full output.")
        console.print(f"[green]Run complete[/green] executed=cmd ok={res.ok} exit_code={res.exit_code}")
        return res.ok

    return True


def _memory_context(memory: LongTermMemory, prompt: str, policy: Policy) -> tuple[str, int]:
    max_memory_items = max(1, policy.max_memory_items())
    max_memory_chars = policy.max_memory_chars()
    retrieved_items = memory.query(prompt, n_results=max_memory_items)
    retrieved_text_full = "\n\n".join(
        [f"- {it.text} (kind={str((it.metadata or {}).get('kind', ''))})" for it in retrieved_items]
    ) or "(none)"
    return _cap_chars(retrieved_text_full, max_memory_chars), len(retrieved_items)


def _ask_capability_brief(policy: Policy) -> str:
    allow = ", ".join(sorted(policy.command_allowlist))
    deny = ", ".join(sorted(policy.command_denylist))
    allow_domains = ", ".join(policy.allow_domains())
    return (
        "Agent profile:\n"
        "- Product: CAD Guardian CLI\n"
        "- Modes: run (execute), ask (read-only), doctor (diagnostics), snapshot-tests (UI QA)\n"
        f"- Execution mode: {policy.execution_mode()} (max_actions_per_run={policy.max_actions_per_run()})\n"
        f"- Limits: max_completion_tokens={policy.max_completion_tokens()}, max_steps_per_plan={policy.max_steps_per_plan()}, "
        f"max_runtime_seconds={policy.max_runtime_seconds()}\n"
        f"- Allowed commands: {allow}\n"
        f"- Denied commands: {deny}\n"
        f"- Allowed HTTP domains: {allow_domains}\n"
        "- Source of truth for architecture: README.md, docs/README.md, core/cg/*.py, config/policy.json\n"
    )


def _run_once(prompt: str, *, full_output: bool = False) -> None:
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
    if not api_key:
        console.print("[yellow]OPENAI_API_KEY not set. LLM call skipped.[/yellow]")
        return

    memory = LongTermMemory(
        chroma_dir=str(paths.chroma_dir),
        collection_name="cg_openclaw_memory",
        openai_api_key=api_key,
    )

    retrieved_text, retrieved_count = _memory_context(memory, prompt, policy)

    console.print(
        Panel(
            f"[bold]Prompt[/bold]\n{prompt}\n\n[bold]Memory[/bold]\n"
            f"retrieved={retrieved_count} | sent_chars={len(retrieved_text)}\n\n"
            f"[bold]Runtime[/bold]\n{_limits_summary(policy)}",
            title="CAD Guardian Agent",
            expand=False,
        )
    )

    llm = LLM(api_key=api_key)
    try:
        reply = llm.ask(prompt, retrieved_text, max_completion_tokens=max_completion_tokens)
    except Exception as e:
        _print_runtime_error(
            "LLM Error",
            e,
            "Check OPENAI_API_KEY, internet/DNS, and policy allow_domains settings.",
        )
        return

    if len(reply.plan) > max_steps_per_plan:
        reply.plan = reply.plan[:max_steps_per_plan]
        console.print(f"[yellow]Plan truncated to {max_steps_per_plan} steps.[/yellow]")

    step_lines = [f"{i}. {_step_preview_text(s)}" for i, s in enumerate(reply.plan, 1)] or ["(no plan steps returned)"]
    console.print(Panel("\n".join(step_lines), title="Execution Plan", expand=False))

    answer_display, answer_truncated = _truncate_for_display(
        reply.answer,
        max_chars=max_response_chars,
        max_lines=max_summary_lines,
        full_output=full_output,
    )
    console.print(Panel(answer_display, title="Answer", expand=False))
    if answer_truncated:
        console.print("[yellow]Answer truncated[/yellow] Use [bold]--full-output[/bold] or raise answer limits in policy.")

    memory.add(
        mem_id=str(uuid.uuid4()),
        text=_cap_chars(f"USER: {prompt}\nASSISTANT: {reply.answer}", 4000),
        metadata={"ts_utc": datetime.now(timezone.utc).isoformat(), "kind": "interaction"},
    )

    actionable = _actionable_steps(reply.plan)
    if not actionable:
        _print_cli_notice(
            title="No Actionable Steps",
            level="warning",
            message="The model returned notes only; nothing can be executed.",
            help_line='Try a direct action request, e.g. cg run "list files in workspace".',
            example_line='cg ask "What command should I run to inspect current files?"',
        )
        return

    mode = policy.execution_mode()
    max_actions = max(1, policy.max_actions_per_run())
    if mode == "single_step":
        selected = actionable[:1]
    else:
        selected = actionable[:max_actions]

    if mode == "continue_until_done" and len(actionable) > len(selected):
        console.print(
            f"[yellow]Execution capped[/yellow] actionable_steps={len(actionable)} -> executing={len(selected)} (max_actions_per_run={max_actions})"
        )

    executor = Executor(policy=policy, workspace=paths.workspace)
    for i, step in enumerate(selected, 1):
        console.print(f"[dim]Executing step {i}/{len(selected)}[/dim] {_step_preview_text(step)}")
        try:
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
                _print_cli_notice(
                    title="Execution Stopped",
                    level="warning",
                    message="A command failed; stopping remaining steps.",
                    help_line="Re-run with --full-output to inspect stdout/stderr, then retry.",
                )
                break
        except PolicyViolation as e:
            _print_runtime_error("Policy Violation", e, "Review policy allow/deny settings and requested operation.")
            break
        except Exception as e:
            _print_runtime_error("Execution Error", e, "Re-run with --full-output and inspect command/output details.")
            break

    if mode == "single_step" and len(actionable) > 1:
        console.print("[dim]Stopped after 1 actionable step (policy: execution_mode=single_step).[/dim]")


def _ask_once(question: str, *, full_output: bool = False, context: bool = False) -> None:
    load_dotenv()

    paths = Paths.resolve()
    policy_path = (paths.home / "agent" / "config" / "policy.json").resolve()
    policy = Policy.load(str(policy_path))

    max_response_chars = policy.max_answer_chars()
    max_summary_lines = policy.max_answer_lines()
    max_completion_tokens = max(64, policy.max_completion_tokens())

    api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    if not api_key:
        console.print("[yellow]OPENAI_API_KEY not set. LLM call skipped.[/yellow]")
        return

    memory = LongTermMemory(
        chroma_dir=str(paths.chroma_dir),
        collection_name="cg_openclaw_memory",
        openai_api_key=api_key,
    )

    # Ask mode is source-first: keep memory as light, secondary context.
    ask_memory_items = 1
    ask_memory_chars = min(800, policy.max_memory_chars())
    retrieved_items = memory.query(question, n_results=ask_memory_items)
    retrieved_count = len(retrieved_items)
    retrieved_text_full = "\n\n".join(
        [f"- {it.text} (kind={str((it.metadata or {}).get('kind', ''))})" for it in retrieved_items]
    ) or "(none)"
    retrieved_text = _cap_chars(retrieved_text_full, ask_memory_chars)
    snapshot_text = _collect_runtime_snapshot(paths, policy)
    capability_text = _ask_capability_brief(policy)
    context_text = (
        f"{capability_text}\n"
        f"Runtime/source snapshot (primary):\n{snapshot_text}\n\n"
        f"Memory context (secondary):\n{retrieved_text}"
    )

    if context:
        preview = _cap_chars(context_text, 12000, full_output=full_output)
        console.print(Panel(preview, title="Ask Context", expand=False))

    console.print(
        Panel(
            f"[bold]Question[/bold]\n{question}\n\n[bold]Context[/bold]\n"
            f"memory_items={retrieved_count} (secondary) | context_chars={len(context_text)}\n\n"
            f"[bold]Runtime[/bold]\n{_limits_summary(policy)}",
            title="CAD Guardian Insight",
            expand=False,
        )
    )

    llm = LLM(api_key=api_key)
    try:
        reply = llm.ask(
            question,
            context_text,
            max_completion_tokens=max_completion_tokens,
            task_mode="ask",
        )
    except Exception as e:
        _print_runtime_error(
            "LLM Error",
            e,
            "Check OPENAI_API_KEY, internet/DNS, and policy allow_domains settings.",
        )
        return

    answer_display, answer_truncated = _truncate_for_display(
        reply.answer,
        max_chars=max_response_chars,
        max_lines=max_summary_lines,
        full_output=full_output,
    )
    console.print(Panel(answer_display, title="Insight Answer", expand=False))
    if answer_truncated:
        console.print("[yellow]Insight answer truncated[/yellow] Use [bold]--full-output[/bold] for full response.")

    memory.add(
        mem_id=str(uuid.uuid4()),
        text=_cap_chars(f"USER: {question}\nASSISTANT: {reply.answer}", 4000),
        metadata={"ts_utc": datetime.now(timezone.utc).isoformat(), "kind": "interaction"},
    )


def _doctor_once() -> None:
    load_dotenv()
    rows: list[tuple[str, str, str]] = []

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    rows.append(("OPENAI_API_KEY", "PASS" if api_key else "WARN", "Set" if api_key else "Missing"))

    policy: Optional[Policy] = None
    paths: Optional[Paths] = None
    try:
        paths = Paths.resolve()
        rows.append(("Paths.resolve()", "PASS", str(paths.agent_root)))
    except Exception as e:
        rows.append(("Paths.resolve()", "FAIL", str(e)))

    if paths is not None:
        policy_path = (paths.home / "agent" / "config" / "policy.json").resolve()
        try:
            policy = Policy.load(str(policy_path))
            rows.append(("Policy.load()", "PASS", str(policy_path)))
        except Exception as e:
            rows.append(("Policy.load()", "FAIL", str(e)))

    if paths is not None:
        workspace_exists = paths.workspace.exists()
        rows.append(("Workspace path", "PASS" if workspace_exists else "FAIL", str(paths.workspace)))
        write_ok = os.access(paths.workspace, os.W_OK)
        rows.append(("Workspace writable", "PASS" if write_ok else "FAIL", "yes" if write_ok else "no"))
        read_ok = os.access(paths.workspace, os.R_OK)
        rows.append(("Workspace readable", "PASS" if read_ok else "FAIL", "yes" if read_ok else "no"))

    git_path = shutil.which("git")
    rows.append(("git binary", "PASS" if git_path else "WARN", git_path or "Not found"))

    try:
        host = socket.gethostbyname("api.openai.com")
        rows.append(("DNS api.openai.com", "PASS", host))
    except Exception as e:
        rows.append(("DNS api.openai.com", "WARN", str(e)))

    if policy is not None:
        rows.append(("Execution mode", "PASS", policy.execution_mode()))
        rows.append(("Max completion tokens", "PASS", str(policy.max_completion_tokens())))
        rows.append(("Max memory chars", "PASS", str(policy.max_memory_chars())))

    table = Table(title="CAD Guardian Doctor Report")
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail", overflow="fold")

    passes = warns = fails = 0
    for name, status, detail in rows:
        if status == "PASS":
            passes += 1
            status_fmt = "[green]PASS[/green]"
        elif status == "WARN":
            warns += 1
            status_fmt = "[yellow]WARN[/yellow]"
        else:
            fails += 1
            status_fmt = "[red]FAIL[/red]"
        table.add_row(name, status_fmt, detail)

    console.print(table)
    console.print(
        Panel(
            f"checks={len(rows)} | pass={passes} | warn={warns} | fail={fails}\n"
            "Tip: Resolve FAIL first, then WARN for best user experience.",
            title="Doctor Summary",
            expand=False,
        )
    )


def _run_snapshot_tests() -> None:
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
    _print_cli_notice(
        title=title,
        level=level,
        message=f"Report saved: {report_file}",
        help_line="Review the report for exact screen snapshots and assertion details.",
    )

    opened = _open_for_review(report_file)
    if not opened:
        preview = _cap_chars(report_file.read_text(encoding="utf-8", errors="ignore"), 3000)
        console.print(
            Panel(
                preview,
                title="Report Preview (open unavailable)",
                expand=False,
            )
        )

    if proc.returncode != 0:
        raise SystemExit(1)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """CAD Guardian CLI."""
    if ctx.invoked_subcommand is not None:
        return
    _print_cli_notice(
        title="Command Required",
        level="warning",
        message="Select a command to continue.",
        usage_line='cg run "<prompt>" [--full-output]  (or: cg ask "<question>")',
        help_line="Run cg --help to see available commands and options.",
        example_line='cg run "summarize workspace"',
    )
    raise SystemExit(1)


@app.command("run")
def run(
    prompt: str = typer.Argument(..., help="Prompt to run."),
    full_output: bool = typer.Option(False, "--full-output", help="Disable output truncation for answer/stdout/stderr."),
):
    """Run CAD Guardian Agent with a prompt."""
    _run_once(prompt, full_output=full_output)


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="Question about the current project state."),
    full_output: bool = typer.Option(False, "--full-output", help="Disable answer truncation."),
    context: bool = typer.Option(False, "--context", help="Show the context payload sent to the model."),
):
    """Read-only Q&A over current source/workspace state."""
    _ask_once(question, full_output=full_output, context=context)


@app.command("doctor")
def doctor():
    """Run onboarding diagnostics and environment checks."""
    _doctor_once()


@app.command("snapshot-tests")
def snapshot_tests():
    """Run CLI snapshot tests, save report in workspace, and open it."""
    _run_snapshot_tests()


def cli() -> None:
    if len(sys.argv) == 2 and sys.argv[1] in {"--help", "-h"}:
        _print_full_help()
        return
    try:
        app(standalone_mode=False)
    except click.exceptions.UsageError as e:
        msg = str(e)
        m = re.search(r"No such command '([^']+)'\.", msg)
        if m:
            cmd = m.group(1)
            _print_cli_notice(
                title=f"Unknown Command: {cmd}",
                level="error",
                message=msg,
                help_line="Run cg --help to see available commands and options.",
                example_line='cg run "summarize workspace"',
            )
            raise SystemExit(2)
        _print_cli_notice(
            title="Command Usage Error",
            level="error",
            message=msg,
            help_line="Run cg --help to see available commands and options.",
        )
        raise SystemExit(2)
    except click.exceptions.Exit as e:
        raise SystemExit(e.exit_code)


if __name__ == "__main__":
    cli()
