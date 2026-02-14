# Platform Boundaries

> Phase 0 — architectural reference only. No code changes.

## 1. Layers

The platform is divided into three layers. Each has a single responsibility
and a strict communication direction.

```
 +-----------------------------------------------------+
 |                    UI  (Reference Client)             |
 |  dashboard.html + dashboard-main.js                   |
 +-------------------------+-----------------------------+
                           | HTTP / WS (JSON)
 +-------------------------v-----------------------------+
 |                   API  (Thin Routing)                  |
 |  api/routes/*  — auth, validation, serialization only  |
 +-----+--------+--------+--------+--------+------------+
       |        |        |        |        |
 +-----v--+ +---v----+ +-v------+ +--v---+ +--v--------+
 | Control | | Integ. | | Collab | | Risk | | Observ.   |
 | Plane   | | Adapt. | | Engine | | Eng. | | Pipeline  |
 | (core/) | |adapters| | (core/)| |(core)| | (core/)   |
 +---------+ +--------+ +--------+ +------+ +-----------+
       |        |        |        |        |
 +-----v--------v--------v--------v--------v------------+
 |              Shared Data Layer  (models.py)            |
 |         SQLAlchemy models, DB sessions, migrations     |
 +-------------------------------------------------------+
```

---

## 2. Control Plane Core

**Location today:** `core/governance/`, `core/risk_engine/`, `core/observability/`, `core/collaboration/`, `auth_routes.py`, `models.py`

**Target location:** `core/{identity, tasks, governance, observability, risk, audit}/`

### Responsibilities

| Domain | What it owns | Key models |
|---|---|---|
| **Identity** | User lifecycle, sessions, magic-link auth, subscription tier, credit balance | `User`, `MagicLink`, `CreditTransaction`, `SubscriptionPlan`, `CreditPackage` |
| **Tasks** | Inter-agent task coordination, state machine, event log | `CollaborationTask`, `TaskEvent` |
| **Governance** | Policy change requests, approval workflow, delegation grants, rollback | `PolicyChangeRequest`, `DelegationGrant`, `GovernanceAuditLog` |
| **Observability** | Event ingestion, run tracking, cost engine, metrics aggregation, alerts, health scores | `ObsEvent`, `ObsRun`, `ObsAgentDailyMetrics`, `ObsAlertRule`, `ObsAlertEvent`, `ObsLlmPricing`, `ObsAgentHealthDaily`, `ObsApiKey`, `WorkspaceTier` |
| **Risk** | Policy evaluation, breach detection, automated interventions (throttle, downgrade, pause) | `RiskPolicy`, `RiskEvent`, `RiskAuditLog` |
| **Audit** | Append-only logs across governance, risk, and collaboration | `GovernanceAuditLog`, `RiskAuditLog`, `TaskEvent` |

### Invariants

1. Every state mutation on a core entity **must** go through its owning core module.
2. Core modules **never** import from `adapters/` or `routes/`.
3. Core modules expose a Python function API consumed by routes and other core modules — no HTTP calls between core modules.
4. All append-only logs (`*AuditLog`, `TaskEvent`, `ObsEvent`) are **insert-only** at the application layer — no UPDATE or DELETE.
5. Tier enforcement is checked inside core, not in routes.

---

## 3. Integration Adapters

**Location today:** `gmail_routes.py`, `calendar_routes.py`, `drive_routes.py`, `notion_routes.py`, `binance_routes.py`, `binance_actions_routes.py`, `github_routes.py`, `spotify_routes.py`, `todoist_routes.py`, `dropbox_routes.py`, `slack_routes.py`, `discord_routes.py`, `telegram_routes.py`, `channels_routes.py`, `oauth_routes.py`

**Target location:** `adapters/{gmail, calendar, drive, notion, binance, github, spotify, todoist, dropbox, slack, discord, telegram}/`

### Responsibilities

| Concern | Adapter does | Adapter does NOT do |
|---|---|---|
| **OAuth** | Execute token exchange, store encrypted tokens via `Superpower` model | Define its own auth model |
| **API calls** | Translate platform actions into vendor API calls | Decide whether an action is allowed |
| **Webhooks** | Receive vendor webhooks, normalize into platform events | Write directly to core audit logs |
| **Channel messages** | Receive inbound messages, format outbound replies | Mutate agent configuration |
| **Error handling** | Map vendor errors to platform error codes | Retry autonomously without backoff policy |

### Invariants

1. Adapters **never** write to core tables (`RiskPolicy`, `PolicyChangeRequest`, `CollaborationTask`, `ObsEvent`, etc.) directly. They call core module functions.
2. Adapters **never** evaluate risk policies or governance rules. They delegate to `core/risk_engine/` and `core/governance/`.
3. Adapters hold **no business logic** beyond vendor-API translation. Shared logic (e.g., "should this action be auto-approved?") lives in core.
4. Each adapter is a self-contained directory. Removing an adapter directory **must not** break core or other adapters.
5. OAuth token storage flows through a single shared path (`Superpower` model via core identity helpers).

---

## 4. API Routes (Thin Routing Layer)

**Location today:** `*_routes.py` files at repo root + `routes/` directory

**Target location:** `api/routes/`

### Responsibilities

- HTTP method + path declaration
- Request parsing and input validation
- Session/auth guard (`user_id = session.get('user_id')`)
- Call into core modules or adapters
- JSON serialization of responses
- Rate-limit decoration

### Invariants

1. Routes contain **zero business logic**. No `if policy.action == 'throttle':` branches — that lives in core.
2. Routes do not import other route modules.
3. Routes do not directly instantiate SQLAlchemy queries beyond the auth guard. They call core functions that return dicts or model instances.
4. A route file maps 1:1 to a URL namespace (e.g., `governance.py` owns `/api/governance/*`).

---

## 5. UI (Reference Client)

**Location today:** `dashboard.html`, `static/js/dashboard-main.js`, `static/css/`

### Responsibilities

- Render agent configuration, superpowers, observability dashboards, chat
- Call `/api/*` endpoints with `credentials: 'include'`
- Handle tab switching, form state, WebSocket connections

### Invariants

1. The UI is a **reference client** — the platform must be fully operable via API alone.
2. The UI **never** bypasses the API layer (no direct DB calls, no server-side template mutations of core state).
3. UI-specific display logic (icon mapping, color coding) stays in JS, not in Python route responses.

---

## 6. What Must NEVER Happen

These are hard architectural violations. Any code review that introduces one of these should be blocked.

| # | Violation | Why it's dangerous |
|---|---|---|
| **N1** | An adapter mutates core state directly (INSERT/UPDATE on `RiskPolicy`, `CollaborationTask`, `PolicyChangeRequest`, `ObsEvent`, etc.) without going through the owning core module. | Bypasses validation, audit logging, tier enforcement, and governance checks. |
| **N2** | A route file contains business logic (risk evaluation, cost calculation, state machine transitions, policy enforcement). | Creates multiple sources of truth; logic drifts between routes. |
| **N3** | Core modules import from `adapters/` or `routes/`. | Creates circular dependencies; core must be testable in isolation. |
| **N4** | An adapter calls another adapter directly. | Creates hidden coupling; adapter removal could cascade. |
| **N5** | Audit log records are updated or deleted at the application layer. | Destroys audit integrity. Append-only is a compliance requirement. |
| **N6** | Tier/quota enforcement is checked only in routes, not in core. | Any new route or adapter could bypass limits. |
| **N7** | An integration stores credentials outside the `Superpower` model (e.g., in `ConfigFile` or environment per-user). | Fragments credential management; complicates rotation and revocation. |
| **N8** | WebSocket or channel handlers execute tool actions without passing through the agent action approval queue (`AgentAction`). | Bypasses human-in-the-loop safety for side-effecting operations. |
| **N9** | The UI embeds knowledge about core state machines (valid transitions, policy rules). | UI becomes a second source of truth; must rely on API error responses. |

---

## 7. Cross-Cutting Concerns

| Concern | Owner | Notes |
|---|---|---|
| **Authentication** | `core/identity` | Session-based via magic link. Every request checks `session.get('user_id')`. |
| **Authorization** | `core/identity` + `core/governance` | Tier checks (free vs pro), delegation grants, role-based (supervisor/worker/specialist). |
| **Rate limiting** | `rate_limiter.py` (infra) | Applied at the route layer via Flask-Limiter decorators. |
| **Encryption at rest** | `Superpower` model | OAuth tokens encrypted. Decryption only at point-of-use in adapters. |
| **Audit trail** | `core/audit` (target) | Currently split across `GovernanceAuditLog`, `RiskAuditLog`, `TaskEvent`. Target: unified query interface. |
| **Cost tracking** | `core/observability/cost_engine` | Token costs computed per-event; aggregated daily. |
| **Notifications** | `core/observability/notifications` | Slack webhook for alerts. Should generalize to multi-channel. |

---

## 8. Dependency Direction (Target)

```
UI ──> API Routes ──> Core Modules ──> Models
                  ──> Adapters ────> Core Modules ──> Models
                                 ──> Vendor SDKs
```

Arrows indicate "depends on" / "may import from."

**Forbidden arrows:**
- Core --> Routes
- Core --> Adapters
- Adapters --> Routes
- Adapters --> Adapters
- Models --> anything above Models
