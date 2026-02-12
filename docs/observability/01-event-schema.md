# 01 — Event Schema

## Canonical Event Fields

Every observability event stored in `obs_events` has these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uid` | UUID string | auto | Unique event identifier |
| `user_id` | int | yes | Owner (workspace) — FK to `users.id` |
| `agent_id` | int | no | Associated agent — FK to `agents.id` |
| `run_id` | UUID string | no | Groups events belonging to one pipeline execution |
| `event_type` | string | yes | One of the valid types below |
| `status` | string | yes | `success`, `error`, or `info` |
| `model` | string | no | LLM model identifier (e.g. `gpt-4o`) |
| `tokens_in` | int | no | Input/prompt tokens |
| `tokens_out` | int | no | Output/completion tokens |
| `cost_usd` | decimal(12,8) | no | Estimated cost (auto-calculated if pricing exists) |
| `latency_ms` | int | no | Wall-clock latency in milliseconds |
| `payload` | JSON | no | Flexible structured data (tool name, error details, etc.) |
| `dedupe_key` | string | no | Idempotency key — unique constraint prevents duplicates |
| `created_at` | datetime | auto | Event timestamp |

## Valid Event Types

```
run_started      — A new agent run begins
run_finished     — Agent run completes (status: success | error)
action_started   — An agent action is proposed
action_finished  — An agent action completes
tool_call        — A tool/function was invoked
tool_result      — A tool returned a result
llm_call         — An LLM API call was made
error            — A standalone error event
metric           — A custom metric datapoint
heartbeat        — Agent liveness signal
```

## Status Values

- `success` — Operation completed normally
- `error` — Operation failed
- `info` — Informational (heartbeats, run_started, etc.)

## Idempotency

If `dedupe_key` is provided, the system enforces uniqueness via a database constraint. Duplicate inserts are silently dropped. This enables safe retries from the SDK.

## Cost Calculation

When `cost_usd` is not provided and `tokens_in`, `model`, and `payload.provider` are present, the system auto-calculates cost from the `obs_llm_pricing` reference table.
