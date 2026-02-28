# CAD Guardian

CAD Guardian is a policy-controlled AI CLI for power users.

Default model: `gpt-4o-mini` (configurable via `execution_limits.llm_model` in policy).
Beginner wording mode: add `--simple` to any command, e.g. `cg --simple do "show files"`.

It helps you:

- Ask over a live runtime snapshot of codebase/workspace (`cg ask`)
- Run safe, policy-governed actions (`cg run`) with deterministic auto-routing for obvious tasks
- Keep token/runtime costs bounded with explicit execution limits
- Optional plugins toggle advanced features (dashboard, evals, snapshots, metrics, tasks, Drive fetch) via `config/plugins.json`
- Delivery guide: `docs/DELIVERY_GUIDE.md` (release, install, update flow)

## Install

### Option 1: Local editable install

```bash
cd /path/to/cad-guardian/agent
python -m pip install -e .
```

Full add-on dependencies:

```bash
python -m pip install -e .[full]
```

### Option 2: pipx (recommended for CLI)

```bash
cd /path/to/cad-guardian/agent
pipx install .
```

Full add-on dependencies:

```bash
pipx install '.[full]'
```

Then run (short notes):

Core-safe commands:

```bash
cg --help  # full command list and flags
cg setup  # env checks + baseline policy
cg guide --mode starter  # beginner flow
cg do "show files"  # auto-route to safe handler
cg guide --mode starter  # repeatable quick flow
cg status --limit 200  # usage summary + tips
cg doctor  # diagnostics
cg doctor --verbose  # full path inventory
cg policy list  # available tiers
cg policy show  # active policy + expectation
cg policy use base --yes  # apply baseline tier
cg inspect structure  # solution tree
```

With full add-on install (`.[full]`) and matching plugin contracts:

```bash
cg tasks list  # built-in templates (tasks plugin)
cg dev snaps  # snapshots plugin
cg dev eval --suite core  # eval plugin
cg dev metrics --format json --limit 1000  # metrics plugin
cg dev dashboard --live --refresh-seconds 5 --event-limit 5000  # dashboard plugin
```

Routing behavior:

- `cg run` is deterministic-first for obvious operational prompts
- falls back to LLM for open-ended prompts
- examples:
  - `cg run "show files"` -> deterministic (no LLM)
  - `cg run "design architecture"` -> LLM

## Quick Usage

Assumes full add-on install (`.[full]`) and satisfied plugin contracts.

```bash
cg ask "What does this app do right now?"
cg do "What can you do with this workspace?"
cg guide --mode starter
cg ask "What can you infer from current policy?" --ctx
cg run "List project files"
cg run "List project files" --full
cg fetch "https://drive.google.com/drive/folders/<id>" --folder incoming-assets
cg status --limit 200
cg policy list
cg policy use cheap --yes
cg inspect workspace
cg inspect loc
cg dev snaps  # snapshots plugin
cg dev metrics --format csv --limit 2000  # metrics plugin
cg dev dashboard --live --event-limit 10000  # dashboard plugin
```

## Policy Tiers (Cost Profiles)

CAD Guardian supports policy snapshots using the same schema with different values:

- `cheap`: lowest token/context/output budget for repetitive operations
- `base`: balanced default for daily use
- `max`: highest context and quality budget for deep analysis sessions

Expectations by tier:

- `cheap` (`gpt-4o-mini`): fastest + lowest cost; best for inspect/count/list and straightforward actions.
- `base` (`gpt-4o`): recommended daily baseline; better reasoning and moderate refactor support with controlled spend.
- `max` (`gpt-4.1`): high-capability mode for deeper architecture work and larger multi-step refactors; highest cost.

Commands:

```bash
cg policy list  # show tiers
cg policy show  # active policy summary
cg policy use cheap --yes  # lowest cost
cg policy use base --yes  # balanced default
cg policy use max --yes  # highest capability
```

Profile files:

- `config/policy.profiles/cheap.json`
- `config/policy.profiles/base.json`
- `config/policy.profiles/max.json`

## Beginner Flows

Use these commands for low-fatigue onboarding:

- `cg setup` to run first-time checks and baseline defaults
- `cg guide --mode starter` for step-by-step usage
- `cg do "<request>"` to auto-route between ask/run
- `cg tasks list` and `cg tasks run <name>` for ready-made workflows

## Dashboard UX

### Plugins

- Config file: `config/plugins.json`
- Defaults: all plugins `true` for full experience.
- Effective plugin availability is contract-based (enabled in config + required files + required deps installed).
- Build profile `CG_BUILD_PROFILE=core` excludes `cg.addons` modules from artifact output.
- Plugin to surface mapping:
  - `dashboard`: enables `cg dev dashboard`
  - `eval`: enables `cg dev eval`
  - `snapshots`: enables `cg dev snaps`
  - `metrics`: enables `cg dev metrics`
  - `tasks`: enables `cg tasks list|run`
  - `fetch_drive`: enables `cg fetch`

`cg dev dashboard` is optimized for readable enterprise reporting:

- Branded dark theme with high-contrast typography
- Fixed-position charts (non-zoom/non-pan) for consistent review screenshots
- Branded chart colors and larger chart axis labels
- Scrollable tables for high-volume sections
- Memory Health includes `Recent Memory Items` table
- Memory Health includes `User Goal Summary (Memories Only)` generated by the AI model
- Mobile/tablet responsive layout for stacked/wrapped sections

Goal summary behavior:

- Uses only persisted memory entries as context
- Cached for 5 minutes and refreshed when memory changes
- Shows a warning when `OPENAI_API_KEY` is not available

Example:

```bash
cg dev dashboard --live --refresh-seconds 5 --port 8501
```

Start/stop:

```bash
# start dashboard
cg dev dashboard --live --refresh-seconds 5 --port 8501

# stop dashboard (if running in background)
pkill -f "streamlit run .*addons/dashboard_app.py"
```

## Marketplace Description (Ready Copy)

**Title:** CAD Guardian — Safe AI Agent for Power Users

**Tagline:** Ask over a live runtime snapshot of codebase/workspace and run policy-controlled actions from one CLI.

**Description:**
CAD Guardian is a local-first AI CLI for developers and operators who need useful automation without losing control.

- Read-only Q&A over a live runtime snapshot (`cg ask`)
- Policy-enforced execution for commands and file writes (`cg run`)
- Deterministic-first routing for obvious operational prompts, with LLM fallback for open-ended requests
- Clear safety boundaries: allowlists, denied paths, network domain controls
- Cost controls: token, memory, output, and execution-step limits
- Built for practical workflows: transparent plans and predictable behavior

## Batch Workflow Pattern

For file and folder operations in `workspace`, use this standard pattern:

1. Scan
2. Propose (dry-run plan)
3. Confirm
4. Apply
5. Log

This keeps UX simple, safe, and repeatable for high-volume workflows.

For apply-style batch requests in `cg run`, use explicit confirmation:

- add `confirm:yes` in the prompt to execute apply actions
- without it, CAD Guardian will propose/plan but block execution

## Developer Notes

- CLI entrypoint: `cg.cli.main:cli`
- Main runtime: `core/cg/cli/main.py`
- Run execution engine: `core/cg/runtime/run_engine.py`
- Ask/read-only engine: `core/cg/runtime/ask_engine.py`
- Shared runtime helpers: `core/cg/runtime/common.py`
- Management command groups (policy/tasks/dev/inspect): `core/cg/cli/command_groups.py`
- Deterministic tool registry: `core/cg/routing/tool_registry.py`
- Runtime capability guard: `core/cg/safety/capability_manifest.py` + `config/capabilities.manifest.json`
- CLI view layer: `core/cg/cli/ui/cli_ui.py` (screen rendering/help/notices)
- Inspection operations: `core/cg/inspect_ops.py` (tree/output/workspace structure utilities)
- Diagnostics service: `core/cg/observability/doctor.py` (`cg doctor` checks and reporting)
- Shared utilities: `core/cg_utils/*` (cross-command reusable text/format helpers)
- Policy schema: `config/policy.json`
- Capability manifest: `config/capabilities.manifest.json`
- Native eval harness: `core/cg/addons/eval_harness.py` (`cg dev eval --suite core`)
- Release workflow scaffold: `.github/workflows/release.yml`
- Homebrew formula template: `packaging/homebrew/cad-guardian.rb`
- Marketplace base manifest: `packaging/marketplace/app-manifest.json`
- Marketplace release manifest generator: `packaging/marketplace/build_release_manifest.py`
- Generated release manifests: `packaging/marketplace/dist/app-manifest.json`, `packaging/marketplace/dist/app-manifest.release.json`
- Telemetry event log: `host_ai/logs/cg_events.jsonl`
- CLI color/style rules: `docs/CLI_COLOR_RULES.md`
- Full brand/design guide: `docs/BRAND_DESIGN_GUIDE.md`

## Marketplace Artifact Ingestion

Generate marketplace manifests locally after building artifacts:

```bash
python -m build
CG_BUILD_PROFILE=core python -m build --outdir dist-core
python packaging/marketplace/build_release_manifest.py --release-ref "local-build"
```

CI release workflow runs this automatically and uploads:

- Python artifacts from `dist/`
- Marketplace manifests from `packaging/marketplace/dist/*.json`
