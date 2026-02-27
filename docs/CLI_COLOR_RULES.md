# CLI Color Rules

Use this guide for consistent, accessible CLI styling.

## Palette

| Tone | Color | Use |
|---|---|---|
| `section_header` | `bold #a78bfa` | Section dividers and headings (brand purple) |
| `success` | `bold #34d399` | Successful outcomes and deterministic matches |
| `info` | `#c4b5fd` | Neutral progress/status lines (purple-tinted info) |
| `warning` | `bold #fbbf24` | Truncation, limits, non-blocking issues |
| `error` | `bold #f87171` | Blocking failures and policy violations |
| `subtle` | `#9ca3af` | Session metadata and secondary labels |
| `text` | `#f3f4f6` | Primary readable foreground text |

## Usage Rules

1. Keep section headers in `section_header` tone.
2. Use `SUCCESS/WARNING/ERROR/INFO` prefixes in notice lines.
3. Reserve `error` for actionable failures only.
4. Use `warning` for soft limits and fallback behavior.
5. Use `info` for progress lines (`Executing step`, etc.).
6. Keep body text plain; use color on labels/prefixes, not entire paragraphs.
7. Keep branding purple-forward in headings/help sections to match website GTM visuals.

## Where Implemented

- `agent/core/cg/cli_ui.py`
  - `COLOR_RULES`
  - `print_cli_notice`
  - `print_status_line`
  - `print_section`

## Accessibility Notes

1. Do not rely on color alone; keep explicit text labels (`ERROR`, `WARNING`, etc.).
2. Prefer high-contrast colors already in the palette above.
3. Keep long instructional text neutral and concise for copy/paste workflows.
