from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

COLOR_RULES = {
    "section_header": "bold cyan",
    "error": "bold red",
    "warning": "bold yellow",
    "success": "bold green",
    "info": "bold blue",
    "subtle": "grey70",
    "text": "white",
}

_PATH_RE = re.compile(r"(?P<path>(?:~|\.{1,2}|/)[A-Za-z0-9._/\-]+|[A-Za-z0-9._-]+/[A-Za-z0-9._/\-]+)")
_URL_RE = re.compile(r"(?P<url>https?://[^\s]+)")
SIMPLE_MODE = False


def set_simple_mode(enabled: bool) -> None:
    global SIMPLE_MODE
    SIMPLE_MODE = bool(enabled)


def _resolve_path(candidate: str, *, base_dir: Path) -> Path | None:
    c = (candidate or "").strip()
    if not c or "://" in c:
        return None
    try:
        p = Path(os.path.expanduser(c))
        return p.resolve() if p.is_absolute() else (base_dir / p).resolve()
    except Exception:
        return None


def _linkify_line(line: str, *, base_dir: Path) -> Text:
    out = Text()
    idx = 0
    spans: list[tuple[int, int, str, str]] = []

    for m in _URL_RE.finditer(line):
        s, e = m.span("url")
        url = m.group("url")
        spans.append((s, e, url, f"underline link {url}"))

    for m in _PATH_RE.finditer(line):
        s, e = m.span("path")
        if any(not (e <= ps or s >= pe) for ps, pe, *_ in spans):
            continue
        token = m.group("path")
        p = _resolve_path(token, base_dir=base_dir)
        if p is None:
            continue
        spans.append((s, e, token, f"underline link file://{p}"))

    spans.sort(key=lambda x: x[0])
    for s, e, token, style in spans:
        if s < idx:
            continue
        out.append(line[idx:s])
        out.append(token, style=style)
        idx = e
    out.append(line[idx:])
    return out


def print_section(console: Console, *, title: str, body: str) -> None:
    console.print(f"\n[{COLOR_RULES['section_header']}]{'-'*12} {title} {'-'*12}[/{COLOR_RULES['section_header']}]")
    if not body:
        return
    base = Path(os.getcwd()).resolve()
    for line in body.splitlines():
        txt = _linkify_line(line, base_dir=base)
        for level, color in (("ERROR", "error"), ("WARNING", "warning"), ("SUCCESS", "success"), ("INFO", "info")):
            prefix = f"{level} "
            if line.startswith(prefix):
                txt.stylize(COLOR_RULES[color], 0, len(prefix))
                break
        console.print(txt)


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
    marker = "START" if phase == "start" else "END"
    console.print(f"\n[{COLOR_RULES['section_header']}]{'='*18} SESSION {marker} {'='*18}[/{COLOR_RULES['section_header']}]")
    console.print(Text(f"command={command} | run_id={run_id}", style=COLOR_RULES["subtle"]))


def print_status_line(console: Console, text: str, *, tone: str = "info") -> None:
    console.print(Text(text, style=COLOR_RULES.get(tone, COLOR_RULES["info"])))


def print_kv_table(console: Console, *, title: str, rows: list[tuple[str, str]]) -> None:
    t = Table(title=title, show_header=False)
    t.add_column("Field", no_wrap=True)
    t.add_column("Value", overflow="fold")
    for k, v in rows:
        t.add_row(k, v)
    console.print(t)


def print_runtime_error(console: Console, title: str, error: Exception, hint: str) -> None:
    print_cli_notice(console, title=title, level="error", message=str(error), help_line=hint)


def print_answer_path(console: Console, used: str, reason: str) -> None:
    label = {
        "llm": "used=llm",
        "command": "used=command",
        "both": "used=llm+command",
    }.get(used, f"used={used}")
    print_cli_notice(console, title="Answer Path", level="success", message=label, help_line=reason)


def print_route_decision(console: Console, decision) -> None:
    # Compatibility shim for older call sites; core profile is LLM-only.
    _ = decision
    print_cli_notice(console, title="Route Decision", level="info", message="mode=llm", help_line="Core profile is LLM-only.")


def print_full_help(console: Console, *, plugins: dict[str, bool] | None = None) -> None:
    _ = plugins
    print_section(
        console,
        title="Help",
        body=(
            "CAD Guardian Core\n"
            "LLM-first CLI agent with policy-controlled execution and interactive loop.\n"
            "Global flag: --simple"
        ),
    )
    t = Table(title="Commands")
    t.add_column("Command", no_wrap=True)
    t.add_column("Arguments", no_wrap=True)
    t.add_column("Flags", overflow="fold")
    t.add_column("Purpose", overflow="fold")
    t.add_row("cg", "(none)", "--simple", "Start interactive loop in a terminal.")
    t.add_row("cg loop", "(none)", "--mode ask|run|do --full --ctx", "Interactive repeat-use loop.")
    t.add_row("cg do", "REQUEST", "--full --ctx", "Auto route to ask/run (LLM-only).")
    t.add_row("cg run", "PROMPT", "--full", "Plan + execute policy-safe steps.")
    t.add_row("cg ask", "QUESTION", "--full --ctx", "Read-only analysis over runtime snapshot.")
    t.add_row("cg inspect workspace", "(none)", "-d", "Workspace tree and summary.")
    t.add_row("cg inspect outputs", "(none)", "-d", "Reports/logs/artifacts tree.")
    t.add_row("cg inspect loc", "(none)", "(none)", "Lines-of-code summary.")
    t.add_row("cg status", "(none)", "--limit", "Telemetry summary and quick health.")
    t.add_row("cg doctor", "(none)", "--verbose", "Environment and policy diagnostics.")
    t.add_row("cg policy show", "(none)", "(none)", "Show active policy summary.")
    console.print(t)
