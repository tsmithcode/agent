from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
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
    skip_dirs = {".git", "venv", "__pycache__"}
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
            out = _cap_chars(_cap_lines(res.stdout, stdout_line_cap, full_output=full_output), max_output_chars, full_output=full_output)
            console.print(Panel(out, title="stdout", expand=False))
        if show_output and res.stderr.strip():
            err = _cap_chars(_cap_lines(res.stderr, stderr_line_cap, full_output=full_output), max_output_chars, full_output=full_output)
            console.print(Panel(err, title="stderr", expand=False))
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
            f"retrieved={retrieved_count} | sent_chars={len(retrieved_text)}",
            title="CAD Guardian Agent",
            expand=False,
        )
    )

    llm = LLM(api_key=api_key)
    try:
        reply = llm.ask(prompt, retrieved_text, max_completion_tokens=max_completion_tokens)
    except Exception as e:
        console.print(f"[red]LLM ERROR[/red] {e}")
        return

    if len(reply.plan) > max_steps_per_plan:
        reply.plan = reply.plan[:max_steps_per_plan]
        console.print(f"[yellow]Plan truncated to {max_steps_per_plan} steps.[/yellow]")

    step_lines = [f"{i}. {_step_preview_text(s)}" for i, s in enumerate(reply.plan, 1)] or ["(no plan steps returned)"]
    console.print(Panel("\n".join(step_lines), title="Execution Plan", expand=False))

    answer_display = _cap_lines(_cap_chars(reply.answer, max_response_chars, full_output=full_output), max_summary_lines, full_output=full_output)
    console.print(Panel(answer_display, title="Answer", expand=False))

    memory.add(
        mem_id=str(uuid.uuid4()),
        text=_cap_chars(f"USER: {prompt}\nASSISTANT: {reply.answer}", 4000),
        metadata={"ts_utc": datetime.now(timezone.utc).isoformat(), "kind": "interaction"},
    )

    actionable = _actionable_steps(reply.plan)
    if not actionable:
        console.print("[yellow]No actionable plan steps to execute.[/yellow]")
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
                console.print("[yellow]Stopping execution after failed command.[/yellow]")
                break
        except PolicyViolation as e:
            console.print(f"[red]POLICY VIOLATION[/red] {e}")
            break
        except Exception as e:
            console.print(f"[red]ERROR[/red] {e}")
            break

    if mode == "single_step" and len(actionable) > 1:
        console.print("[dim]Stopped after 1 actionable step (policy: execution_mode=single_step).[/dim]")


def _ask_once(question: str, *, full_output: bool = False) -> None:
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

    retrieved_text, retrieved_count = _memory_context(memory, question, policy)
    snapshot_text = _collect_runtime_snapshot(paths, policy)
    context_text = f"Memory context:\n{retrieved_text}\n\nRuntime snapshot:\n{snapshot_text}"

    console.print(
        Panel(
            f"[bold]Question[/bold]\n{question}\n\n[bold]Context[/bold]\n"
            f"memory_items={retrieved_count} | context_chars={len(context_text)}",
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
        console.print(f"[red]LLM ERROR[/red] {e}")
        return

    answer_display = _cap_lines(
        _cap_chars(reply.answer, max_response_chars, full_output=full_output),
        max_summary_lines,
        full_output=full_output,
    )
    console.print(Panel(answer_display, title="Insight Answer", expand=False))

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
):
    """Read-only Q&A over current source/workspace state."""
    _ask_once(question, full_output=full_output)


@app.command("doctor")
def doctor():
    """Run onboarding diagnostics and environment checks."""
    _doctor_once()


def cli() -> None:
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
