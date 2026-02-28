from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .memory import LongTermMemory
from .paths import Paths
from .policy import Policy
from .telemetry import append_event
from cg_utils import cap_chars


def limits_summary(policy: Policy) -> str:
    return (
        f"model={policy.llm_model()} | "
        f"mode={policy.execution_mode()} | "
        f"max_tokens={policy.max_completion_tokens()} | "
        f"max_steps={policy.max_steps_per_plan()} | "
        f"max_output_chars={policy.max_output_chars()}"
    )


def print_run_summary(print_section, console, *, route_mode: str, decision_reason: str, outcome: str, llm_used: bool, handler_id: str = "") -> None:
    lines = [
        f"outcome={outcome}",
        f"route={route_mode}",
        f"handler={handler_id or 'n/a'}",
        f"llm_used={llm_used}",
        f"reason={decision_reason or 'n/a'}",
    ]
    print_section(console, title="Run Summary", body="\n".join(lines))


def log_event(paths: Paths, event: dict[str, Any], *, session_id: str) -> None:
    try:
        payload = dict(event)
        payload.setdefault("session_id", session_id)
        payload.setdefault("run_id", str(uuid.uuid4()))
        append_event(paths.logs_dir, payload)
    except Exception:
        return


def memory_context(memory: LongTermMemory, prompt: str, policy: Policy) -> tuple[str, int]:
    max_memory_items = max(1, policy.max_memory_items())
    max_memory_chars = policy.max_memory_chars()
    retrieved_items = memory.query(prompt, n_results=max_memory_items)
    retrieved_text_full = "\n\n".join(
        [f"- {it.text} (kind={str((it.metadata or {}).get('kind', ''))})" for it in retrieved_items]
    ) or "(none)"
    return cap_chars(retrieved_text_full, max_memory_chars), len(retrieved_items)


def infer_memory_kind(user_text: str, *, mode: str) -> str:
    t = (user_text or "").strip().lower()
    if any(k in t for k in ["prefer ", "i prefer", "always ", "never ", "by default", "do not"]):
        return "preferences"
    if any(k in t for k in ["my name is", "i am ", "i'm ", "about me"]):
        return "user_profile"
    if mode == "run" and any(k in t for k in ["workflow", "pipeline", "scan", "propose", "confirm", "apply", "log"]):
        return "workflow_pattern"
    return "interaction"


def save_memory(
    memory: LongTermMemory,
    *,
    user_text: str,
    assistant_text: str,
    mode: str,
    kind_override: Optional[str] = None,
    extra_metadata: Optional[dict[str, str]] = None,
) -> None:
    kind = kind_override or infer_memory_kind(user_text, mode=mode)
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
        return


def finish_event(
    *,
    paths: Paths,
    started: float,
    session_id: str,
    command: str,
    route_mode: str,
    handler_id: str,
    outcome: str,
    llm_used: bool,
    actionable_steps: int,
    executed_steps: int,
    error_type: str = "",
    error_message: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    event = {
        "command": command,
        "route_mode": route_mode,
        "handler_id": handler_id,
        "outcome": outcome,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "llm_used": llm_used,
        "actionable_steps": actionable_steps,
        "executed_steps": executed_steps,
        "error_type": error_type,
        "error_message": cap_chars(error_message or "", 400),
    }
    if extra:
        event.update(extra)
    log_event(paths, event, session_id=session_id)
