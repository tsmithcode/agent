# Command Reference (Core Profile)

This is the source-of-truth command set for the reduced LLM-only CAD Guardian core.

## Notes

- `cg` with no subcommand starts interactive loop mode when running in a terminal.
- `do`, `ask`, and `run` are all LLM-based in this profile.
- Deterministic routing, plugin-gated commands, and dashboard/eval add-ons are removed.

## Core Commands

| Command | Arguments | Flags | Behavior |
|---|---|---|---|
| `cg loop` | none | `--mode do|ask|run`, `--full`, `--ctx` | Interactive repeat-use loop with slash commands and easy exit. |
| `cg do` | `REQUEST` | `--full`, `--ctx` | Auto-routes to `ask` or `run`. |
| `cg run` | `PROMPT` | `--full` | LLM plans actions; executor runs policy-allowed steps. |
| `cg ask` | `QUESTION` | `--full`, `--ctx` | Read-only analysis over runtime snapshot + memory context. |
| `cg status` | none | `--limit` | Telemetry summary. |
| `cg doctor` | none | `--verbose` | Environment, policy, and memory diagnostics. |
| `cg setup` | none | `--doctor/--no-doctor` | First-run checks and quick next steps. |
| `cg inspect structure` | none | `-d` | Solution tree view. |
| `cg inspect workspace` | none | `-d` | Workspace file tree + summary. |
| `cg inspect outputs` | none | `-d` | Reports/logs/artifacts tree + summary. |
| `cg inspect loc` | none | none | Line count excluding workspace/log/cache/media/docs artifacts. |
| `cg policy show` | none | none | Show active policy controls and limits. |

## Loop Slash Commands

Inside `cg` or `cg loop`:

- `/help`
- `/mode ask|run|do`
- `/full on|off`
- `/ctx on|off`
- `/status [limit]`
- `/doctor`
- `/workspace`
- `/clear`
- `/exit` (or `exit`)
