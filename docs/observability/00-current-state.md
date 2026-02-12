# 00 — Current Architecture Summary

## Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Runtime | **Flask 3.0** (Python 3.13) | Single WSGI app, all routes registered in `server.py` |
| Database | **Neon PostgreSQL 17** (prod) / SQLite (dev) | SQLAlchemy ORM, Alembic migrations |
| ORM | **Flask-SQLAlchemy 3.0.5** | 18 model classes in `models.py` (698 lines) |
| Migrations | **Alembic 1.13.1** | Manual version numbering: 002, 004, 006. `alembic/env.py` imports Flask app context |
| Auth | **Session-based** | Magic-link email via SendGrid. `session['user_id']` checked at every endpoint |
| Payments | **Stripe 6.6.0** | Free + Pro ($15/mo). Credit packs for Moltbook posts. Webhook handler |
| Deployment | **Vercel** (`@vercel/python`) | Serverless. No persistent processes. Max 60s per invocation |
| Frontend | **Vanilla JS** | Single `dashboard.html` (~2000 lines), `static/js/dashboard-main.js` (~5000+ lines). No build step |
| Rate limiting | **Flask-Limiter 3.5.0** | Memory storage (no Redis in prod). 1000/hr, 100/min defaults |
| LLM | **`llm_service.py`** | 12 providers (OpenAI, Anthropic, Google, Groq, Mistral, Ollama, Together, xAI, OpenRouter, Cohere, Azure, Custom) |
| Tools | **`agent_tools.py`** | 14+ write tools (email, calendar, tasks, etc). OpenAI function-calling schema |

## Directory Layout (app code only, excludes venv/docs/node_modules)

```
server.py                    — App entry point, route registration, admin endpoints
models.py                    — All 18 SQLAlchemy models
llm_service.py               — LLMService class, provider dispatch
agent_tools.py               — Tool registry + executors
binance_service.py           — Binance exchange client
rate_limiter.py              — Flask-Limiter setup
dashboard.html               — Entire frontend UI
static/js/dashboard-main.js  — All frontend logic
vercel.json                  — Vercel deployment config
requirements.txt             — Python dependencies
alembic/                     — Migration framework
  env.py                     — Alembic-Flask integration
  versions/002,004,006.py    — Existing migrations
routes/                      — 28 route modules
  __init__.py                — Imports all route registrars
  auth_routes.py             — Magic link auth
  stripe_routes.py           — Subscriptions + credits
  analytics_routes.py        — Moltbook-only analytics (3 endpoints)
  chatbot_routes.py          — Chat + LLM pipeline with tool loop
  agent_routes.py            — Agent CRUD
  agent_actions_routes.py    — Approval queue
  channels_routes.py         — Telegram/Discord channel integration
  llm_providers_routes.py    — Provider config UI data
  model_config_routes.py     — Per-user LLM config
  external_agents_routes.py  — Third-party agent registration
  gmail_routes.py            — Gmail superpower
  calendar_routes.py         — Calendar superpower
  drive_routes.py            — Drive superpower
  notion_routes.py           — Notion superpower
  binance_routes.py          — Binance superpower
  binance_actions_routes.py  — Binance action execution
  oauth_routes.py            — OAuth flows (Google, Slack, GitHub, etc.)
  slack_routes.py            — Slack integration
  github_routes.py           — GitHub integration
  discord_routes.py          — Discord integration
  telegram_routes.py         — Telegram bot integration
  spotify_routes.py          — Spotify integration
  todoist_routes.py          — Todoist integration
  dropbox_routes.py          — Dropbox integration
  web_browsing_routes.py     — Web search/scrape
  utility_routes.py          — Misc utilities
  setup_routes.py            — Onboarding
  moltbook_routes.py         — Moltbook social network API
tests/
  conftest.py                — Fixtures (app, client, user, agent, etc.)
  test_auth.py               — Auth tests
  test_stripe_webhooks.py    — Stripe webhook tests
```

## Existing Data Model (18 tables)

**Core:** User, MagicLink, Agent, ConfigFile
**Billing:** CreditTransaction, CreditPackage, SubscriptionPlan, PostHistory
**Chat:** ChatConversation, ChatMessage, UserModelConfig
**Integrations:** Superpower (OAuth tokens), ExternalAgent, WebBrowsingResult
**Agent Actions:** AgentAction (approval queue)
**Moltbook Analytics:** AnalyticsSnapshot, PostAnalytics, MoltbookFeedCache, UserUpvote

## What's Tracked Today vs. What's Missing

| Dimension | Currently tracked | Gap |
|-----------|------------------|-----|
| LLM calls | Token counts saved in ChatMessage.metadata_json | No time-series. No cost. No latency. No per-provider breakdown. |
| Tool executions | Tool results saved as ChatMessage (role='tool') | No success/failure rates. No latency. No aggregate stats. |
| Agent actions | AgentAction table: created_at, approved_at, executed_at | No aggregate metrics. No time-to-approve calculation. |
| Service health | Superpower: usage_count, last_error | No time-series. No error rates. No SLA tracking. |
| Costs | Zero | Nothing. Users have no idea what they're spending on LLM calls. |
| Alerting | Zero | No rules, no notifications, no budget alerts. |
| Analytics UI | Moltbook-only (karma, posts) | Only 3 endpoints. Pro-gated. Only for Moltbook social metrics. |

## Route Registration Pattern

Two styles coexist:
1. **Function registrar:** `register_X_routes(app)` — function adds routes directly to app
2. **Blueprint:** `analytics_bp = Blueprint(...)` — registered via `app.register_blueprint()`

Both are used. New observability routes should use **Blueprint** for namespace isolation (`/api/obs/...`).

## Migration Pattern

Alembic with manual version numbers. Latest = `006`. Import chain: `env.py` → `server.py` → `models.py`.
New migration should be `008_add_observability.py` (keeping the even-number pattern).

## Test Pattern

pytest with session-scoped app fixture, function-scoped client. SQLite temp DB. `_clean_db` autouse fixture truncates all tables between tests. Rate limiter disabled in tests.

## Deployment Constraints

- **Vercel serverless:** No background processes. Max 60s function execution. Cold starts.
- **Vercel cron:** Supported via `vercel.json` `crons` field. Minimum 1-hour interval on Hobby plan, 1-minute on Vercel Pro.
- **No Redis in production.** Rate limiter uses memory storage (per-invocation, not shared).
- **Connection pool:** 5 + 10 overflow, 5-min recycle, pre-ping for SSL drops.
- **PUT requests unreliable on Vercel** — existing code prefers POST.

## Safest Extension Points

1. **New route file:** `routes/observability_routes.py` registered as Blueprint — zero risk to existing code
2. **New models in `models.py`:** Append new classes at bottom — no impact on existing tables
3. **New Alembic migration:** `008_add_observability.py` — additive only (CREATE TABLE)
4. **Instrumentation in `llm_service.py`:** Wrap `LLMService.call()` return path — measure after call completes
5. **Instrumentation in `chatbot_routes.py`:** Wrap `execute_tool()` in `run_llm_pipeline()` — add timing
6. **New service module:** `observability_service.py` — event emission, cost calculation, aggregation
7. **Vercel cron in `vercel.json`:** Add `crons` array — no impact on existing routes
8. **Frontend:** Add new tab in `dashboard.html` + JS section in `dashboard-main.js`

---

# Recommended Plan

## v1 — Core Observability (this implementation)

End-to-end: schema + ingestion + processing + alerts + SDK + minimal UI.

### Files to create
| File | Purpose |
|------|---------|
| `observability_service.py` | Event emission, cost calc, aggregation logic, alert evaluation |
| `routes/observability_routes.py` | All observability API endpoints (Blueprint: `/api/obs/...`) |
| `alembic/versions/008_add_observability.py` | Migration: 7 new tables |
| `scripts/seed_observability.py` | Seed workspace, agents, API key, pricing |
| `scripts/generate_demo_events.py` | Generate 24h of synthetic events |
| `tests/test_observability.py` | Ingestion validation, aggregation correctness, alert evaluation |
| `docs/observability/01-event-schema.md` | Event schema documentation |
| `docs/observability/02-ingestion-api.md` | Ingestion API docs + curl examples |
| `docs/observability/03-metrics.md` | Metrics/aggregation docs |
| `docs/observability/04-alerts.md` | Alert system docs |
| `docs/observability/05-sdk.md` | SDK/instrumentation docs |
| `docs/observability/06-ui.md` | UI docs |
| `docs/observability/07-demo.md` | Demo/seed docs |
| `docs/observability/99-acceptance.md` | Acceptance checklist |

### Files to modify
| File | Change | Risk |
|------|--------|------|
| `models.py` | Append 7 new model classes (~200 lines) | None — additive only |
| `server.py` | Register new Blueprint + cron endpoints (~10 lines) | Minimal — one import + one register call |
| `llm_service.py` | Add timing + event hook around `call()` (~15 lines) | Low — wraps return path, never blocks |
| `routes/chatbot_routes.py` | Add tool timing in `run_llm_pipeline()` (~10 lines) | Low — wraps existing execute_tool |
| `vercel.json` | Add `crons` array | None — new field |
| `.env.example` | Add `CRON_SECRET`, `SLACK_WEBHOOK_URL` | None — documentation only |
| `requirements.txt` | No new deps needed (stdlib uuid, hashlib, json, time) | None |
| `routes/__init__.py` | Import new Blueprint | Minimal — one line |
| `dashboard.html` | Add Observability tab | Low — appended to existing tabs |
| `static/js/dashboard-main.js` | Add observability JS section | Low — appended |

### New tables (7)
1. `obs_events` — Append-only event log (JSONB metadata)
2. `obs_api_keys` — API keys for ingestion auth (tied to user_id)
3. `obs_runs` — Run tracking (start/end, status, cost)
4. `obs_agent_daily_metrics` — Pre-aggregated daily metrics per agent
5. `obs_alert_rules` — User-defined alert rules
6. `obs_alert_events` — Fired alert history
7. `obs_llm_pricing` — Cost reference data (provider + model → cost per token)

### Key decisions
- **`workspace_id` = `user_id`** for v1. Single-user workspace. Real multi-tenant workspaces deferred to v2.
- **`agent_id`** = existing `Agent.id` from the agents table. No new agent table.
- **All new tables prefixed `obs_`** to avoid collisions and make the subsystem clearly identifiable.
- **Blueprint at `/api/obs/`** for clear namespace separation.
- **Ingestion auth via Bearer API key** (separate from session auth) to support external agent SDKs.
- **Aggregation: hybrid** — Vercel cron for daily rollups, on-demand for recent data queries.
- **Alerts: cron-driven evaluation** with Slack webhook + in-app notification stubs.
- **SDK: Python module** (`observability_service.py`) with `emit_event()`, `track_llm_call()` context manager, and `@track_service_call` decorator. Also serves as the "SDK" for this Flask app.

## v1.1 — Deferred Enhancements
- Real-time dashboard (polling every 30s)
- Cost forecast (7-day rolling average projection)
- Data retention enforcement via cron
- Email alert notifications via SendGrid
- Export API (CSV/JSON)

## v2 — Future
- Multi-tenant workspaces with team RBAC
- Custom dashboards
- Business + Enterprise pricing tiers
- Distributed tracing (request → LLM → tool → result spans)
- External SDK published as PyPI package
