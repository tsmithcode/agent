from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .telemetry import read_events, summarize_events
except ImportError as e:
    if "attempted relative import with no known parent package" not in str(e):
        raise
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from telemetry import read_events, summarize_events  # type: ignore


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def load_event_overview(logs_dir: Path, *, limit: int = 5000) -> dict[str, Any]:
    events = read_events(logs_dir, limit=limit)
    summary = summarize_events(events)

    command_timeline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    route_timeline: dict[str, int] = defaultdict(int)
    outcome_timeline: dict[str, int] = defaultdict(int)
    latest_events: list[dict[str, Any]] = []

    for e in events:
        cmd = str(e.get("command") or "unknown")
        route = str(e.get("route_mode") or "n/a")
        outcome = str(e.get("outcome") or "unknown")
        ts = str(e.get("ts_utc") or "")
        command_timeline[cmd].append({"ts_utc": ts, "duration_ms": int(e.get("duration_ms") or 0), "outcome": outcome})
        route_timeline[route] += 1
        outcome_timeline[outcome] += 1
        latest_events.append(
            {
                "ts_utc": ts,
                "command": cmd,
                "route_mode": route,
                "outcome": outcome,
                "duration_ms": int(e.get("duration_ms") or 0),
                "llm_used": bool(e.get("llm_used")),
            }
        )

    latest_events.sort(key=lambda x: x.get("ts_utc") or "", reverse=True)
    latest_events = latest_events[:50]

    return {
        "events": events,
        "summary": summary,
        "route_distribution": dict(sorted(route_timeline.items())),
        "outcome_distribution": dict(sorted(outcome_timeline.items())),
        "command_timeline": dict(command_timeline),
        "latest_events": latest_events,
    }


def load_memory_overview(chroma_dir: Path, *, collection_name: str = "cg_openclaw_memory") -> dict[str, Any]:
    out: dict[str, Any] = {
        "items_total": 0,
        "by_kind": {},
        "newest_ts_utc": "",
        "oldest_ts_utc": "",
        "latest_items": [],
        "status": "ok",
        "error": "",
    }
    try:
        from chromadb import PersistentClient

        client = PersistentClient(path=str(chroma_dir))
        coll = client.get_or_create_collection(name=collection_name)
        count = coll.count()
        out["items_total"] = count
        if count == 0:
            return out

        got = coll.get(include=["metadatas", "documents"], limit=min(count, 5000))
        metas = got.get("metadatas") or []
        docs = got.get("documents") or []
        kinds = Counter(str((m or {}).get("kind") or "unknown") for m in metas)
        out["by_kind"] = dict(sorted(kinds.items()))

        ts_vals = [str((m or {}).get("ts_utc") or "") for m in metas if (m or {}).get("ts_utc")]
        ts_vals = [x for x in ts_vals if x]
        if ts_vals:
            out["oldest_ts_utc"] = min(ts_vals)
            out["newest_ts_utc"] = max(ts_vals)

        latest_items: list[dict[str, Any]] = []
        for i, meta in enumerate(metas):
            m = meta or {}
            doc = ""
            if i < len(docs):
                doc = str(docs[i] or "")
            latest_items.append(
                {
                    "ts_utc": str(m.get("ts_utc") or ""),
                    "kind": str(m.get("kind") or "unknown"),
                    "mode": str(m.get("mode") or ""),
                    "preview": (doc.replace("\n", " ")[:140] + ("..." if len(doc) > 140 else "")),
                }
            )
        latest_items.sort(key=lambda x: x.get("ts_utc") or "", reverse=True)
        out["latest_items"] = latest_items[:50]
        return out
    except Exception as e:
        out["status"] = "error"
        out["error"] = str(e)
        return out


def load_workspace_overview(workspace: Path) -> dict[str, Any]:
    files = 0
    dirs = 0
    total_bytes = 0
    by_ext: Counter[str] = Counter()
    largest: list[tuple[int, str]] = []
    changed_recent: list[str] = []
    now = datetime.now(timezone.utc)

    for p in workspace.rglob("*"):
        if p.is_dir():
            dirs += 1
            continue
        files += 1
        try:
            stat = p.stat()
            size = int(stat.st_size)
            total_bytes += size
            ext = p.suffix.lower() or "(no_ext)"
            by_ext[ext] += 1
            largest.append((size, str(p.relative_to(workspace))))
            mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            if (now - mtime).total_seconds() <= 24 * 3600:
                changed_recent.append(str(p.relative_to(workspace)))
        except Exception:
            continue

    largest.sort(reverse=True)
    top_largest = [{"path": p, "bytes": b} for b, p in largest[:20]]
    top_ext = [{"ext": k, "count": v} for k, v in by_ext.most_common(20)]

    return {
        "files_total": files,
        "dirs_total": dirs,
        "bytes_total": total_bytes,
        "top_extensions": top_ext,
        "largest_files": top_largest,
        "changed_last_24h_total": len(changed_recent),
        "changed_last_24h_sample": changed_recent[:50],
    }


def load_policy_overview(policy_path: Path) -> dict[str, Any]:
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    exec_limits = dict(data.get("execution_limits") or {})
    routing = dict(data.get("routing_controls") or {})
    network = dict(data.get("network_controls") or {})
    return {
        "execution_limits": exec_limits,
        "routing_controls": routing,
        "network_controls": network,
        "command_allowlist_count": len(data.get("command_allowlist") or []),
        "command_denylist_count": len(data.get("command_denylist") or []),
        "denied_paths_count": len(data.get("denied_paths") or []),
    }


def load_reports_overview(workspace: Path) -> dict[str, Any]:
    reports_root = workspace / "reports"
    ui_root = reports_root / "ui-snapshots"
    metrics_root = reports_root / "metrics"

    ui_runs = sorted([p.name for p in ui_root.iterdir() if p.is_dir()], reverse=True) if ui_root.exists() else []
    metric_runs = sorted([p.name for p in metrics_root.iterdir() if p.is_dir()], reverse=True) if metrics_root.exists() else []

    return {
        "ui_snapshot_runs_total": len(ui_runs),
        "ui_snapshot_runs_latest": ui_runs[:20],
        "metrics_runs_total": len(metric_runs),
        "metrics_runs_latest": metric_runs[:20],
    }
