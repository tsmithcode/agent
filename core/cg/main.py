from __future__ import annotations

import os
import re
import shutil
import sys
import time
import uuid
from datetime import datetime

import click
import typer
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
    set_simple_mode,
)
from .command_groups import (
    detect_active_policy_tier,
    policy_file,
    policy_profiles_dir,
    register_groups,
)
from .app_flow import enforce_runtime_manifest, interactive_start_menu, select_do_mode, status_recommendations
from .doctor import doctor_once
from .env import get_openai_api_key, load_project_dotenv
from .gdrive_fetch import download_public_folder
from .inspect_ops import extract_depth, open_target, show_folder_once, structure_once, workspace_once, outputs_once
from .llm import LLM
from .memory import LongTermMemory
from .paths import Paths
from .policy import Policy
from .router import decide_route
from .runtime_ask import ask_once, ask_workspace_file_count
from .runtime_common import finish_event
from .runtime_run import run_once, _run_with_spinner
from .telemetry import read_events, summarize_events

app = typer.Typer(add_completion=False)
inspect_app = typer.Typer(help="Inspect project structure, workspace files, and output folders.")
dev_app = typer.Typer(help="Developer-only maintenance and QA commands.")
policy_app = typer.Typer(help="Manage policy profiles for cost/quality tiers.")
tasks_app = typer.Typer(help="Beginner-friendly task templates.")
console = Console()
SESSION_ID = str(uuid.uuid4())

app.add_typer(inspect_app, name="inspect")
app.add_typer(dev_app, name="dev")
app.add_typer(policy_app, name="policy")
app.add_typer(tasks_app, name="tasks")

# Set by register_groups; used by run deterministic handler for dev_snaps.
_SNAPSHOT_RUNNER = None

def _start_end_session(command_name: str):
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command=command_name, run_id=run_id, phase="start")
    return run_id


# Backward-compatible wrappers kept for tests and external imports.
def _print_cli_notice(
    *,
    title: str,
    level: str,
    message: str,
    usage_line: str | None = None,
    help_line: str | None = None,
    example_line: str | None = None,
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

def _run_once(prompt: str, *, full_output: bool = False) -> None:
    run(prompt=prompt, full_output=full_output, simple=False)

def _ask_once(question: str, *, full_output: bool = False, context: bool = False) -> None:
    ask(question=question, full_output=full_output, context=context, simple=False)

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    """CAD Guardian CLI."""
    set_simple_mode(simple)
    if ctx.invoked_subcommand is not None:
        enforce_runtime_manifest(app=app, print_section=print_section, print_cli_notice=print_cli_notice, console=console)
        return
    print_cli_notice(
        console,
        title="Command Required",
        level="warning",
        message="Select a command to continue.",
        usage_line='cg do "<request>"  (or: cg run "<prompt>")',
        help_line="Run cg guide --mode starter for guided onboarding, or cg --help for full options.",
        example_line='cg do "show files"',
    )
    interactive_start_menu(
        is_tty=sys.stdin.isatty(),
        print_section=print_section,
        console=console,
        guide_fn=lambda: guide(mode="starter"),
        ask_fn=lambda q: ask_once(question=q, full_output=False, context=False, console=console, print_session_boundary=print_session_boundary, print_kv_table=print_kv_table, print_section=print_section, print_answer_path=print_answer_path, print_status_line=print_status_line, print_runtime_error=print_runtime_error, session_id=SESSION_ID, llm_cls=LLM, memory_cls=LongTermMemory),
        workspace_fn=lambda: workspace_once(console, None),
    )
    raise SystemExit(1)

@app.command("run")
def run(
    prompt: str = typer.Argument(..., help="Prompt to run."),
    full_output: bool = typer.Option(False, "--full", help="Disable output truncation for answer/stdout/stderr."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    run_once(
        prompt=prompt,
        full_output=full_output,
        console=console,
        print_session_boundary=print_session_boundary,
        print_kv_table=print_kv_table,
        print_route_decision=print_route_decision,
        print_section=print_section,
        print_status_line=print_status_line,
        print_answer_path=print_answer_path,
        print_cli_notice=print_cli_notice,
        print_runtime_error=print_runtime_error,
        session_id=SESSION_ID,
        workspace_once=lambda d: workspace_once(console, d),
        outputs_once=lambda d: outputs_once(console, d),
        structure_once=lambda d: structure_once(console, d),
        extract_depth=extract_depth,
        snapshot_runner=_SNAPSHOT_RUNNER,
        llm_cls=LLM,
        memory_cls=LongTermMemory,
    )

@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="Question about the current project state."),
    full_output: bool = typer.Option(False, "--full", help="Disable answer truncation."),
    context: bool = typer.Option(False, "--ctx", help="Show the context payload sent to the model."),
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
        llm_cls=LLM,
        memory_cls=LongTermMemory,
    )

@app.command("doctor")
def doctor(
    verbose: bool = typer.Option(False, "--verbose", help="Show full path inventory and expanded diagnostics."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    run_id = _start_end_session("doctor")
    started = time.perf_counter()
    outcome = "success"
    err_type = ""
    err_msg = ""
    summary: dict[str, int] = {"checks": 0, "pass": 0, "warn": 0, "fail": 0}
    try:
        summary = doctor_once(console, verbose=verbose, app=app)
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
            finish_event(
                paths=paths,
                started=started,
                session_id=SESSION_ID,
                command="doctor",
                route_mode="n/a",
                handler_id="",
                outcome=outcome,
                llm_used=False,
                actionable_steps=0,
                executed_steps=0,
                error_type=err_type,
                error_message=err_msg,
                extra={
                    "doctor_warn": int(summary.get("warn", 0)),
                    "doctor_fail": int(summary.get("fail", 0)),
                    "doctor_checks": int(summary.get("checks", 0)),
                    "verbose": bool(verbose),
                },
            )
        except Exception:
            pass
        print_session_boundary(console, command="doctor", run_id=run_id, phase="end")

@app.command("guide")
def guide(
    mode: str = typer.Option("starter", "--mode", help="Guide mode: starter | power"),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    m = (mode or "starter").strip().lower()
    if m not in {"starter", "power"}:
        print_cli_notice(console, title="Invalid Guide Mode", level="error", message=f"Unsupported mode: {mode}", help_line="Use --mode starter or --mode power.")
        raise SystemExit(2)
    if m == "starter":
        print_section(console, title="Starter Guide", body=(
            "1) Health check: cg doctor\n"
            "2) Set balanced tier: cg policy use base --yes\n"
            "3) See workspace files: cg inspect workspace\n"
            "4) Ask safely: cg ask \"What can you do with this workspace?\"\n"
            "5) Run direct action: cg do \"show files\"\n"
            "6) Review success loop: cg status --limit 100"
        ))
        return
    print_section(console, title="Power Guide", body=(
        "1) Set workload tier: cg policy use max --yes (or base)\n"
        "2) Ingest data: cg fetch \"<drive-folder-link>\" --folder incoming\n"
        "3) Inspect fast: cg inspect outputs and cg inspect workspace\n"
        "4) Plan/apply batches: cg run \"... confirm:yes\"\n"
        "5) Export telemetry: cg dev metrics --format json --limit 5000\n"
        "6) Live observability: cg dev dashboard --live --refresh-seconds 5"
    ))

@app.command("status")
def status(
    limit: int = typer.Option(200, "--limit", min=1, max=20000, help="Telemetry events to analyze."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    paths = Paths.resolve()
    events = read_events(paths.logs_dir, limit=limit)
    summary = summarize_events(events)
    total = int(summary.get("events_total", 0) or 0)
    by_outcome = summary.get("by_outcome") or {}
    by_command = summary.get("by_command") or {}
    success = int(by_outcome.get("success", 0) or 0)
    fail_like = sum(int(v or 0) for k, v in by_outcome.items() if k in {"error", "fail", "policy_violation", "command_failed"})
    success_rate = round((success / max(1, total)) * 100.0, 1) if total else 0.0
    llm_rate = round(float(summary.get("llm_used_rate", 0.0) or 0.0) * 100.0, 1)
    top_cmd = max(by_command.items(), key=lambda kv: kv[1])[0] if by_command else "n/a"

    print_kv_table(console, title="CAD Guardian Status", rows=[("Events Analyzed", str(total)), ("Success Rate", f"{success_rate}%"), ("Failure-like Outcomes", str(fail_like)), ("LLM Usage Rate", f"{llm_rate}%"), ("Top Command", top_cmd)])
    print_section(console, title="Recommendations", body="\n".join(f"- {x}" for x in status_recommendations(summary)))

@app.command("do")
def do(
    request: str = typer.Argument(..., help="Natural request. Auto-routes to ask or run."),
    full_output: bool = typer.Option(False, "--full", help="Disable truncation."),
    context: bool = typer.Option(False, "--ctx", help="Show ask context when ask route is chosen."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    mode = select_do_mode(request)
    print_cli_notice(console, title="Auto Route", level="info", message=f"Selected mode: {mode}", help_line="Questions route to ask; action requests route to run.")
    if mode == "ask":
        ask(question=request, full_output=full_output, context=context)
    else:
        run(prompt=request, full_output=full_output)

@app.command("setup")
def setup(
    apply_base: bool = typer.Option(True, "--apply-base/--no-apply-base", help="Set policy tier to base during setup."),
    run_doctor: bool = typer.Option(True, "--doctor/--no-doctor", help="Run doctor checks during setup."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    run_id = _start_end_session("setup")
    try:
        load_project_dotenv()
        paths = Paths.resolve()
        api_key = get_openai_api_key()
        tier = detect_active_policy_tier(paths)
        print_kv_table(console, title="Setup Check", rows=[("OPENAI_API_KEY", "set" if api_key else "missing"), ("Workspace", str(paths.workspace)), ("Policy Tier", tier)])
        if apply_base and tier != "base":
            base_profile = policy_profiles_dir(paths) / "base.json"
            if base_profile.exists():
                shutil.copy2(policy_file(paths), policy_file(paths).with_name(f"policy.backup.setup.{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"))
                shutil.copy2(base_profile, policy_file(paths))
                print_cli_notice(console, title="Policy Baseline Applied", level="success", message="Set active policy to base tier for balanced default behavior.")
        if run_doctor:
            doctor(verbose=False)
        print_section(console, title="Next Steps", body="1) cg guide --mode starter\n2) cg do \"show files\"\n3) cg status --limit 100")
    finally:
        print_session_boundary(console, command="setup", run_id=run_id, phase="end")

@app.command("fetch")
def fetch(
    link: str = typer.Argument(..., help="Google Drive folder link to download."),
    folder: str = typer.Option("", "--folder", "-f", help="Destination folder name under workspace/downloads."),
    depth: int = typer.Option(3, "-d", min=1, max=8, help="Tree depth to display after download."),
    open_gui: bool = typer.Option(True, "--open/--no-open", help="Try opening folder in GUI when not in SSH."),
    simple: bool = typer.Option(False, "--simple", help="Use beginner-friendly wording."),
):
    set_simple_mode(simple)
    run_id = _start_end_session("fetch")
    try:
        if "drive.google.com" not in (link or "").lower():
            print_cli_notice(console, title="Invalid Link", level="error", message="Only Google Drive links are supported by this command.", help_line="Provide a link like: https://drive.google.com/drive/folders/<id>")
            raise SystemExit(2)

        desired = (folder or "").strip() or typer.prompt("Folder name in workspace/downloads").strip()
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", desired).strip("-.") or "downloaded-folder"

        paths = Paths.resolve()
        downloads_root = (paths.workspace / "downloads").resolve()
        downloads_root.mkdir(parents=True, exist_ok=True)
        target = downloads_root / safe
        if target.exists():
            target = downloads_root / f"{safe}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        target.mkdir(parents=True, exist_ok=True)

        print_cli_notice(console, title="Download Started", level="info", message=f"Fetching files into: {target}", help_line="This may take time for large folders.")
        result = _run_with_spinner(console, "Downloading files from Google Drive...", lambda: download_public_folder(link, target))

        file_count = int(getattr(result, "downloaded_files", 0) or 0)
        partial_hint = ""
        if bool(getattr(result, "partial", False)):
            reason = str(getattr(result, "partial_reason", "") or "Large folder may be partially listed.")
            partial_hint = f" | possible_partial=true ({reason})"
        print_cli_notice(console, title="Download Complete", level="success", message=f"Saved {file_count} file(s) to {target}", help_line=f"Folder view is shown below for console/SSH workflows.{partial_hint}")

        if bool(getattr(result, "partial", False)):
            print_cli_notice(console, title="Partial Download Advice", level="warning", message="Google Drive appears to have truncated folder listing.", help_line="For complete results, zip the folder in Drive and fetch the single archive file, or split into smaller subfolders.")

        show_folder_once(console, target, depth=depth, title="Downloaded Folder")

        is_ssh = bool(os.getenv("SSH_CONNECTION") or os.getenv("SSH_TTY"))
        if open_gui and not is_ssh:
            opened = open_target(str(target))
            if opened:
                print_cli_notice(console, title="Opened Folder", level="success", message=f"Opened folder in system file browser: {target}")
            else:
                print_cli_notice(console, title="Open Folder Fallback", level="warning", message=f"Could not open GUI browser. Folder path: {target}")
        else:
            print_section(console, title="Console Folder Path", body=f"Use this folder path directly:\n{target}")
    except Exception as e:
        print_runtime_error(console, "Download Error", e, "Google Drive folder download failed. Check sharing permissions and network/DNS.")
        raise
    finally:
        print_session_boundary(console, command="fetch", run_id=run_id, phase="end")

# Register policy/dev/inspect/tasks command groups.
_SNAPSHOT_RUNNER = register_groups(
    policy_app=policy_app,
    dev_app=dev_app,
    inspect_app=inspect_app,
    tasks_app=tasks_app,
    console=console,
    print_cli_notice=print_cli_notice,
    print_section=print_section,
    print_kv_table=print_kv_table,
    print_session_boundary=print_session_boundary,
    start_end_session=_start_end_session,
    do_setup=lambda apply_base, run_doctor: setup(apply_base=apply_base, run_doctor=run_doctor),
    do_status=lambda limit: status(limit=limit),
    do_ask=lambda q, full, ctx: ask(question=q, full_output=full, context=ctx),
    do_fetch_template=lambda link, folder, depth, open_gui: fetch(link=link, folder=folder, depth=depth, open_gui=open_gui),
    select_do_mode=select_do_mode,
    decide_route_cb=decide_route,
    file_count_probe=ask_workspace_file_count,
    log_event_wrapper=lambda event: finish_event(
        paths=Paths.resolve(),
        started=time.perf_counter(),
        session_id=SESSION_ID,
        command=event.get("command", "unknown"),
        route_mode=event.get("route_mode", "n/a"),
        handler_id=event.get("handler_id", ""),
        outcome=event.get("outcome", "unknown"),
        llm_used=bool(event.get("llm_used", False)),
        actionable_steps=int(event.get("actionable_steps", 0) or 0),
        executed_steps=int(event.get("executed_steps", 0) or 0),
        error_type=str(event.get("error_type", "") or ""),
        error_message=str(event.get("error_message", "") or ""),
    ),
)

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
                help_line="Run cg guide --mode starter for guided flow, or cg --help for full options.",
                example_line='cg do "show files"',
            )
            raise SystemExit(2)
        print_cli_notice(console, title="Command Usage Error", level="error", message=msg, help_line="CLI argument parsing error. Run cg --help for valid syntax.")
        raise SystemExit(2)
    except click.exceptions.Exit as e:
        raise SystemExit(e.exit_code)

if __name__ == "__main__":
    cli()
