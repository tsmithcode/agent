# CAD Guardian Plugin Architecture

## Goal

Provide true plugin behavior with runtime gating and clean extensibility, while keeping core CLI stable.

## Source of Truth

- Plugin config: `config/plugins.json`
- Plugin contracts + resolution: `core/cg/safety/plugins.py`
- Capability enforcement: `core/cg/safety/capability_manifest.py`
- Command registration: `core/cg/cli/main.py` and `core/cg/cli/command_groups.py`

## How Plugin Gating Works

A plugin is effectively available only when all are true:

1. plugin key is `true` in `config/plugins.json`
2. required files exist
3. required Python modules are installed (if declared)
4. capability manifest validation passes

If not available:

- related commands are not attached
- related help surfaces should be hidden
- doctor reports contract failures

## Current Plugin Set

| Plugin key | Primary command surface | Main implementation |
|---|---|---|
| `dashboard` | `cg dev dashboard` | `core/cg/addons/dashboard_app.py`, `core/cg/addons/dashboard_data.py` |
| `eval` | `cg dev eval` | `core/cg/addons/eval_harness.py` |
| `snapshots` | `cg dev snaps` | snapshot runner in CLI/dev flow + tests |
| `metrics` | `cg dev metrics` | `core/cg/observability/telemetry.py` aggregation |
| `tasks` | `cg tasks list/run` | task templates in `core/cg/cli/command_groups.py` |
| `fetch_drive` | `cg fetch` | `core/cg/addons/gdrive_fetch.py` |

## Build Profiles

- Full build: default artifact (includes add-ons)
- Core build: `CG_BUILD_PROFILE=core` strips add-on modules from artifacts for minimal distribution

## Contract-First Extension Pattern

When adding a plugin:

1. Add contract entry in `plugins.py`
2. Define required files/deps
3. Register command only when enabled
4. Add capability manifest mapping
5. Add doctor checks
6. Add docs under `core/cg/addons/README.<plugin>.md`

## UX/DX Requirements

- Plugin-off means no dead commands in help
- Errors must state missing contract part (file/dependency/config)
- Command output must identify route used (`command`, `llm`, `both`)
- Telemetry must remain schema-consistent whether plugins are on/off
