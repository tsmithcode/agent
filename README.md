# CAD Guardian

CAD Guardian is a policy-controlled AI CLI for power users.

It helps you:

- Ask questions about your live codebase in read-only mode (`cg ask`)
- Run safe, policy-governed actions (`cg run`)
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
cg snapshot-tests
```

## Quick Usage

```bash
cg ask "What does this app do right now?"
cg run "List project files"
cg run "List project files" --full
cg snapshot-tests
```

## Marketplace Description (Ready Copy)

**Title:** CAD Guardian — Safe AI Agent for Power Users

**Tagline:** Ask your live codebase questions and run policy-controlled actions from one CLI.

**Description:**
CAD Guardian is a local-first AI CLI for developers and operators who need useful automation without losing control.

- Read-only project Q&A with live snapshot context (`cg ask`)
- Policy-enforced execution for commands and file writes (`cg run`)
- Clear safety boundaries: allowlists, denied paths, network domain controls
- Cost controls: token, memory, output, and execution-step limits
- Built for practical workflows: transparent plans and predictable behavior

## Developer Notes

- CLI entrypoint: `cg.main:cli`
- Main runtime: `core/cg/main.py`
- Policy schema: `config/policy.json`
- Release workflow scaffold: `.github/workflows/release.yml`
- Homebrew formula template: `packaging/homebrew/cad-guardian.rb`
