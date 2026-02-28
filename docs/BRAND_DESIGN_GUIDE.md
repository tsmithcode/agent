# CAD Guardian Brand and Design Guide

This file is the single source of truth for CAD Guardian visual and UX consistency.

Use it for:

- CLI output design
- Dashboard design
- Accessibility requirements
- Product copy tone
- Future UI additions

## 1. Brand Identity

### Brand goals

- Enterprise trust
- Operational clarity
- Low fatigue for power users
- Consistent purple-on-dark visual language

### Voice and tone

- Direct
- Technical
- Calm and precise
- Actionable over promotional

## 2. Core Color System

### Primary palette

| Token | Hex | Usage |
|---|---|---|
| `cad-bg` | `#050506` | Global app background |
| `cad-card` | `#0f1020` | Primary card/panel backgrounds |
| `cad-card-2` | `#15172a` | Secondary chart panel background |
| `cad-accent` | `#a78bfa` | Primary brand accent |
| `cad-text` | `#f3f4f6` | Main readable foreground |
| `cad-subtle` | `#c2c6d0` | Secondary foreground labels |
| `cad-muted` | `#9aa0ad` | Tertiary helper text |
| `cad-border` | `rgba(167, 139, 250, 0.35)` | Border system |

### Semantic status colors (CLI)

| Token | Hex | Meaning |
|---|---|---|
| `success` | `#34d399` | successful outcomes |
| `warning` | `#fbbf24` | non-blocking limits/warnings |
| `error` | `#f87171` | blocking failures |
| `info` | `#c4b5fd` | neutral progress updates |

## 3. Typography and Spacing

### Base sizes

- Base body: `17px`
- Caption/body secondary: `16px` equivalent
- Chart axis labels: `13px` minimum
- Chart axis titles: `14px` minimum
- KPI metric values: `28px+` responsive

### Readability rules

- Never use light background with light text.
- Avoid tiny chart labels.
- Keep line-length practical for terminals and dashboards.
- Prefer concise, high-signal labels.

## 4. CLI Design Standards

### Screen composition

- Use section dividers for narrative/status blocks.
- Use tables for dense structured data.
- Use tree view for filesystem data.
- Always keep explicit labels (`ERROR`, `WARNING`, `SUCCESS`).

### Required UX behaviors

- Show deterministic vs LLM route decisions.
- Show answer path (`command`, `llm`, `both`).
- Show policy rule when a violation occurs.
- Keep output copy/paste friendly.

### CLI references

- `agent/core/cg/cli_ui.py`
- `agent/docs/CLI_COLOR_RULES.md`

## 5. Dashboard Design Standards

### Layout principles

- Dark-themed, high contrast at all times.
- Metric cards must be readable at a glance.
- Charts must match brand palette.
- Tables must be scrollable for large datasets.
- Mobile/tablet layouts must stack or wrap cleanly.

### Chart rules

- Use branded purple bars.
- Non-zoom/non-pan by default (stable review state).
- Hide chart action toolbars.
- Keep chart labels readable (`13px+`).
- Keep chart background dark and integrated with cards.

### Table/data grid rules

- Dark header background with strong contrast text.
- Consistent border color (`cad-border`).
- Vertical scrolling enabled for dense sections.
- Hide index when not useful.

### JSON panel rules

- Dark card background (never white default).
- High contrast text.
- Same border radius/border system as tables/charts.

### Dashboard references

- `agent/core/cg/dashboard_app.py`
- `agent/core/cg/dashboard_data.py`

## 6. Accessibility Requirements

### Must-have

- Do not rely on color alone.
- Maintain status keywords (`ERROR`, `WARNING`, etc.).
- High contrast foreground/background.
- Mobile readable font sizes.
- Avoid tiny controls and cramped layout.

### Responsive behavior

- Desktop: multi-column layout.
- Tablet: wrap to 2-column where needed.
- Mobile: stack to single-column.

## 7. Component Mapping

Use this component type by data shape:

| Data shape | Preferred component |
|---|---|
| Key/value runtime info | key-value table/card |
| Command/policy matrix | table |
| Status/explanations | section blocks |
| File hierarchy | tree |
| Metric trends/distributions | branded charts |
| Large record sets | scrollable dataframe/table |
| Structured detail blobs | JSON panel (dark themed) |

## 7.1 Path Rendering Rules

Path display must be consistent across all CLI screens:

- Keep clickable hyperlink behavior for all rendered absolute/relative paths.
- Root path in tree views: semantic success green.
- Directory paths: brand purple (`path_dir`).
- File paths: readable subtle light text (`path_file`).
- If a path is shown in a status message, render via section/notice components so hyperlink + color rules apply.
- Do not print raw unstyled path strings when a styled helper exists.

## 8. Copy Standards

- Keep command hints short and concrete.
- Use consistent naming (`CAD Guardian`, `Route Decision`, `Answer Path`).
- Prefer “what happened + what to do next”.
- Avoid redundant phrasing.

## 9. Implementation Checklist

Before shipping any UI change:

1. Matches color tokens and status semantics.
2. Uses correct component type for data.
3. Works on desktop/tablet/mobile.
4. Preserves accessibility (contrast + labels).
5. Keeps copy concise and actionable.
6. Keeps policy/route transparency intact.

## 10. Change Control

If any UI/style behavior deviates from this guide:

1. Update code to match this guide, or
2. Update this guide first, then implement consistently.

This prevents visual drift and keeps GTM presentation consistent.
