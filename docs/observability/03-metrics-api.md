# 03 — Metrics & Query API

All metrics endpoints require session authentication (logged-in user).

## GET /api/obs/metrics/overview

Dashboard KPI summary. Returns real-time today stats and 7-day aggregated totals.

**Response:**
```json
{
  "today": {
    "cost_usd": 1.2345,
    "llm_calls": 42,
    "errors": 3,
    "total_events": 156
  },
  "week": {
    "cost_usd": 8.5,
    "total_runs": 280,
    "errors": 12
  },
  "active_agents_24h": 3,
  "unacknowledged_alerts": 1
}
```

## GET /api/obs/metrics/agents

Aggregated daily metrics for all agents. Used by the Agents Overview table.

**Query params:**
- `from` — Start date (YYYY-MM-DD, default: 7 days ago)
- `to` — End date (YYYY-MM-DD, default: today)

**Response:**
```json
{
  "metrics": [
    {
      "date": "2025-01-15",
      "agent_id": 1,
      "total_runs": 45,
      "successful_runs": 42,
      "failed_runs": 3,
      "success_rate": 0.9333,
      "error_rate": 0.0667,
      "total_tokens_in": 150000,
      "total_tokens_out": 80000,
      "total_cost_usd": 0.85,
      "latency_p50_ms": 800,
      "latency_p95_ms": 2500,
      "models_used": {"gpt-4o": 30, "gpt-4o-mini": 15}
    }
  ]
}
```

## GET /api/obs/metrics/agent/:id

Detailed metrics + recent events for a single agent.

**Query params:** `from`, `to` (same as above, default 30 days)

**Response:**
```json
{
  "agent": {"id": 1, "name": "Content Writer", ...},
  "metrics": [...],
  "recent_events": [...]
}
```

## GET /api/obs/events

Query raw events with filtering.

**Query params:**
- `agent_id` — Filter by agent
- `event_type` — Filter by type (e.g. `llm_call`)
- `status` — Filter by status (`success`, `error`, `info`)
- `run_id` — Filter by run
- `limit` — Max results (default 50, max 200)
- `offset` — Pagination offset

**Response:**
```json
{
  "events": [...],
  "total": 156,
  "limit": 50,
  "offset": 0
}
```

## GET /api/obs/pricing

List current LLM token pricing (no auth required).

```json
{
  "pricing": [
    {"provider": "openai", "model": "gpt-4o", "input_cost_per_mtok": 2.5, "output_cost_per_mtok": 10.0, ...}
  ]
}
```
