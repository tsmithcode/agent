from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .router import RouteDecision

_PATH_RE = re.compile(r"(?P<path>(?:~|\.{1,2}|/)[A-Za-z0-9._/\-]+|[A-Za-z0-9._-]+/[A-Za-z0-9._/\-]+)")
COLOR_RULES = {
    "section_header": "bold #a78bfa",
    "error": "bold #f87171",
    "warning": "bold #fbbf24",
    "success": "bold #34d399",
    "info": "#c4b5fd",
    "subtle": "#9ca3af",
    "text": "#f3f4f6",
}


def _resolve_path(candidate: str, *, base_dir: Path) -> Path | None:
    c = (candidate or "").strip()
    if not c or "://" in c:
        return None
    if c.startswith("~"):
        return Path(c).expanduser().resolve()
    p = Path(c)
    if p.is_absolute():
        return p.resolve()
    return (base_dir / p).resolve()


def _linkify_line(line: str, *, base_dir: Path) -> Text:
    out = Text()
    idx = 0
    for m in _PATH_RE.finditer(line):
        start, end = m.span("path")
        cand = m.group("path")
        path_obj = _resolve_path(cand, base_dir=base_dir)
        if path_obj is None:
            continue
        out.append(line[idx:start])
        out.append(cand, style=f"link file://{path_obj}")
        idx = end
    out.append(line[idx:])
    return out


def print_cli_notice(
    console: Console,
    *,
    title: str,
    level: str,
    message: str,
    usage_line: Optional[str] = None,
    help_line: Optional[str] = None,
    example_line: Optional[str] = None,
) -> None:
    status = level.upper()
    lines = [f"{status} {message}"]
    if usage_line:
        lines.append(f"Usage: {usage_line}")
    if help_line:
        lines.append(f"Help: {help_line}")
    if example_line:
        lines.append(f"Example: {example_line}")
    print_section(console, title=title, body="\n".join(lines))


def print_session_boundary(console: Console, *, command: str, run_id: str, phase: str) -> None:
    phase_txt = "START" if phase == "start" else "END"
    console.print(f"\n[{COLOR_RULES['section_header']}]{'=' * 18} SESSION {phase_txt} {'=' * 18}[/{COLOR_RULES['section_header']}]")
    console.print(Text(f"command={command} | run_id={run_id}", style=COLOR_RULES["subtle"]))


def print_status_line(console: Console, text: str, *, tone: str = "info") -> None:
    color = COLOR_RULES.get(tone, COLOR_RULES["info"])
    console.print(Text(text, style=color))


def print_section(console: Console, *, title: str, body: str) -> None:
    console.print(f"\n[{COLOR_RULES['section_header']}]{'-' * 12} {title} {'-' * 12}[/{COLOR_RULES['section_header']}]")
    if body:
        base_dir = Path(os.getcwd()).resolve()
        for line in body.splitlines():
            txt = _linkify_line(line, base_dir=base_dir)
            for level in ("ERROR", "WARNING", "SUCCESS", "INFO"):
                prefix = f"{level} "
                if line.startswith(prefix):
                    txt.stylize(COLOR_RULES[level.lower()], 0, len(prefix))
                    break
            console.print(txt)


def print_kv_table(console: Console, *, title: str, rows: list[tuple[str, str]]) -> None:
    table = Table(title=title, show_header=False)
    table.add_column("Field", style=COLOR_RULES["section_header"], no_wrap=True)
    table.add_column("Value", style=COLOR_RULES["text"], overflow="fold")
    for k, v in rows:
        table.add_row(k, v)
    console.print(table)


def print_runtime_error(console: Console, title: str, error: Exception, hint: str) -> None:
    print_cli_notice(
        console,
        title=title,
        level="error",
        message=str(error),
        help_line=hint,
    )


def print_route_decision(console: Console, decision: RouteDecision) -> None:
    level = "success" if decision.mode == "deterministic" else "warning"
    message = (
        f"mode={decision.mode}"
        + (f" | handler={decision.handler_id}" if decision.handler_id else "")
        + f" | confidence={decision.confidence:.2f}"
    )
    print_cli_notice(
        console,
        title="Route Decision",
        level=level,
        message=message,
        help_line=decision.reason,
    )


def print_answer_path(console: Console, used: str, reason: str) -> None:
    print_cli_notice(
        console,
        title="Answer Path",
        level="success",
        message=f"used={used}",
        help_line=reason,
    )


def print_full_help(console: Console) -> None:
    print_section(
        console,
        title="Help",
        body=(
            "CAD Guardian CLI\n"
            "Ask over a live runtime snapshot of codebase/workspace and run policy-controlled actions from one CLI."
        ),
    )

    table = Table(title="Commands and Flags")
    table.add_column("Command", style=COLOR_RULES["section_header"], no_wrap=True)
    table.add_column("Arguments", style=COLOR_RULES["text"], no_wrap=True)
    table.add_column("Flags", style=COLOR_RULES["info"], overflow="fold")
    table.add_column("Purpose", style=COLOR_RULES["text"], overflow="fold")
    table.add_row("cg run", "PROMPT", "--full", "Deterministic-first execution; LLM fallback for open-ended tasks.")
    table.add_row("cg ask", "QUESTION", "--full, --ctx", "Read-only Q&A over runtime snapshot + light memory.")
    table.add_row("cg doctor", "(none)", "--verbose (optional)", "Environment and policy diagnostics.")
    table.add_row("cg inspect structure", "(none)", "-d 4", "Project tree from home path.")
    table.add_row("cg inspect workspace", "(none)", "-d (optional)", "Workspace tree with summary.")
    table.add_row("cg inspect outputs", "(none)", "-d (optional)", "Reports/logs/artifacts tree view.")
    table.add_row("cg dev snaps", "(none)", "(none)", "Run CLI snapshot tests and save report.")
    table.add_row("cg dev metrics", "(none)", "--format json|csv", "Build BI-ready telemetry summaries.")
    table.add_row(
        "cg dev dashboard",
        "(none)",
        "--live --refresh-seconds --port",
        "Open live dashboard for telemetry/memory/workspace/policy.",
    )
    table.add_row("cg --help", "(none)", "(none)", "Show this expanded help view.")
    console.print(table)
    print_section(
        console,
        title="Routing",
        body=(
            "Deterministic-first behavior:\n"
            "- obvious operational prompt -> deterministic handler (no LLM)\n"
            "- open-ended/ambiguous prompt -> LLM fallback\n"
            "Examples:\n"
            "- cg run \"show files\" -> deterministic\n"
            "- cg run \"design architecture\" -> llm"
        ),
    )
    print_section(
        console,
        title="Ask Shortcuts",
        body=(
            "Deterministic ask shortcuts:\n"
            "- \"how many <filename> files\" scans workspace directly (no LLM)\n"
            "Example:\n"
            "- cg ask \"how many metrics-summary.csv files?\""
        ),
    )
    print_section(
        console,
        title="Policy and Logs",
        body=(
            "Policy violations:\n"
            "- blocked actions show exact policy key from config/policy.json\n"
            "Traceability:\n"
            "- each session prints run_id\n"
            "- telemetry events are written for reporting"
        ),
    )
    print_section(
        console,
        title="Prompt Style",
        body="Use direct verbs for deterministic actions: show, list, count, run.",
    )
    print_section(
        console,
        title="Quick Examples",
        body=(
            "cg run \"List files in workspace\"\n"
            "cg run \"Run tests\" --full\n"
            "cg ask \"What does this app do?\" --ctx\n"
            "cg doctor\n"
            "cg doctor --verbose\n"
            "cg inspect structure -d 4\n"
            "cg inspect workspace -d 4\n"
            "cg inspect outputs -d 3\n"
            "cg dev snaps\n"
            "cg dev metrics --format json\n"
            "cg dev dashboard --live --refresh-seconds 5"
        ),
    )
