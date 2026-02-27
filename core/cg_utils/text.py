from __future__ import annotations


def cap_chars(s: str, max_chars: int, *, full_output: bool = False) -> str:
    if full_output or max_chars <= 0 or len(s) <= max_chars:
        return s
    return s[:max_chars] + "...(truncated)"


def cap_lines(text: str, max_lines: int, *, full_output: bool = False) -> str:
    if full_output or max_lines <= 0:
        return text
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n...(truncated lines)"


def truncate_for_display(
    text: str,
    *,
    max_chars: int,
    max_lines: int,
    full_output: bool,
) -> tuple[str, bool]:
    capped_chars = cap_chars(text, max_chars, full_output=full_output)
    out = cap_lines(capped_chars, max_lines, full_output=full_output)
    truncated = (not full_output) and (out != text)
    return out, truncated
