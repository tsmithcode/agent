from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ..data.memory import LongTermMemory
from ..data.paths import Paths
from ..observability.telemetry import append_event
from ..safety.policy import Policy
from cg_utils import cap_chars


def limits_summary(policy: Policy) -> str:
    return (
        f"model={policy.llm_model()} | "
        f"max_tokens={policy.max_completion_tokens()} | "
        f"max_steps={policy.max_steps_per_plan()} | "
        f"max_output_chars={policy.max_output_chars()}"
    )


def memory_context(memory: LongTermMemory, prompt: str, policy: Policy) -> tuple[str, int]:
    items = memory.query(prompt, n_results=max(1, policy.max_memory_items()))
    text = "\n\n".join(f"- {x.text}" for x in items) or "(none)"
    return cap_chars(text, policy.max_memory_chars()), len(items)


def save_memory(
    memory: LongTermMemory,
    *,
    user_text: str,
    assistant_text: str,
    mode: str,
    kind: str = "interaction",
    extra_metadata: dict[str, str] | None = None,
) -> None:
    metadata = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "mode": mode,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    try:
        memory.add(mem_id=str(uuid.uuid4()), text=cap_chars(f"USER: {user_text}\nASSISTANT: {assistant_text}", 4000), metadata=metadata)
    except Exception:
        return


def finish_event(
    *,
    paths: Paths,
    started: float,
    session_id: str,
    command: str,
    route_mode: str,
    outcome: str,
    llm_used: bool,
    executed_steps: int,
    error_type: str = "",
    error_message: str = "",
) -> None:
    event = {
        "session_id": session_id,
        "run_id": str(uuid.uuid4()),
        "command": command,
        "route_mode": route_mode,
        "outcome": outcome,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "llm_used": llm_used,
        "executed_steps": executed_steps,
        "error_type": error_type,
        "error_message": cap_chars(error_message or "", 400),
    }
    append_event(paths.logs_dir, event)
