from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import typer

from .eval_harness import run_core_eval, save_eval_report
from .inspect_ops import loc_once, open_for_review, open_target, outputs_once, show_folder_once, structure_once, workspace_once
from .paths import Paths
from .plugins import load_plugins, plugin_enabled
from .policy import Policy
from .telemetry import append_event, read_events, summarize_events, write_summary_csv, write_summary_json
from .tool_registry import list_tools
from cg_utils import cap_chars


def policy_file(paths: Paths) -> Path:
    return (paths.agent_root / "config" / "policy.json").resolve()


def policy_profiles_dir(paths: Paths) -> Path:
    return (paths.agent_root / "config" / "policy.profiles").resolve()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def detect_active_policy_tier(paths: Paths) -> str:
    current_path = policy_file(paths)
    profiles_dir = policy_profiles_dir(paths)
    if not current_path.exists() or not profiles_dir.exists():
        return "custom"
    try:
        current = load_json(current_path)
    except Exception:
        return "custom"
    for p in sorted(profiles_dir.glob("*.json")):
        try:
            candidate = load_json(p)
        except Exception:
            continue
        if candidate == current:
            return p.stem
    return "custom"


def policy_summary_line(data: dict[str, Any]) -> str:
    limits = data.get("execution_limits") or {}
    routing = data.get("routing_controls") or {}
    return (
        f"model={limits.get('llm_model', 'gpt-4o-mini')} | "
        f"tokens={limits.get('max_completion_tokens', 'n/a')} | "
        f"memory_items={limits.get('max_memory_items', 'n/a')} | "
        f"context_chars={limits.get('max_context_chars', 'n/a')} | "
        f"mode={limits.get('execution_mode', 'n/a')} | "
        f"actions={limits.get('max_actions_per_run', 'n/a')} | "
        f"threshold={routing.get('deterministic_confidence_threshold', 'n/a')}"
    )


def policy_expectation_line(tier: str, data: dict[str, Any]) -> str:
    t = (tier or "").strip().lower()
    if t == "cheap":
        return "Lowest-cost mode. Best for quick inspect/count/list tasks; limited depth and shorter answers."
    if t == "base":
        return "Balanced daily mode. Stronger reasoning/refactors with controlled spend and moderate throughput."
    if t == "max":
        return "Power mode for deep analysis, larger plans, and heavy refactors. Highest cost tier."
    limits = data.get("execution_limits") or {}
    model = str(limits.get("llm_model", "gpt-4o-mini"))
    return f"Custom profile. Review limits before use (model={model})."


def run_snapshot_tests(*, console, print_cli_notice, print_section, log_event: Callable[[dict[str, Any]], None], log_event_enabled: bool = True) -> None:
    started = time.perf_counter()
    paths = Paths.resolve()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = (paths.workspace / "reports" / "ui-snapshots" / run_id).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "snapshot-test-report.txt"

    cmd = [sys.executable, "-m", "unittest", "-v", "tests.test_cli_snapshots"]
    proc = subprocess.run(cmd, cwd=str((paths.agent_root / "core").resolve()), capture_output=True, text=True)
    body = [
        "CAD Guardian Snapshot Test Report",
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
    print_cli_notice(console, title=title, level=level, message=f"Report saved: {report_file}", help_line="Review the report for exact screen snapshots and assertion details.")

    opened = open_for_review(report_file)
    if not opened:
        preview = cap_chars(report_file.read_text(encoding="utf-8", errors="ignore"), 3000)
        print_section(console, title="Report Preview (open unavailable)", body=preview)

    if log_event_enabled:
        log_event(
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
            }
        )

    if proc.returncode != 0:
        raise SystemExit(1)


def register_groups(
    *,
    policy_app: typer.Typer,
    dev_app: typer.Typer,
    inspect_app: typer.Typer,
    tasks_app: typer.Typer,
    console,
    print_cli_notice,
    print_section,
    print_kv_table,
    print_session_boundary,
    start_end_session: Callable[[str], str],
    do_setup: Callable[[bool, bool], None],
    do_status: Callable[[int], None],
    do_ask: Callable[[str, bool, bool], None],
    do_fetch_template: Callable[[str, str, int, bool], None],
    log_event_wrapper: Callable[[dict[str, Any]], None],
    select_do_mode: Callable[[str], str],
    decide_route_cb: Callable[[str, Policy], object],
    file_count_probe: Callable[[str, Path], tuple[bool, str]],
) -> Callable[..., None]:
    plugins = load_plugins(Paths.resolve())

    def require_plugin(plugin_name: str, title: str):
        if plugin_enabled(plugins, plugin_name):
            return
        print_cli_notice(
            console,
            title=title,
            level="warning",
            message=f"Plugin '{plugin_name}' is disabled in config/plugins.json.",
            help_line="Set the value to true and rerun if you want this feature.",
        )
        raise SystemExit(2)
    @tasks_app.command("list")
    def tasks_list():
        require_plugin("tasks", "Tasks Disabled")
        print_section(console, title="Task Templates", body=(
            "starter-check: Run setup flow and health checks\n"
            "workspace-overview: Show files and summarize workspace via ask\n"
            "project-faq: Ask architecture/policy FAQ\n"
            "health-report: Generate metrics and status summary\n"
            "download-drive-folder: Prompt for Drive folder link and fetch into workspace"
        ))

    @tasks_app.command("run")
    def tasks_run(name: str = typer.Argument(..., help="Template name from `cg tasks list`.")):
        require_plugin("tasks", "Tasks Disabled")
        n = (name or "").strip().lower()
        if n == "starter-check":
            do_setup(True, True)
            return
        if n == "workspace-overview":
            workspace_once(console, None)
            do_ask("Summarize what is in my workspace and what I can do next.", False, False)
            return
        if n == "project-faq":
            do_ask("What does this app do, what are limits, and what commands should I use next?", False, False)
            return
        if n == "health-report":
            dev_metrics(fmt="json", limit=2000)
            do_status(200)
            return
        if n == "download-drive-folder":
            link = typer.prompt("Google Drive folder link").strip()
            folder = typer.prompt("Folder name in workspace/downloads").strip()
            do_fetch_template(link, folder, 3, True)
            return
        print_cli_notice(console, title="Unknown Task Template", level="error", message=f"Unsupported template: {name}", help_line="Run cg tasks list to see valid templates.")
        raise SystemExit(2)

    @policy_app.command("list")
    def policy_list():
        paths = Paths.resolve()
        profiles_dir = policy_profiles_dir(paths)
        if not profiles_dir.exists():
            print_cli_notice(console, title="Policy Profiles Missing", level="error", message=f"Directory not found: {profiles_dir}", help_line="Create config/policy.profiles with tier JSON files.")
            raise SystemExit(1)
        active = detect_active_policy_tier(paths)
        lines: list[str] = []
        for p in sorted(profiles_dir.glob("*.json")):
            try:
                data = load_json(p)
            except Exception as e:
                lines.append(f"{p.stem}: invalid profile ({e})")
                continue
            marker = " (active)" if p.stem == active else ""
            lines.append(f"{p.stem}{marker}: {policy_summary_line(data)}")
            lines.append(f"  expectation: {policy_expectation_line(p.stem, data)}")
        if not lines:
            lines = ["No profile JSON files found."]
        print_section(console, title="Policy Profiles", body="\n".join(lines))

    @policy_app.command("show")
    def policy_show():
        paths = Paths.resolve()
        path = policy_file(paths)
        if not path.exists():
            print_cli_notice(console, title="Policy Missing", level="error", message=f"Policy file not found: {path}")
            raise SystemExit(1)
        data = load_json(path)
        tier = detect_active_policy_tier(paths)
        print_kv_table(console, title="Active Policy", rows=[("Path", str(path)), ("Tier", tier), ("Summary", policy_summary_line(data)), ("Expectation", policy_expectation_line(tier, data))])

    @policy_app.command("use")
    def policy_use(tier: str = typer.Argument(..., help="Policy tier name: max | base | cheap"), yes: bool = typer.Option(False, "--yes", help="Apply without interactive confirmation.")):
        t = (tier or "").strip().lower()
        paths = Paths.resolve()
        source = (policy_profiles_dir(paths) / f"{t}.json").resolve()
        target = policy_file(paths)
        if not source.exists():
            print_cli_notice(console, title="Unknown Policy Tier", level="error", message=f"Profile not found: {source}", help_line="Use: cg policy list")
            raise SystemExit(2)
        if not yes:
            approved = typer.confirm(f"Apply policy tier '{t}' to {target}?")
            if not approved:
                print_cli_notice(console, title="Policy Unchanged", level="warning", message="Operation cancelled by user.")
                raise SystemExit(1)
        backup = target.with_name(f"policy.backup.{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        if target.exists():
            shutil.copy2(target, backup)
        shutil.copy2(source, target)
        data = load_json(target)
        print_cli_notice(console, title="Policy Applied", level="success", message=f"Active policy set to tier '{t}'.", help_line=f"Backup saved: {backup}" if backup.exists() else "No previous policy file to backup.", example_line="cg policy show")
        print_section(console, title="Applied Limits", body=policy_summary_line(data))
        print_section(console, title="Tier Expectation", body=policy_expectation_line(t, data))

    @dev_app.command("snaps")
    def dev_snaps():
        require_plugin("snapshots", "Snapshots Disabled")
        run_id = start_end_session("dev.snaps")
        try:
            run_snapshot_tests(console=console, print_cli_notice=print_cli_notice, print_section=print_section, log_event=log_event_wrapper)
        finally:
            print_session_boundary(console, command="dev.snaps", run_id=run_id, phase="end")

    @dev_app.command("metrics")
    def dev_metrics(fmt: str = typer.Option("json", "--format", help="Summary report format: json or csv."), limit: int = typer.Option(0, "--limit", min=0, help="Optional tail limit of events (0 = all).")):
        require_plugin("metrics", "Metrics Disabled")
        f = (fmt or "json").strip().lower()
        if f not in {"json", "csv"}:
            print_cli_notice(console, title="Invalid Format", level="error", message=f"Unsupported format: {fmt}", help_line="Use --format json or --format csv.")
            raise SystemExit(2)
        paths = Paths.resolve()
        events = read_events(paths.logs_dir, limit=(limit or None))
        summary = summarize_events(events)
        out_dir = (paths.workspace / "reports" / "metrics" / datetime.now().strftime("%Y%m%d-%H%M%S")).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"metrics-summary.{f}"
        write_summary_json(out_file, summary) if f == "json" else write_summary_csv(out_file, summary)
        print_cli_notice(console, title="Metrics Report Ready", level="success", message=f"Saved: {out_file}", help_line=f"events_total={summary.get('events_total', 0)} | llm_used_rate={summary.get('llm_used_rate', 0.0)}")

    @dev_app.command("dashboard")
    def dev_dashboard(live: bool = typer.Option(True, "--live", help="Enable auto-refresh while dashboard is open."), refresh_seconds: int = typer.Option(5, "--refresh-seconds", min=1, max=60, help="Auto-refresh interval."), port: int = typer.Option(8501, "--port", min=1024, max=65535, help="Dashboard port."), event_limit: int = typer.Option(5000, "--event-limit", min=100, max=50000, help="Max telemetry events loaded.")):
        require_plugin("dashboard", "Dashboard Disabled")
        run_id = start_end_session("dev.dashboard")
        try:
            paths = Paths.resolve()
            try:
                import streamlit  # noqa: F401
            except Exception:
                print_cli_notice(console, title="Missing Dependency", level="error", message="Streamlit is not installed.", help_line="Install with: pip install streamlit")
                raise SystemExit(1)
            app_path = (paths.agent_root / "core" / "cg" / "dashboard_app.py").resolve()
            policy_path = (paths.agent_root / "config" / "policy.json").resolve()
            cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.headless", "true", "--server.port", str(port), "--", "--workspace", str(paths.workspace), "--logs-dir", str(paths.logs_dir), "--chroma-dir", str(paths.chroma_dir), "--policy", str(policy_path), "--live", "1" if live else "0", "--refresh-seconds", str(refresh_seconds), "--event-limit", str(event_limit)]
            subprocess.Popen(cmd, cwd=str(paths.agent_root))
            url = f"http://127.0.0.1:{port}"
            open_target(url)
            print_cli_notice(console, title="Dashboard Started", level="success", message=f"Live dashboard available at {url}", help_line=f"live={live} refresh_seconds={refresh_seconds} event_limit={event_limit}")
        finally:
            print_session_boundary(console, command="dev.dashboard", run_id=run_id, phase="end")

    @dev_app.command("eval")
    def dev_eval(
        suite: str = typer.Option("core", "--suite", help="Eval suite name."),
    ):
        require_plugin("eval", "Eval Disabled")
        s = (suite or "core").strip().lower()
        if s != "core":
            print_cli_notice(console, title="Invalid Eval Suite", level="error", message=f"Unsupported suite: {suite}", help_line="Use --suite core")
            raise SystemExit(2)
        paths = Paths.resolve()
        policy_path = (paths.home / "agent" / "config" / "policy.json").resolve()
        policy = Policy.load(str(policy_path))
        handlers = {t.handler_id for t in list_tools()}
        cases = run_core_eval(
            select_do_mode=select_do_mode,
            decide_route=lambda prompt: decide_route_cb(prompt, policy),
            file_count_probe=file_count_probe,
            expected_handlers=handlers,
        )
        report = save_eval_report(paths, suite="core", cases=cases)
        passed = sum(1 for c in cases if c.passed)
        level = "success" if passed == len(cases) else "warning"
        print_cli_notice(
            console,
            title="Eval Report Ready",
            level=level,
            message=f"Passed {passed}/{len(cases)} checks.",
            help_line=f"Saved: {report}",
        )
        detail = "\n".join(f"- {c.name}: {'PASS' if c.passed else 'FAIL'} ({c.detail})" for c in cases)
        print_section(console, title="Eval Cases", body=detail)

    @inspect_app.command("structure")
    def inspect_structure(depth: int = typer.Option(4, "-d", min=1, max=10, help="Tree depth (default: 4).")):
        structure_once(console, depth)

    @inspect_app.command("workspace")
    def inspect_workspace(depth: Optional[int] = typer.Option(None, "-d", min=1, max=10, help="Optional tree depth limit.")):
        workspace_once(console, depth)

    @inspect_app.command("outputs")
    def inspect_outputs(depth: Optional[int] = typer.Option(None, "-d", min=1, max=10, help="Optional tree depth limit.")):
        outputs_once(console, depth)

    @inspect_app.command("loc")
    def inspect_loc():
        loc_once(console)

    return run_snapshot_tests
