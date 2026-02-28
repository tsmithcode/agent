# Dashboard Add-on

## Purpose

Live observability UI for telemetry, memory, workspace, policy, and report health.

## Commands

- `cg dev dashboard --live --refresh-seconds 5 --port 8501 --event-limit 5000`

Authoritative command reference:

- [`docs/COMMAND_REFERENCE.md`](../../../docs/COMMAND_REFERENCE.md)

## Files

- `dashboard_app.py`: Streamlit UI
- `dashboard_data.py`: data loading + summarization

## Inputs

- workspace path
- logs directory (`cg_events.jsonl` source)
- chroma memory directory
- policy file path

## Outputs

- live dashboard UI
- optional user-goal summary based on memories

## Dependencies

- `streamlit`
- `pandas`
- `altair`

## Failure Behavior

- startup failures are written to dashboard log path
- CLI should report explicit restart/start errors and remediation commands

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Port already in use | stale Streamlit process | rerun `cg dev dashboard` (auto-restart behavior) |
| Dashboard fails immediately | dependency or runtime startup failure | check dashboard log path printed by CLI |
| Import path errors | outdated package/install state | reinstall editable package and rerun |
| Missing dashboard command | plugin/dependency contract unmet | run `cg doctor` and verify `dashboard` plugin contract |
