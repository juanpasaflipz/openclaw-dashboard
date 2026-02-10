# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Green Monkey Dashboard (formerly OpenClaw) — a Flask web app that lets users configure AI agents, connect external services (superpowers), manage LLM providers, and interact via a chatbot. Deployed on Vercel with Neon PostgreSQL.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (serves on http://localhost:5000)
python server.py

# Run tests
pytest
pytest tests/test_auth.py -v          # single test file
pytest tests/test_auth.py::test_name  # single test

# Deploy (auto-deploys on push to main via Vercel)
git push origin main
```

Environment: copy `.env.example` to `.env.local` for local dev. Production env vars are set in Vercel dashboard. SQLite is used locally; PostgreSQL (Neon) in production.

## Architecture

**Single-page Flask app.** No frontend build step — vanilla JS.

- `server.py` — App entry point. Registers all route modules, configures DB, defines admin/utility endpoints.
- `models.py` — All SQLAlchemy models (User, Agent, Superpower, AgentAction, UserModelConfig, ChatConversation, ChatMessage, etc.)
- `dashboard.html` — The entire frontend UI (single HTML file, ~2000 lines)
- `static/js/dashboard-main.js` — All frontend logic (~5000+ lines, `API_BASE = window.location.origin + '/api'`)

### Route Registration Pattern

Every feature follows this pattern:

```python
# feature_routes.py
def register_feature_routes(app):
    @app.route('/api/feature/endpoint', methods=['GET'])
    def handler():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        # ...

# server.py
from feature_routes import register_feature_routes
register_feature_routes(app)
```

Route files: `auth_routes.py`, `gmail_routes.py`, `calendar_routes.py`, `drive_routes.py`, `notion_routes.py`, `binance_routes.py`, `binance_actions_routes.py`, `oauth_routes.py`, `agent_actions_routes.py`, `agent_routes.py`, `channels_routes.py`, `chatbot_routes.py`, `model_config_routes.py`, `llm_providers_routes.py`, `external_agents_routes.py`, `web_browsing_routes.py`, `utility_routes.py`, `stripe_routes.py`, `setup_routes.py`, `moltbook_routes.py`, `analytics_routes.py`.

### Superpowers (External Services)

Connected services use the `Superpower` model. OAuth tokens stored in `access_token_encrypted` / `refresh_token_encrypted`. API-key services (Binance) use the same fields.

**To add a new superpower:**
1. Create `service_routes.py` with `register_X_routes(app)` — service client helper + REST endpoints
2. Register in `server.py`
3. Add service card in `dashboard.html` (Connect tab, after the Notion card)
4. Add JS functions in `dashboard-main.js` (connect function, `getServiceIcon()` entry, status update in `loadConnectedServices()`)

### Agent Actions (Approval Queue)

AI proposes actions → stored as `AgentAction` with `status='pending'` → user approves/rejects in dashboard → if approved, backend executes and sets `status='executed'`.

Execution branches live in `agent_actions_routes.py` `approve_action()` — one `elif` per `(action_type, service_type)` pair.

### LLM Provider System

Two-layer config:

- **`llm_service.py`** — `PROVIDER_DEFAULTS` dict (endpoint URLs, model lists) + `LLMService` class with `call()` and `test_connection()`. OpenAI-compatible providers share `_call_openai_compatible()`. Non-standard providers (Anthropic, Google, Ollama, Cohere) have dedicated methods.
- **`llm_providers_routes.py`** — `PROVIDERS` dict with UI metadata (icon, tier, difficulty, fields, models, docs). Tier-gated: `'free'` or `'pro'`.

To add a provider: add entry in both `PROVIDER_DEFAULTS` and `PROVIDERS`. If it's OpenAI-compatible, no new call method needed.

### Chatbot System

`chatbot_routes.py` manages conversations and messages. `POST /api/chat/send` loads `UserModelConfig` for the feature slot, builds message history, calls `LLMService.call()`, saves response. Frontend in `dashboard-main.js` handles both Direct LLM mode (HTTP) and Nautilus WebSocket mode.

### Auth

Magic link email auth via SendGrid. `auth_routes.py` handles `/api/auth/request-magic-link` and `/api/auth/verify`. Sessions stored server-side. `BASE_URL` env var controls the link domain.

## Key Technical Details

- **Database:** Flask-SQLAlchemy. Production uses Neon PostgreSQL with SSL (`sslmode=require`), connection pooling, and `pool_pre_ping=True`. Local dev uses SQLite.
- **Payments:** Stripe for subscriptions (Free + $15/mo Pro) and credit packs.
- **Deployment:** Vercel with `@vercel/python` runtime. All routes go through `server.py`. PUT requests can be unreliable on Vercel — prefer POST.
- **Frontend state:** No framework. Tab switching via `switchTab(tabName)`. API calls use `fetch()` with `credentials: 'include'`.
- **Rate limiting:** Flask-Limiter (`rate_limiter.py`).
