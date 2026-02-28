from __future__ import annotations

import re
from dataclasses import dataclass

from .policy import Policy
from .tool_registry import score_tools


@dataclass(frozen=True)
class RouteDecision:
    mode: str
    handler_id: str | None
    confidence: float
    reason: str


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

    candidates = score_tools(text)

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
