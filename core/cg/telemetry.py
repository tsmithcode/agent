from __future__ import annotations

import csv
import json
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.1"
EVENT_FILE = "cg_events.jsonl"
MAX_EVENT_FILE_BYTES = 5 * 1024 * 1024
MAX_ROTATED_FILES = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rotate_if_needed(logs_dir: Path) -> None:
    p = logs_dir / EVENT_FILE
    if not p.exists():
        return
    try:
        if p.stat().st_size <= MAX_EVENT_FILE_BYTES:
            return
    except Exception:
        return

    oldest = logs_dir / f"{EVENT_FILE}.{MAX_ROTATED_FILES}"
    if oldest.exists():
        oldest.unlink(missing_ok=True)
    for i in range(MAX_ROTATED_FILES - 1, 0, -1):
        cur = logs_dir / f"{EVENT_FILE}.{i}"
        nxt = logs_dir / f"{EVENT_FILE}.{i+1}"
        if cur.exists():
            cur.rename(nxt)
    p.rename(logs_dir / f"{EVENT_FILE}.1")


def _sanitize_text(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"sk-[A-Za-z0-9_\-]{10,}", "sk-***REDACTED***", s)
    s = re.sub(r"(?i)(api[_-]?key)\s*[:=]\s*[^,\s]+", r"\1=***REDACTED***", s)
    return s


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in event.items():
        if isinstance(v, str):
            out[k] = _sanitize_text(v)
        else:
            out[k] = v
    return out


def append_event(logs_dir: Path, event: dict[str, Any]) -> None:
    logs_dir = logs_dir.resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed(logs_dir)
    payload = _sanitize_event(dict(event))
    payload.setdefault("event_id", str(uuid.uuid4()))
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("ts_utc", _utc_now())
    line = json.dumps(payload, ensure_ascii=True)
    with (logs_dir / EVENT_FILE).open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_events(logs_dir: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    p = (logs_dir.resolve() / EVENT_FILE)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    if limit is not None and limit > 0:
        return out[-limit:]
    return out


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_command: dict[str, int] = defaultdict(int)
    by_route: dict[str, int] = defaultdict(int)
    by_outcome: dict[str, int] = defaultdict(int)
    by_command_outcome: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    duration_sum: dict[str, int] = defaultdict(int)
    duration_count: dict[str, int] = defaultdict(int)
    llm_used = 0

    for e in events:
        cmd = str(e.get("command") or "unknown")
        route = str(e.get("route_mode") or "n/a")
        outcome = str(e.get("outcome") or "unknown")
        by_command[cmd] += 1
        by_route[route] += 1
        by_outcome[outcome] += 1
        by_command_outcome[cmd][outcome] += 1
        if bool(e.get("llm_used")):
            llm_used += 1
        try:
            d = int(e.get("duration_ms") or 0)
            duration_sum[cmd] += d
            duration_count[cmd] += 1
        except Exception:
            pass

    avg_duration_by_command: dict[str, float] = {}
    for cmd, total in duration_sum.items():
        n = duration_count.get(cmd, 0) or 1
        avg_duration_by_command[cmd] = round(total / n, 2)

    by_command_outcome_sorted: dict[str, dict[str, int]] = {}
    for cmd, outcomes in sorted(by_command_outcome.items()):
        by_command_outcome_sorted[cmd] = dict(sorted(outcomes.items()))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_ts_utc": _utc_now(),
        "events_total": len(events),
        "llm_used_count": llm_used,
        "llm_used_rate": round((llm_used / len(events)), 4) if events else 0.0,
        "by_command": dict(sorted(by_command.items())),
        "by_route_mode": dict(sorted(by_route.items())),
        "by_outcome": dict(sorted(by_outcome.items())),
        "by_command_outcome": by_command_outcome_sorted,
        "avg_duration_ms_by_command": dict(sorted(avg_duration_by_command.items())),
    }


def write_summary_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")


def write_summary_csv(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_command = summary.get("by_command") or {}
    by_command_outcome = summary.get("by_command_outcome") or {}
    avg = summary.get("avg_duration_ms_by_command") or {}
    rows = []
    for cmd, total in sorted(by_command.items()):
        outcomes = by_command_outcome.get(cmd) or {}
        rows.append(
            {
                "command": cmd,
                "events_total": total,
                "avg_duration_ms": avg.get(cmd, 0),
                "outcome_success_total": outcomes.get("success", 0),
                "outcome_warn_total": outcomes.get("warn", 0),
                "outcome_fail_total": outcomes.get("fail", 0),
                "outcome_error_total": outcomes.get("error", 0),
                "outcome_confirmation_required_total": outcomes.get("confirmation_required", 0),
                "outcome_no_actionable_total": outcomes.get("no_actionable", 0),
            }
        )
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "command",
                "events_total",
                "avg_duration_ms",
                "outcome_success_total",
                "outcome_warn_total",
                "outcome_fail_total",
                "outcome_error_total",
                "outcome_confirmation_required_total",
                "outcome_no_actionable_total",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)
