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
cg snapshot-tests
```

### Homebrew-ready note

A formula template is included at:

- `agent/packaging/homebrew/cad-guardian.rb`

Replace `url` and `sha256` with your release artifact values before publishing a tap.

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
./cg.sh run "Check project files" --full-output
```

## Command Reference

| Command | What it does | Example |
|---|---|---|
| `cg run "<prompt>"` | Runs one agent request | `cg run "List files"` |
| `cg run "<prompt>" --full-output` | Same, but shows full answer/stdout/stderr | `cg run "Run tests" --full-output` |
| `cg ask "<question>"` | Read-only chat about current source/workspace state | `cg ask "What does main.py do?"` |
| `cg doctor` | Runs setup and environment diagnostics | `cg doctor` |
| `cg snapshot-tests` | Runs UI snapshot tests, saves report in workspace, opens/fallback previews report | `cg snapshot-tests` |
| `cg --help` | Shows help screen | `cg --help` |

> Note: in this setup you run through `./cg.sh`, which calls `python -m cg.main`.

## How CAD Guardian Works (Simple Flow)

1. Load policy from `agent/config/policy.json`
2. Read memory from Chroma
3. Send your request + memory to AI model
4. Receive JSON answer + plan
5. Show plan and answer
6. Execute safe actionable plan steps
7. Save interaction to memory

For `cg ask`, the app also builds a read-only runtime snapshot (file sample + key file previews) and sends it to the model for contextual answers.

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
| `execution_limits` | Cost and behavior limits (time, tokens, output, mode) |

## Execution Limits You Should Know

| Key | Meaning |
|---|---|
| `max_runtime_seconds` | Max seconds per command |
| `max_output_chars` | Max chars shown for stdout/stderr unless `--full-output` |
| `max_file_write_bytes` | Max bytes for one file write |
| `max_steps_per_plan` | Max AI plan steps kept |
| `max_completion_tokens` | Hard cap for model output tokens |
| `max_memory_items` | How many memory items are sent into prompt |
| `max_memory_chars` | Max memory text chars sent into prompt |
| `max_answer_chars` | Max answer chars shown unless `--full-output` |
| `max_answer_lines` | Max answer lines shown unless `--full-output` |
| `max_stdout_lines` | Max stdout lines shown unless `--full-output` |
| `max_stderr_lines` | Max stderr lines shown unless `--full-output` |
| `execution_mode` | `single_step` or `continue_until_done` |
| `max_actions_per_run` | Max actionable steps executed in one run |

## Architecture Map (User + Developer)

### Main runtime files

| File | Role |
|---|---|
| `agent/core/cg.sh` | Shell launcher |
| `agent/core/cg/main.py` | CLI flow, rendering, orchestration |
| `agent/core/cg/llm.py` | LLM request/response contract |
| `agent/core/cg/executor.py` | Policy enforcement for commands/writes |
| `agent/core/cg/policy.py` | Policy parsing + typed accessors |
| `agent/core/cg/memory.py` | Long-term memory store and retrieval |
| `agent/core/cg/paths.py` | Path resolution and environment roots |

### Data and config paths

| Path | Purpose |
|---|---|
| `agent/config/policy.json` | Safety + execution policy |
| `host_ai/memory/chroma` | Chroma persistent memory |
| `host_ai/logs` | Host-side logs/warnings |
| `agent/workspace` | Allowed primary working area |

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
| Too little output | Use `--full-output` or raise output limits |
| Too expensive | Lower `max_completion_tokens`, `max_memory_items`, `max_memory_chars` |

## Safe Defaults for Power Users

If you want useful but controlled behavior:

- Keep `execution_mode = "single_step"` while testing
- Keep `max_actions_per_run = 1` until confident
- Use `--full-output` only when debugging
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
