# CAD Guardian

CAD Guardian is a policy-controlled AI CLI for power users.

It helps you:

- Ask over a live runtime snapshot of codebase/workspace (`cg ask`)
- Run safe, policy-governed actions (`cg run`) with deterministic auto-routing for obvious tasks
- Keep token/runtime costs bounded with explicit execution limits

## Install

### Option 1: Local editable install

```bash
cd /path/to/cad-guardian/agent
python -m pip install -e .
```

### Option 2: pipx (recommended for CLI)

```bash
cd /path/to/cad-guardian/agent
pipx install .
```

Then run:

```bash
cg --help
cg doctor
cg doctor --verbose
cg inspect structure
cg dev snaps
cg dev metrics --format json
cg dev dashboard --live --refresh-seconds 5
```

Routing behavior:

- `cg run` is deterministic-first for obvious operational prompts
- falls back to LLM for open-ended prompts
- examples:
  - `cg run "show files"` -> deterministic (no LLM)
  - `cg run "design architecture"` -> LLM

## Quick Usage

```bash
cg ask "What does this app do right now?"
cg run "List project files"
cg run "List project files" --full
cg inspect workspace
cg dev snaps
cg dev metrics --format csv
cg dev dashboard --live
```

## Dashboard UX

`cg dev dashboard` is optimized for readable enterprise reporting:

- Branded dark theme with high-contrast typography
- Fixed-position charts (non-zoom/non-pan) for consistent review screenshots
- Branded chart colors and larger chart axis labels
- Scrollable tables for high-volume sections
- Memory Health includes `Recent Memory Items` table
- Mobile/tablet responsive layout for stacked/wrapped sections

Example:

```bash
cg dev dashboard --live --refresh-seconds 5 --port 8501
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

- CLI entrypoint: `cg.main:cli`
- Main runtime: `core/cg/main.py`
- CLI view layer: `core/cg/cli_ui.py` (screen rendering/help/notices)
- Inspection operations: `core/cg/inspect_ops.py` (tree/output/workspace structure utilities)
- Diagnostics service: `core/cg/doctor.py` (`cg doctor` checks and reporting)
- Shared utilities: `core/cg_utils/*` (cross-command reusable text/format helpers)
- Policy schema: `config/policy.json`
- Release workflow scaffold: `.github/workflows/release.yml`
- Homebrew formula template: `packaging/homebrew/cad-guardian.rb`
- Marketplace base manifest: `packaging/marketplace/app-manifest.json`
- Marketplace release manifest generator: `packaging/marketplace/build_release_manifest.py`
- Generated release manifests: `packaging/marketplace/dist/app-manifest.json`, `packaging/marketplace/dist/app-manifest.release.json`
- Telemetry event log: `host_ai/logs/cg_events.jsonl`
- CLI color/style rules: `docs/CLI_COLOR_RULES.md`

## Marketplace Artifact Ingestion

Generate marketplace manifests locally after building artifacts:

```bash
python -m build
python packaging/marketplace/build_release_manifest.py --release-ref "local-build"
```

CI release workflow runs this automatically and uploads:

- Python artifacts from `dist/`
- Marketplace manifests from `packaging/marketplace/dist/*.json`
