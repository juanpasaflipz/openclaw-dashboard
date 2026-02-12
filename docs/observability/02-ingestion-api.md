# 02 — Ingestion API

All ingestion endpoints are authenticated via Bearer API key (not session auth).

## Authentication

```
Authorization: Bearer obsk_<hex>
```

API keys are created via the dashboard UI or `POST /api/obs/api-keys` (session auth required). Keys are stored as SHA-256 hashes; the raw key is shown only once at creation.

## POST /api/obs/ingest/events

Ingest one or more events.

**Single event:**
```json
{
  "event_type": "llm_call",
  "status": "success",
  "agent_id": 1,
  "model": "gpt-4o",
  "tokens_in": 1500,
  "tokens_out": 800,
  "latency_ms": 1200,
  "payload": {"provider": "openai"}
}
```

**Batch (up to 1000):**
```json
{
  "events": [
    {"event_type": "llm_call", "status": "success", ...},
    {"event_type": "tool_call", "status": "success", ...}
  ]
}
```

**Response:**
```json
{
  "accepted": 2,
  "rejected": [],
  "total_submitted": 2
}
```

Rejected events include an index and reason:
```json
{"rejected": [{"index": 0, "reason": "invalid event_type 'foo'"}]}
```

## POST /api/obs/ingest/heartbeat

Lightweight agent liveness check.

**Request:**
```json
{
  "agent_id": 1,
  "status": "alive",
  "metadata": {"version": "1.2.0"}
}
```

**Response:**
```json
{"success": true, "agent_id": 1, "ts": "2025-01-15T12:00:00"}
```

## Error Handling

| Status | Meaning |
|--------|---------|
| 200 | Events accepted (check `rejected` array for partial failures) |
| 400 | Malformed request (no JSON, >1000 events, etc.) |
| 401 | Missing or invalid API key |
| 404 | Agent not found (heartbeat only) |

## Rate Limits

Standard Flask-Limiter rates apply. The ingestion endpoints are designed for moderate throughput (hundreds of events/minute). For high-volume scenarios, use batch ingestion.
