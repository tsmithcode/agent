from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class DeterministicTool:
    handler_id: str
    label: str
    scorer: Callable[[str], tuple[float, str]]


@dataclass
class DeterministicContext:
    workspace_once: Callable[[int | None], None]
    outputs_once: Callable[[int | None], None]
    structure_once: Callable[[int | None], None]
    extract_depth: Callable[[str, int], int]
    snapshot_runner: Optional[Callable[..., None]] = None


def _contains_any(text: str, items: tuple[str, ...]) -> bool:
    return any(x in text for x in items)


def score_workspace(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if _contains_any(text, ("workspace files", "workspace tree", "list files in workspace", "show workspace files", "show files", "list files")):
        score += 0.8
        reasons.append("workspace phrase")
    if _contains_any(text, ("list", "show", "print", "display", "scan", "inventory")):
        score += 0.15
        reasons.append("action verb")
    if "workspace" in text:
        score += 0.1
        reasons.append("workspace token")
    return min(1.0, score), ", ".join(reasons) or "weak workspace match"


def score_outputs(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if _contains_any(text, ("show outputs", "inspect outputs", "output folders", "reports logs artifacts")):
        score += 0.8
        reasons.append("outputs phrase")
    if _contains_any(text, ("reports", "logs", "artifacts")):
        score += 0.15
        reasons.append("output token")
    if _contains_any(text, ("list", "show", "print", "display")):
        score += 0.1
        reasons.append("action verb")
    return min(1.0, score), ", ".join(reasons) or "weak outputs match"


def score_structure(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if _contains_any(text, ("show structure", "solution structure", "project tree", "folder tree")):
        score += 0.8
        reasons.append("structure phrase")
    if _contains_any(text, ("structure", "tree", "hierarchy")):
        score += 0.15
        reasons.append("structure token")
    if _contains_any(text, ("list", "show", "print", "display")):
        score += 0.1
        reasons.append("action verb")
    return min(1.0, score), ", ".join(reasons) or "weak structure match"


def score_snaps(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if _contains_any(text, ("snapshot tests", "run snapshots", "ui snapshot", "screen snapshot")):
        score += 0.85
        reasons.append("snapshot phrase")
    if _contains_any(text, ("run", "execute", "check", "validate")):
        score += 0.1
        reasons.append("action verb")
    return min(1.0, score), ", ".join(reasons) or "weak snapshot match"


TOOLS: tuple[DeterministicTool, ...] = (
    DeterministicTool("inspect_workspace", "Inspect Workspace", score_workspace),
    DeterministicTool("inspect_outputs", "Inspect Outputs", score_outputs),
    DeterministicTool("inspect_structure", "Inspect Structure", score_structure),
    DeterministicTool("dev_snaps", "Run Snapshot Tests", score_snaps),
)


def list_tools() -> list[DeterministicTool]:
    return list(TOOLS)


def score_tools(text: str) -> list[tuple[str, float, str]]:
    normalized = (text or "").strip().lower()
    return [(t.handler_id, *t.scorer(normalized)) for t in TOOLS]


def execute_tool(handler_id: str, prompt: str, ctx: DeterministicContext) -> tuple[bool, str]:
    try:
        if handler_id == "inspect_workspace":
            ctx.workspace_once(ctx.extract_depth(prompt, default=4))
            return True, "executed inspect workspace"
        if handler_id == "inspect_outputs":
            ctx.outputs_once(ctx.extract_depth(prompt, default=3))
            return True, "executed inspect outputs"
        if handler_id == "inspect_structure":
            ctx.structure_once(ctx.extract_depth(prompt, default=4))
            return True, "executed inspect structure"
        if handler_id == "dev_snaps":
            if ctx.snapshot_runner is None:
                return False, "snapshot runner unavailable"
            ctx.snapshot_runner(log_event=False)
            return True, "executed dev snaps"
        return False, f"unknown handler: {handler_id}"
    except SystemExit as e:
        code = int(getattr(e, "code", 1) or 1)
        return code == 0, f"handler exited with code {code}"
    except Exception as e:
        return False, str(e)
