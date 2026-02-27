# Telemetry Schema

CAD Guardian writes structured events to:

- `host_ai/logs/cg_events.jsonl`

Each line is one JSON object.

## Core Fields

| Field | Type | Notes |
|---|---|---|
| `schema_version` | string | Current schema version (`1.1`) |
| `event_id` | string | Unique event ID (UUID) |
| `ts_utc` | string | ISO-8601 UTC timestamp |
| `session_id` | string | CLI process/session identifier |
| `run_id` | string | Unique invocation identifier |
| `command` | string | `run`, `ask`, `doctor`, `dev_snaps`, etc. |
| `route_mode` | string | `deterministic`, `llm`, or `n/a` |
| `handler_id` | string | Deterministic handler ID when used |
| `outcome` | string | `success`, `warn`, `fail`, `error`, etc. |
| `duration_ms` | integer | End-to-end command duration |
| `llm_used` | boolean | Whether LLM was called |
| `actionable_steps` | integer | LLM planned actionable steps |
| `executed_steps` | integer | Steps actually executed |
| `error_type` | string | Error class/category if any |
| `error_message` | string | Sanitized error summary |

## Safety

- Sensitive token patterns are redacted from string fields before writing.
- Event file rotates automatically when it reaches size limit.

## Aggregation

Use:

```bash
cg dev metrics --format json
cg dev metrics --format csv
```

Outputs are written under:

- `workspace/reports/metrics/<timestamp>/`
