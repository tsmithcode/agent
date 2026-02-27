from __future__ import annotations

import re
from dataclasses import dataclass

from .policy import Policy


@dataclass(frozen=True)
class RouteDecision:
    mode: str
    handler_id: str | None
    confidence: float
    reason: str


def _contains_any(text: str, items: tuple[str, ...]) -> bool:
    return any(x in text for x in items)


def _score_workspace(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if _contains_any(
        text,
        (
            "workspace files",
            "workspace tree",
            "list files in workspace",
            "show workspace files",
            "show files",
            "list files",
        ),
    ):
        score += 0.8
        reasons.append("workspace phrase")
    if _contains_any(text, ("list", "show", "print", "display", "scan", "inventory")):
        score += 0.15
        reasons.append("action verb")
    if "workspace" in text:
        score += 0.1
        reasons.append("workspace token")
    return min(1.0, score), ", ".join(reasons) or "weak workspace match"


def _score_outputs(text: str) -> tuple[float, str]:
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


def _score_structure(text: str) -> tuple[float, str]:
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


def _score_snaps(text: str) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if _contains_any(text, ("snapshot tests", "run snapshots", "ui snapshot", "screen snapshot")):
        score += 0.85
        reasons.append("snapshot phrase")
    if _contains_any(text, ("run", "execute", "check", "validate")):
        score += 0.1
        reasons.append("action verb")
    return min(1.0, score), ", ".join(reasons) or "weak snapshot match"


def decide_route(prompt: str, policy: Policy) -> RouteDecision:
    if not policy.enable_deterministic_routing():
        return RouteDecision(mode="llm", handler_id=None, confidence=0.0, reason="routing disabled by policy")

    text = (prompt or "").strip().lower()
    if not text:
        return RouteDecision(mode="llm", handler_id=None, confidence=0.0, reason="empty prompt")

    for pattern in policy.force_llm_patterns():
        try:
            if re.search(pattern, text):
                return RouteDecision(mode="llm", handler_id=None, confidence=1.0, reason=f"force_llm pattern: {pattern}")
        except re.error:
            continue

    candidates: list[tuple[str, float, str]] = []
    for handler_id, scorer in (
        ("inspect_workspace", _score_workspace),
        ("inspect_outputs", _score_outputs),
        ("inspect_structure", _score_structure),
        ("dev_snaps", _score_snaps),
    ):
        score, reason = scorer(text)
        candidates.append((handler_id, score, reason))

    allowed = set(policy.allowed_deterministic_handlers())
    if allowed:
        candidates = [c for c in candidates if c[0] in allowed]
        if not candidates:
            return RouteDecision(mode="llm", handler_id=None, confidence=0.0, reason="no allowed deterministic handlers")

    candidates.sort(key=lambda x: x[1], reverse=True)
    best = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0.0
    threshold = policy.deterministic_confidence_threshold()

    if best[1] < threshold:
        return RouteDecision(
            mode="llm",
            handler_id=None,
            confidence=best[1],
            reason=f"top score {best[1]:.2f} below threshold {threshold:.2f}",
        )

    if (best[1] - second_score) < 0.08:
        return RouteDecision(
            mode="llm",
            handler_id=None,
            confidence=best[1],
            reason=f"ambiguous candidates delta<{0.08:.2f}",
        )

    return RouteDecision(mode="deterministic", handler_id=best[0], confidence=best[1], reason=best[2])
