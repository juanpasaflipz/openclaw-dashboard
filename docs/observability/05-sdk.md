# 05 — Internal SDK (Python)

The observability SDK is a Python module (`observability_service.py`) used by the application to emit events without external HTTP calls.

## Core Functions

### emit_event()

```python
from observability_service import emit_event

emit_event(
    user_id=1,
    event_type='llm_call',
    status='success',
    agent_id=1,
    run_id='uuid-string',
    model='gpt-4o',
    tokens_in=1500,
    tokens_out=800,
    cost_usd=0.0105,
    latency_ms=1200,
    payload={'provider': 'openai'},
    dedupe_key='unique-idempotency-key',
)
```

**Never raises.** Errors are swallowed and logged to stderr. This ensures observability never breaks the main application flow.

### start_run() / finish_run()

```python
from observability_service import start_run, finish_run

run_id = start_run(user_id=1, agent_id=1, model='gpt-4o', metadata={'source': 'chat'})

# ... do work ...

finish_run(
    run_id=run_id,
    status='success',  # or 'error'
    tokens_in=3000,
    tokens_out=1500,
    cost_usd=0.025,
    latency_ms=2500,
    tool_calls=2,
)
```

`start_run()` creates an `ObsRun` record and emits a `run_started` event.
`finish_run()` updates the run record and emits a `run_finished` event.

### calculate_cost()

```python
from observability_service import calculate_cost

cost = calculate_cost('openai', 'gpt-4o', tokens_in=1000, tokens_out=500)
# Returns float (USD), e.g. 0.0075
```

Uses the `obs_llm_pricing` table with a 5-minute in-memory cache. Returns 0.0 if no pricing found.

### aggregate_daily()

```python
from observability_service import aggregate_daily
from datetime import date

rows = aggregate_daily(date.today())
# Returns count of (user, agent, day) tuples aggregated
```

Reads raw events, computes metrics (runs, tokens, cost, latency percentiles), and upserts into `obs_agent_daily_metrics`. Idempotent — safe to run multiple times.

### evaluate_alerts()

```python
from observability_service import evaluate_alerts

fired = evaluate_alerts()
# Returns count of alerts fired
```

## LLM Hook Pattern

The chatbot pipeline instruments LLM calls via a hook on `LLMService`:

```python
def _llm_obs_hook(provider, model, usage, latency_ms, success, error_msg):
    emit_event(user_id, 'llm_call', ...)

LLMService._obs_hook = _llm_obs_hook
try:
    result = LLMService.call(...)
finally:
    LLMService._obs_hook = None
```

The hook is called in `LLMService.call()`'s `finally` block, ensuring it fires even on error. The hook is set per-request and cleared afterward to avoid cross-request leakage.

## Design Principles

1. **Fire-and-forget** — All SDK calls swallow exceptions
2. **No external dependencies** — Direct DB writes (no queue, no Redis)
3. **Idempotent** — dedupe_key prevents duplicate events on retry
4. **Zero overhead on failure** — If DB is down, events are silently dropped
5. **Incremental** — Existing code paths are minimally modified
