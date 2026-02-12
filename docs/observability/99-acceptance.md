# 99 — Acceptance Checklist

## Data Layer

- [x] 7 new `obs_` tables added to `models.py`
- [x] Alembic migration `008_add_observability.py` created
- [x] All tables have proper indexes (uid, run_id, created_at, composite)
- [x] `dedupe_key` unique constraint for idempotency
- [x] `ObsAgentDailyMetrics` has composite unique on (user_id, agent_id, date)
- [x] Foreign keys to `users` and `agents` tables
- [x] `ObsApiKey` stores SHA-256 hash (raw key never persisted)

## Ingestion API

- [x] `POST /api/obs/ingest/events` accepts single and batch events
- [x] Bearer API key authentication
- [x] Event type validation against allowed set
- [x] Max 1000 events per batch request
- [x] Dedupe key prevents duplicate insertion
- [x] Partial failures handled gracefully (accepted + rejected counts)
- [x] `POST /api/obs/ingest/heartbeat` validates agent ownership

## Metrics & Query

- [x] `GET /api/obs/metrics/overview` returns real-time today + 7-day aggregated stats
- [x] `GET /api/obs/metrics/agents` returns daily metrics with date range filter
- [x] `GET /api/obs/metrics/agent/:id` returns detail + recent events
- [x] `GET /api/obs/events` supports filtering by agent_id, event_type, status, run_id
- [x] Pagination with limit/offset
- [x] All metrics endpoints require session auth

## Aggregation

- [x] `aggregate_daily()` computes: total_runs, success/failed, tokens, cost, latency percentiles
- [x] Upsert logic (idempotent — safe to re-run)
- [x] Models used tracking (JSON field)
- [x] Vercel cron job configured for hourly aggregation
- [x] Aggregates both today and yesterday (catch missed runs)

## Alerts

- [x] Three rule types: `cost_per_day`, `error_rate`, `no_heartbeat`
- [x] CRUD endpoints for alert rules
- [x] Cooldown prevents repeated firing
- [x] Slack webhook notification (when SLACK_WEBHOOK_URL set)
- [x] Alert event history with acknowledge
- [x] Vercel cron job configured for 15-minute evaluation

## SDK / Instrumentation

- [x] `observability_service.py` with emit_event, start_run, finish_run, calculate_cost
- [x] All SDK functions are fire-and-forget (never raise)
- [x] LLM calls instrumented via `_obs_hook` on `LLMService`
- [x] Tool executions instrumented in chatbot pipeline
- [x] Run tracking (start → accumulate → finish)
- [x] Cost auto-calculation from pricing table

## UI

- [x] Observability tab accessible from Workbench dropdown
- [x] KPI cards: cost, calls, errors, active agents, alerts
- [x] Agents Overview table with key metrics
- [x] Agent Detail panel with Canvas line charts
- [x] Events Log with type/status filters
- [x] Alert Rules management (create, toggle, delete)
- [x] Alert Events history with acknowledge
- [x] API Key management (create, list, revoke)

## Demo & Seed

- [x] `scripts/seed_observability.py` — pricing, agents, API key
- [x] `scripts/generate_demo_events.py` — 24h synthetic data
- [x] Demo script triggers aggregation after generation

## Tests

- [x] API key create/lookup/revoke
- [x] Ingestion: single, batch, invalid type, auth, max limit, dedupe
- [x] Heartbeat: valid, missing agent, wrong user
- [x] Metrics: auth required, response structure, agent detail
- [x] Events query: auth, empty, filters
- [x] Alert rules: create, invalid type, list, toggle, delete
- [x] Alert evaluation: cost fires, error rate fires, no heartbeat fires, cooldown
- [x] Aggregation: correct metrics, idempotent
- [x] Cost calculation: with pricing, unknown model
- [x] Pricing endpoint

## Documentation

- [x] `docs/observability/00-current-state.md` — Architecture audit
- [x] `docs/observability/01-event-schema.md` — Event fields and types
- [x] `docs/observability/02-ingestion-api.md` — Ingestion endpoints
- [x] `docs/observability/03-metrics-api.md` — Metrics and query endpoints
- [x] `docs/observability/04-alerts.md` — Alert system
- [x] `docs/observability/05-sdk.md` — Internal Python SDK
- [x] `docs/observability/06-ui.md` — Dashboard UI
- [x] `docs/observability/07-demo.md` — Demo setup guide
- [x] `docs/observability/99-acceptance.md` — This checklist

## Environment

- [x] `.env.example` updated with `CRON_SECRET` and `SLACK_WEBHOOK_URL`
- [x] `vercel.json` updated with cron jobs
- [x] Blueprint registered in `server.py`
- [x] No new pip dependencies required
- [x] Compatible with existing SQLite (local) and PostgreSQL (production)

## Files Created / Modified

### New Files (12)
| File | Purpose |
|------|---------|
| `observability_service.py` | Core service module |
| `routes/observability_routes.py` | API Blueprint |
| `alembic/versions/008_add_observability.py` | Migration |
| `scripts/seed_observability.py` | Seed script |
| `scripts/generate_demo_events.py` | Demo data generator |
| `tests/test_observability.py` | Test suite |
| `docs/observability/00-current-state.md` | Arch audit |
| `docs/observability/01-event-schema.md` | Schema docs |
| `docs/observability/02-ingestion-api.md` | Ingestion docs |
| `docs/observability/03-metrics-api.md` | Metrics docs |
| `docs/observability/04-alerts.md` | Alerts docs |
| `docs/observability/05-sdk.md` | SDK docs |
| `docs/observability/06-ui.md` | UI docs |
| `docs/observability/07-demo.md` | Demo guide |
| `docs/observability/99-acceptance.md` | This checklist |

### Modified Files (7)
| File | Change |
|------|--------|
| `models.py` | Added 7 Obs* model classes |
| `server.py` | Registered obs_bp Blueprint |
| `routes/__init__.py` | Added obs_bp import |
| `llm_service.py` | Added _obs_hook + timing in call() |
| `routes/chatbot_routes.py` | Instrumented run tracking + tool events |
| `dashboard.html` | Added Observability tab + HTML content |
| `static/js/dashboard-main.js` | Added obs* JS functions |
| `vercel.json` | Added cron jobs |
| `.env.example` | Added CRON_SECRET, SLACK_WEBHOOK_URL |
