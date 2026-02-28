# Command Reference (Source of Truth)

This is the canonical command and flag reference for CAD Guardian.

Notes:

- Use `--simple` on any command for beginner-friendly wording.
- `dev` and some other commands are plugin-gated.
- Deterministic-first routing applies mainly to `run` and `do`.

## Core Commands

| Command | Arguments | Flags | Behavior |
|---|---|---|---|
| `cg run` | `PROMPT` | `--full` | Deterministic-first execution, LLM fallback for open-ended prompts. |
| `cg ask` | `QUESTION` | `--full`, `--ctx` | Read-only Q&A over runtime snapshot + memory context. |
| `cg do` | `REQUEST` | `--full`, `--ctx` | Auto-selects ask or run mode for lower user fatigue. |
| `cg setup` | none | `--apply-base/--no-apply-base`, `--doctor/--no-doctor` | First-run onboarding checks and baseline setup. |
| `cg guide` | none | `--mode starter|power` | Guided usage paths. |
| `cg status` | none | `--limit` | Telemetry summary and recommendations. |
| `cg doctor` | none | `--verbose` | Runtime, policy, plugin, and environment diagnostics. |
| `cg inspect structure` | none | `-d` | Solution tree view. |
| `cg inspect workspace` | none | `-d` | Workspace file tree + summary. |
| `cg inspect outputs` | none | `-d` | Reports/logs/artifacts tree + summary. |
| `cg inspect loc` | none | none | Line count excluding workspace/log/cache areas. |
| `cg policy list` | none | none | Show available policy tiers. |
| `cg policy show` | none | none | Show active policy + inferred tier. |
| `cg policy use` | `TIER` | `--yes` | Apply `cheap`, `base`, or `max` policy profile. |

## Plugin-Gated Commands

| Command | Plugin key | Arguments | Flags | Behavior |
|---|---|---|---|---|
| `cg fetch` | `fetch_drive` | `DRIVE_FOLDER_LINK` | `--folder`, `-d`, `--open/--no-open` | Download public Drive folder into workspace downloads. |
| `cg tasks list` | `tasks` | none | none | List starter task templates. |
| `cg tasks run` | `tasks` | `NAME` | none | Run selected task template. |
| `cg dev snaps` | `snapshots` | none | none | Run CLI snapshot tests and save report. |
| `cg dev eval` | `eval` | none | `--suite core` | Run native eval harness suite. |
| `cg dev metrics` | `metrics` | none | `--format json|csv`, `--limit` | Export aggregated telemetry report. |
| `cg dev dashboard` | `dashboard` | none | `--live`, `--refresh-seconds`, `--port`, `--event-limit` | Start/restart live Streamlit dashboard. |

## Deterministic vs LLM Routing

Examples:

- `cg run "show files"` -> deterministic command handler
- `cg run "design architecture options"` -> LLM route
- `cg do "show files"` -> deterministic via auto-route

## Ownership

CAD Guardian is a CAD Guardian brand product.
