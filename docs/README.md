# CAD Guardian User Guide

CAD Guardian is a smart helper that can read, plan, and do safe actions on your computer workspace.

This guide is written so a young beginner can follow it, but it also maps to the real code so developers can use it as a technical reference.

## What CAD Guardian Does

CAD Guardian can:

- Read your request
- Make a short plan
- Do safe file writes and safe terminal commands
- Save memory from each run
- Follow your safety policy in `agent/config/policy.json`

CAD Guardian does **not** run forever on its own. It runs when you ask it to run.

Core product intent:

- Ask over a live runtime snapshot of codebase/workspace
- Run policy-controlled actions from one CLI

## Before You Start

| Item | Why you need it |
|---|---|
| Python virtual environment | Runs the app dependencies |
| `OPENAI_API_KEY` | Lets the app talk to the AI model |
| Policy file | Defines safety rules and limits |

## Install (Distribution Ready)

### pipx (recommended)

```bash
cd /home/cg-ai/agent
pipx install .
```

### pip editable install

```bash
cd /home/cg-ai/agent
python -m pip install -e .
```

After install:

```bash
cg --help
cg doctor
cg inspect structure
cg dev snaps
cg dev metrics --format json
cg dev dashboard --live --refresh-seconds 5
```

### Homebrew-ready note

A formula template is included at:

- `agent/packaging/homebrew/cad-guardian.rb`

Replace `url` and `sha256` with your release artifact values before publishing a tap.

### Marketplace manifest (ingestion-ready)

Base manifest:

- `agent/packaging/marketplace/app-manifest.json`

Generated release manifests:

- `agent/packaging/marketplace/dist/app-manifest.json`
- `agent/packaging/marketplace/dist/app-manifest.release.json`

Generate locally:

```bash
cd /home/cg-ai/agent
python -m build
python packaging/marketplace/build_release_manifest.py --release-ref "local-build"
```

CI release workflow generates and uploads these automatically on build/tag pipelines.

## Quick Start

1. Open terminal.
2. Go to app core folder:

```bash
cd /home/cg-ai/agent/core
```

3. Run help:

```bash
./cg.sh --help
```

4. Run a task:

```bash
./cg.sh run "Create a simple README in my workspace"
```

5. If you want full output (no display truncation):

```bash
./cg.sh run "Check project files" --full
```

## Command Reference

| Command | What it does | Example |
|---|---|---|
| `cg run "<prompt>"` | Runs one agent request | `cg run "List files"` |
| `cg run "<prompt>" --full` | Same, but shows full answer/stdout/stderr | `cg run "Run tests" --full` |
| `cg ask "<question>"` | Read-only chat about current source/workspace state | `cg ask "What does main.py do?"` |
| `cg doctor` | Runs setup and environment diagnostics | `cg doctor` |
| `cg doctor --verbose` | Shows full path inventory and expanded diagnostics | `cg doctor --verbose` |
| `cg inspect structure` | Shows solution tree (default depth 4) | `cg inspect structure -d 4` |
| `cg inspect workspace` | Shows workspace tree | `cg inspect workspace` |
| `cg inspect outputs` | Shows reports/logs/artifacts trees | `cg inspect outputs` |
| `cg dev snaps` | Runs UI snapshot tests, saves report in workspace, opens/fallback previews report | `cg dev snaps` |
| `cg dev metrics` | Aggregates JSONL telemetry to BI-ready summary report (`json` or `csv`) | `cg dev metrics --format csv` |
| `cg dev dashboard` | Launches live dashboard (telemetry, memory, workspace, policy, reports) | `cg dev dashboard --live` |
| `cg --help` | Shows help screen | `cg --help` |

> Note: in this setup you run through `./cg.sh`, which calls `python -m cg.main`.

Routing quick note:

- `cg run "show files"` routes to deterministic handler (no LLM)
- `cg run "design architecture"` routes to LLM fallback

### Dashboard behavior

`cg dev dashboard` now includes:

- Branded dark, high-contrast visuals
- Locked charts (no zoom/pan) for stable review views
- Larger chart label fonts for readability
- Scrollable tables/data grids to reduce page bloat
- Memory Health `Recent Memory Items` table
- Responsive layout across desktop/tablet/mobile

## How CAD Guardian Works (Simple Flow)

1. Load policy from `agent/config/policy.json`
2. Read memory from Chroma
3. Send your request + memory to AI model
4. Receive JSON answer + plan
5. Show plan and answer
6. Execute safe actionable plan steps
7. Save interaction to memory

For `cg ask`, the app builds a read-only runtime snapshot (file sample + git status) and sends it to the model for contextual answers.

`cg ask` is for understanding current state.
`cg run` is for file/folder operations and batch workflows inside workspace.

For `cg run`, routing is deterministic-first:

1. If prompt is an obvious operational request, run native deterministic handler
2. Otherwise route to LLM planning/execution flow

Execution transparency:

- CAD Guardian prints `Route Decision` (deterministic vs LLM) and `Answer Path` (`command`, `llm`, or `both`)

Batch apply confirmation:

- apply-style requests require explicit `confirm:yes` in the prompt
- without `confirm:yes`, the plan is shown but execution is blocked

Memory is tagged by kind to improve retrieval quality:

- `preferences`
- `user_profile`
- `workflow_pattern`
- `task_result`
- `interaction`

## Standard Batch Workflow

Use this sequence for bulk file operations:

1. Scan
2. Propose (dry-run plan)
3. Confirm
4. Apply
5. Log

Example:

- Download content into `workspace`
- Scan filenames/metadata
- Propose normalization plan
- Wait for explicit user confirmation
- Apply file/tag changes
- Save structured report in `workspace/reports`

## Safety Rules (Policy)

Your policy file is at:

- `agent/config/policy.json`

### Core safety areas

| Policy area | Purpose |
|---|---|
| `allowed_write_roots` | Where files may be written |
| `allowed_read_roots` | Where command working directories may run |
| `denied_paths` | Never allow reads/writes/execution context there |
| `command_allowlist` | Allowed command names |
| `command_denylist` | Explicitly blocked command names |
| `destructive_command_controls` | Extra guard rails for destructive patterns and `rm` |
| `git_controls` | Restricts risky git actions |
| `network_controls` | Restricts outbound HTTP domains |
| `routing_controls` | Controls deterministic-first routing behavior for `cg run` |
| `execution_limits` | Cost and behavior limits (time, tokens, output, mode) |

## Execution Limits You Should Know

| Key | Meaning |
|---|---|
| `max_runtime_seconds` | Max seconds per command |
| `max_output_chars` | Max chars shown for stdout/stderr unless `--full` |
| `max_file_write_bytes` | Max bytes for one file write |
| `max_steps_per_plan` | Max AI plan steps kept |
| `max_completion_tokens` | Hard cap for model output tokens |
| `max_memory_items` | How many memory items are sent into prompt |
| `max_memory_chars` | Max memory text chars sent into prompt |
| `max_answer_chars` | Max answer chars shown unless `--full` |
| `max_answer_lines` | Max answer lines shown unless `--full` |
| `max_stdout_lines` | Max stdout lines shown unless `--full` |
| `max_stderr_lines` | Max stderr lines shown unless `--full` |
| `execution_mode` | `single_step` or `continue_until_done` |
| `max_actions_per_run` | Max actionable steps executed in one run |

## Architecture Map (User + Developer)

### Main runtime files

| File | Role |
|---|---|
| `agent/core/cg.sh` | Shell launcher |
| `agent/core/cg/main.py` | CLI flow, rendering, orchestration |
| `agent/core/cg/cli_ui.py` | CLI presentation layer (help, notices, route/answer panels) |
| `agent/core/cg/llm.py` | LLM request/response contract |
| `agent/core/cg/executor.py` | Policy enforcement for commands/writes |
| `agent/core/cg/policy.py` | Policy parsing + typed accessors |
| `agent/core/cg/memory.py` | Long-term memory store and retrieval |
| `agent/core/cg/paths.py` | Path resolution and environment roots |
| `agent/core/cg/inspect_ops.py` | Structure/workspace/output inspection utilities |
| `agent/core/cg/doctor.py` | Diagnostic checks service used by `cg doctor` |
| `agent/core/cg_utils/text.py` | Shared utility helpers (truncate/cap logic) |

### Data and config paths

| Path | Purpose |
|---|---|
| `agent/config/policy.json` | Safety + execution policy |
| `host_ai/memory/chroma` | Chroma persistent memory |
| `host_ai/logs` | Host-side logs/warnings |
| `host_ai/logs/cg_events.jsonl` | Structured command telemetry event stream |
| `agent/workspace` | Allowed primary working area |

Telemetry schema reference:

- `agent/docs/TELEMETRY_SCHEMA.md`
- `agent/docs/CLI_COLOR_RULES.md`

## JSON Contract from AI (Important)

The AI must return one JSON object:

```json
{
  "answer": "string",
  "plan": [
    {"type": "cmd", "value": "..."},
    {"type": "write", "path": "relative/path", "value": "..."},
    {"type": "note", "value": "..."}
  ]
}
```

## Typical Output Screens

| Screen title | Meaning |
|---|---|
| `CAD Guardian Agent` | Input prompt + memory summary |
| `Execution Plan` | Steps the model proposed |
| `Answer` | Short response to the user |
| `stdout` / `stderr` | Command output panels |
| `Command Required` | You ran `cg` without a command |
| `Unknown Command: ...` | You passed an unsupported command |

## Troubleshooting

| Problem | What to check |
|---|---|
| `OPENAI_API_KEY not set` | Set environment variable and retry |
| `LLM ERROR Connection error` | Check internet/DNS and outbound access to `api.openai.com` |
| Command blocked | Check `command_allowlist`, `command_denylist`, and safety controls |
| Path blocked | Check `allowed_*_roots` and `denied_paths` |
| Too little output | Use `--full` or raise output limits |
| Too expensive | Lower `max_completion_tokens`, `max_memory_items`, `max_memory_chars` |

## Safe Defaults for Power Users

If you want useful but controlled behavior:

- Keep `execution_mode = "single_step"` while testing
- Keep `max_actions_per_run = 1` until confident
- Use `--full` only when debugging
- Start with low `max_completion_tokens` and raise gradually

## For Developers: Where to Add Features

| Goal | File to edit |
|---|---|
| New CLI flags/commands | `agent/core/cg/main.py` |
| Change model behavior | `agent/core/cg/llm.py` |
| Add policy rule enforcement | `agent/core/cg/executor.py` and `agent/core/cg/policy.py` |
| Memory strategy tuning | `agent/core/cg/memory.py` |
| Environment/path behavior | `agent/core/cg/paths.py` |

## One-Page Memory Trick (For Kids)

Remember CAD Guardian as:

- **Ask**: “Do this task”
- **Plan**: It makes steps
- **Check**: Policy says what is safe
- **Do**: It runs safe steps
- **Save**: It remembers what happened

That is the full loop.
