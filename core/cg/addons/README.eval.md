# Eval Harness Add-on

## Purpose

Runs native benchmark suites to validate task success behavior.

## Commands

- `cg dev eval --suite core`

Authoritative command reference:

- [`docs/COMMAND_REFERENCE.md`](../../../docs/COMMAND_REFERENCE.md)

## Files

- `eval_harness.py`: case execution and report generation

## Inputs

- current policy
- deterministic router behavior
- expected handlers

## Outputs

- eval report JSON written under workspace reports
- pass/fail summary shown in CLI

## Notes

- Keep eval suites deterministic and lightweight for CI and local smoke checks.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `dev eval` command missing | eval plugin disabled or contract unmet | run `cg doctor`, enable plugin in `config/plugins.json`, install required deps |
| suite rejected | unsupported suite value | use `--suite core` |
| report not created | write path or runtime failure | verify workspace permissions with `cg doctor` and rerun |
