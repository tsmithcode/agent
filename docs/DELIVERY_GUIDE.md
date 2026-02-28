# CAD Guardian Core Delivery, Install, and Update Guide

This guide covers install/update/uninstall for the reduced LLM-only core profile.

## What Changed

- Core profile only (no plugin system).
- No dashboard/eval/snapshot/fetch add-on commands.
- Deterministic router removed; `ask/run/do` are LLM-based.

## Install (pipx)

```bash
pipx install cad-guardian
cg setup
```

If `pipx` is not installed:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

## Update

```bash
pipx upgrade cad-guardian
```

If installed in a venv:

```bash
pip install --upgrade cad-guardian
```

## Uninstall

### pipx

```bash
pipx uninstall cad-guardian
```

### venv/pip

```bash
pip uninstall cad-guardian
```

## Validation Checklist

Run these after install/update:

```bash
cg setup
cg doctor
cg do "summarize this workspace"
cg status --limit 100
```

## Notes

- Do not ship API keys; user sets `OPENAI_API_KEY` locally.
- `cg` (no subcommand) starts interactive loop mode in terminal.
- Policy controls still enforce command/path/network/runtime boundaries.
