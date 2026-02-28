from __future__ import annotations

import re
import shlex
import sys
import time
import uuid

import click
import typer
from rich.console import Console

from .ui.cli_ui import (
    print_answer_path,
    print_cli_notice,
    print_full_help,
    print_kv_table,
    print_runtime_error,
    print_section,
    print_session_boundary,
    print_status_line,
    set_simple_mode,
)
from ..data.env import get_openai_api_key, load_project_dotenv
from ..data.paths import Paths
from ..inspect.inspect_ops import loc_once, outputs_once, structure_once, workspace_once
from ..observability.doctor import doctor_once
from ..observability.telemetry import read_events, summarize_events
from ..runtime.ask_engine import ask_once
from ..runtime.common import finish_event
from ..runtime.run_engine import run_once
from ..safety.policy import Policy


app = typer.Typer(add_completion=False)
inspect_app = typer.Typer(help="Inspect workspace and outputs.")
policy_app = typer.Typer(help="Inspect active policy settings.")
app.add_typer(inspect_app, name="inspect")
app.add_typer(policy_app, name="policy")

console = Console()
SESSION_ID = str(uuid.uuid4())
_LOOP_EXIT_WORDS = {"exit", "quit", ":q", "/exit", "/quit", "/q"}


def _start_session(command_name: str) -> str:
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command=command_name, run_id=run_id, phase="start")
    return run_id


def _parse_on_off(value: str) -> bool | None:
    v = (value or "").strip().lower()
    if v in {"on", "yes", "true", "1"}:
        return True
    if v in {"off", "no", "false", "0"}:
        return False
    return None


def _select_do_mode(request: str) -> str:
    q = (request or "").strip().lower()
    ask_leads = (
        "what",
        "why",
        "how",
        "who",
        "when",
        "where",
        "which",
        "can you",
        "could you",
        "explain",
        "summarize",
        "tell me",
    )
    if not q or q.endswith("?") or q.startswith(ask_leads):
        return "ask"
    return "run"


def _print_loop_help() -> None:
    print_section(
        console,
        title="Loop Help",
        body=(
            "Type a request and press Enter.\n"
            "Slash commands:\n"
            "/help               Show this help\n"
            "/mode ask|run|do    Change loop mode\n"
            "/full on|off        Toggle full output\n"
            "/ctx on|off         Toggle ask context\n"
            "/status [limit]     Show health summary\n"
            "/doctor             Run diagnostics\n"
            "/workspace          Show workspace tree\n"
            "/clear              Clear terminal\n"
            "/exit               Exit loop"
        ),
    )


def _loop_prompt(mode: str, *, full_output: bool, context: bool) -> str:
    flags: list[str] = []
    if full_output:
        flags.append("full")
    if context:
        flags.append("ctx")
    suffix = f" ({','.join(flags)})" if flags else ""
    return f"cg[{mode}{suffix}]"


def _handle_loop_control(
    raw: str,
    *,
    mode: str,
    full_output: bool,
    context: bool,
    simple: bool,
) -> tuple[str, bool, bool, bool]:
    try:
        tokens = shlex.split(raw)
    except ValueError:
        print_cli_notice(
            console,
            title="Loop Command Error",
            level="error",
            message="Could not parse control command.",
            help_line="Use /help for valid loop commands.",
        )
        return mode, full_output, context, False

    if not tokens:
        return mode, full_output, context, False

    cmd = tokens[0].lower()
    args = tokens[1:]

    if cmd in {"/help", "/h"}:
        _print_loop_help()
        return mode, full_output, context, False

    if cmd in {"/exit", "/quit", "/q"}:
        return mode, full_output, context, True

    if cmd == "/mode":
        if not args:
            print_cli_notice(console, title="Loop Mode", level="info", message=f"Current mode: {mode}")
            return mode, full_output, context, False
        wanted = str(args[0]).strip().lower()
        if wanted not in {"ask", "run", "do"}:
            print_cli_notice(console, title="Loop Command Error", level="error", message=f"Unsupported mode: {wanted}", help_line="Use /mode ask, /mode run, or /mode do.")
            return mode, full_output, context, False
        print_cli_notice(console, title="Loop Mode", level="success", message=f"Mode set to: {wanted}")
        return wanted, full_output, context, False

    if cmd in {"/full", "/ctx"}:
        current = full_output if cmd == "/full" else context
        if not args:
            key = "full output" if cmd == "/full" else "ask context"
            print_cli_notice(console, title="Loop Toggle", level="info", message=f"{key} is {'on' if current else 'off'}")
            return mode, full_output, context, False
        toggled = _parse_on_off(str(args[0]))
        if toggled is None:
            print_cli_notice(console, title="Loop Command Error", level="error", message=f"Invalid value: {args[0]}", help_line=f"Use {cmd} on or {cmd} off.")
            return mode, full_output, context, False
        if cmd == "/full":
            print_cli_notice(console, title="Loop Toggle", level="success", message=f"Full output {'enabled' if toggled else 'disabled'}.")
            return mode, toggled, context, False
        print_cli_notice(console, title="Loop Toggle", level="success", message=f"Ask context {'enabled' if toggled else 'disabled'}.")
        return mode, full_output, toggled, False

    if cmd == "/status":
        limit = 200
        if args:
            try:
                limit = max(1, min(20000, int(args[0])))
            except ValueError:
                print_cli_notice(console, title="Loop Command Error", level="error", message=f"Invalid limit: {args[0]}", help_line="Use /status 200")
                return mode, full_output, context, False
        status(limit=limit, simple=simple)
        return mode, full_output, context, False

    if cmd == "/doctor":
        doctor(verbose=False, simple=simple)
        return mode, full_output, context, False

    if cmd == "/workspace":
        workspace_once(console, None)
        return mode, full_output, context, False

    if cmd == "/clear":
        console.clear()
        return mode, full_output, context, False

    print_cli_notice(console, title="Loop Command Error", level="error", message=f"Unknown loop command: {cmd}", help_line="Use /help for valid loop commands.")
    return mode, full_output, context, False


def _run_interactive_loop(*, mode: str = "do", full_output: bool = False, context: bool = False, simple: bool = False) -> None:
    current_mode = mode if mode in {"ask", "run", "do"} else "do"
    current_full = bool(full_output)
    current_ctx = bool(context)

    _print_loop_help()
    print_cli_notice(console, title="Loop Started", level="success", message="Interactive loop is ready.", help_line="Type requests directly. Use /exit to leave.")

    while True:
        prompt_label = _loop_prompt(current_mode, full_output=current_full, context=current_ctx)
        try:
            raw = typer.prompt(prompt_label, prompt_suffix=" > ", show_default=False).strip()
        except (KeyboardInterrupt, EOFError):
            print_cli_notice(console, title="Loop Ended", level="info", message="Exited interactive loop.")
            break

        if not raw:
            continue
        if raw.lower() in _LOOP_EXIT_WORDS:
            print_cli_notice(console, title="Loop Ended", level="info", message="Exited interactive loop.")
            break

        if raw.startswith("/"):
            current_mode, current_full, current_ctx, should_exit = _handle_loop_control(
                raw,
                mode=current_mode,
                full_output=current_full,
                context=current_ctx,
                simple=simple,
            )
            if should_exit:
                print_cli_notice(console, title="Loop Ended", level="info", message="Exited interactive loop.")
                break
            continue

        try:
            if current_mode == "ask":
                ask(question=raw, full_output=current_full, context=current_ctx, simple=simple)
            elif current_mode == "run":
                run(prompt=raw, full_output=current_full, simple=simple)
            else:
                do(request=raw, full_output=current_full, context=current_ctx, simple=simple)
        except Exception as e:
            print_runtime_error(console, "Loop Command Error", e, "Use /help for loop commands.")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    """CAD Guardian Core CLI."""
    set_simple_mode(simple)
    if ctx.invoked_subcommand is not None:
        return
    if sys.stdin.isatty():
        _run_interactive_loop(mode="do", full_output=False, context=False, simple=simple)
        raise SystemExit(0)
    print_cli_notice(
        console,
        title="Command Required",
        level="warning",
        message="Select a command to continue.",
        usage_line='cg do "<request>"',
        help_line="Run cg loop for interactive mode, or cg --help for options.",
        example_line='cg do "summarize project status"',
    )
    raise SystemExit(1)


@app.command("run")
def run(
    prompt: str = typer.Argument(..., help="Prompt to run."),
    full_output: bool = typer.Option(False, "--full", help="Disable truncation for answer/stdout/stderr."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    run_once(
        prompt=prompt,
        full_output=full_output,
        console=console,
        print_session_boundary=print_session_boundary,
        print_kv_table=print_kv_table,
        print_section=print_section,
        print_status_line=print_status_line,
        print_answer_path=print_answer_path,
        print_cli_notice=print_cli_notice,
        print_runtime_error=print_runtime_error,
        session_id=SESSION_ID,
    )


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="Question about current project/workspace state."),
    full_output: bool = typer.Option(False, "--full", help="Disable answer truncation."),
    context: bool = typer.Option(False, "--ctx", help="Show context payload sent to model."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    ask_once(
        question=question,
        full_output=full_output,
        context=context,
        console=console,
        print_session_boundary=print_session_boundary,
        print_kv_table=print_kv_table,
        print_section=print_section,
        print_answer_path=print_answer_path,
        print_status_line=print_status_line,
        print_runtime_error=print_runtime_error,
        session_id=SESSION_ID,
    )


@app.command("do")
def do(
    request: str = typer.Argument(..., help="Natural request. Auto-routes to ask or run."),
    full_output: bool = typer.Option(False, "--full", help="Disable truncation."),
    context: bool = typer.Option(False, "--ctx", help="Show ask context when ask route is selected."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    mode = _select_do_mode(request)
    print_cli_notice(console, title="Auto Route", level="info", message=f"Selected mode: {mode}", help_line="Question-like text routes to ask; action text routes to run.")
    if mode == "ask":
        ask(question=request, full_output=full_output, context=context)
    else:
        run(prompt=request, full_output=full_output)


@app.command("loop")
def loop(
    mode: str = typer.Option("do", "--mode", help="Loop mode: do | ask | run"),
    full_output: bool = typer.Option(False, "--full", help="Default full output for loop requests."),
    context: bool = typer.Option(False, "--ctx", help="Default ask context for loop requests."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    _run_interactive_loop(mode=mode, full_output=full_output, context=context, simple=simple)


@app.command("status")
def status(
    limit: int = typer.Option(200, "--limit", min=1, max=20000, help="Telemetry events to analyze."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    paths = Paths.resolve()
    events = read_events(paths.logs_dir, limit=limit)
    summary = summarize_events(events)
    by_outcome = summary.get("by_outcome") or {}
    success = int(by_outcome.get("success", 0) or 0)
    total = int(summary.get("events_total", 0) or 0)
    success_rate = round((success / max(1, total)) * 100.0, 1) if total else 0.0

    print_kv_table(
        console,
        title="CAD Guardian Status",
        rows=[
            ("Events Analyzed", str(total)),
            ("Success Rate", f"{success_rate}%"),
            ("LLM Usage Rate", f"{round(float(summary.get('llm_used_rate', 0.0) or 0.0) * 100.0, 1)}%"),
            ("Top Command", max((summary.get("by_command") or {"n/a": 0}).items(), key=lambda kv: kv[1])[0]),
        ],
    )


@app.command("doctor")
def doctor(
    verbose: bool = typer.Option(False, "--verbose", help="Show expanded diagnostics."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    run_id = _start_session("doctor")
    started = time.perf_counter()
    outcome = "success"
    err_type = ""
    err_msg = ""
    summary = {"checks": 0, "warn": 0, "fail": 0}
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
            finish_event(
                paths=Paths.resolve(),
                started=started,
                session_id=SESSION_ID,
                command="doctor",
                route_mode="n/a",
                outcome=outcome,
                llm_used=False,
                executed_steps=0,
                error_type=err_type,
                error_message=err_msg,
            )
        except Exception:
            pass
        print_session_boundary(console, command="doctor", run_id=run_id, phase="end")


@app.command("setup")
def setup(
    run_doctor: bool = typer.Option(True, "--doctor/--no-doctor", help="Run doctor checks during setup."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    run_id = _start_session("setup")
    try:
        load_project_dotenv()
        paths = Paths.resolve()
        api_key = get_openai_api_key()
        print_kv_table(
            console,
            title="Setup Check",
            rows=[
                ("OPENAI_API_KEY", "set" if api_key else "missing"),
                ("Workspace", str(paths.workspace)),
                ("Policy", str((paths.home / "agent" / "config" / "policy.json").resolve())),
            ],
        )
        if run_doctor:
            doctor(verbose=False)
        print_section(console, title="Next Steps", body='1) cg do "summarize this repository"\n2) cg ask "what should I do next?"\n3) cg status --limit 100')
    finally:
        print_session_boundary(console, command="setup", run_id=run_id, phase="end")


@policy_app.command("show")
def policy_show() -> None:
    paths = Paths.resolve()
    policy = Policy.load(str((paths.home / "agent" / "config" / "policy.json").resolve()))
    print_kv_table(
        console,
        title="Active Policy",
        rows=[
            ("command_allowlist", str(len(policy.command_allowlist))),
            ("command_denylist", str(len(policy.command_denylist))),
            ("allowed_write_roots", str(len(policy.allowed_write_roots))),
            ("allowed_read_roots", str(len(policy.allowed_read_roots))),
            ("denied_paths", str(len(policy.denied_paths))),
            ("allow_outbound_http", str(policy.allow_outbound_http())),
            ("allow_domains", ", ".join(policy.allow_domains()) or "(none)"),
            ("execution_mode", policy.execution_mode()),
            ("llm_model", policy.llm_model()),
        ],
    )


@inspect_app.command("structure")
def inspect_structure(depth: int = typer.Option(4, "-d", min=1, max=10, help="Tree depth limit.")) -> None:
    structure_once(console, depth)


@inspect_app.command("workspace")
def inspect_workspace(depth: int | None = typer.Option(None, "-d", min=1, max=10, help="Optional tree depth limit.")) -> None:
    workspace_once(console, depth)


@inspect_app.command("outputs")
def inspect_outputs(depth: int | None = typer.Option(None, "-d", min=1, max=10, help="Optional tree depth limit.")) -> None:
    outputs_once(console, depth)


@inspect_app.command("loc")
def inspect_loc() -> None:
    loc_once(console)


def _usage_error_notice_fields(message: str) -> dict[str, str | None]:
    msg = str(message or "").strip()
    fields: dict[str, str | None] = {
        "message": msg,
        "usage_line": None,
        "help_line": "Run cg loop for interactive use, or cg --help for valid command syntax.",
        "example_line": 'cg do "show files in workspace"',
    }

    extra = re.search(r"unexpected extra arguments? \((.+)\)", msg, re.IGNORECASE)
    if extra:
        spill = extra.group(1).strip()
        fields["message"] = f"I found extra words outside the command input: {spill}"
        fields["usage_line"] = 'cg do "<what you want>"'
        fields["help_line"] = "Put the full request inside quotes so it is parsed as one argument."
        return fields

    missing = re.search(r"Missing argument '([^']+)'\.", msg)
    if missing:
        arg_name = missing.group(1).strip().lower()
        fields["message"] = f"The command is missing required input: {arg_name}."
        fields["usage_line"] = 'cg do "<what you want>"'
        fields["help_line"] = "Add your request in quotes right after the command."
        return fields

    bad_option = re.search(r"No such option:\s*(--[A-Za-z0-9_-]+)", msg)
    if bad_option:
        flag = bad_option.group(1)
        fields["message"] = f"That flag is not valid here: {flag}"
        fields["usage_line"] = 'cg ask "<question>" [--full] [--ctx]'
        fields["help_line"] = "Use only flags shown in help for this command."
        fields["example_line"] = 'cg ask "what changed?" --full'
        return fields

    return fields


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
                help_line="Run cg --help to see available commands.",
                example_line='cg do "show files"',
            )
            raise SystemExit(2)
        fields = _usage_error_notice_fields(msg)
        print_cli_notice(
            console,
            title="Command Usage Error",
            level="error",
            message=str(fields["message"] or msg),
            usage_line=fields["usage_line"],
            help_line=fields["help_line"],
            example_line=fields["example_line"],
        )
        raise SystemExit(2)
    except click.exceptions.Exit as e:
        raise SystemExit(e.exit_code)


if __name__ == "__main__":
    cli()
