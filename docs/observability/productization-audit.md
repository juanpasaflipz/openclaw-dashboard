# Productization Audit — Observability Layer

**Date:** 2026-02-11
**Status:** Phase 0 — No code changes yet

---

## 1. Executive Summary

The observability subsystem (`core/observability/`) is architecturally ready for productization. It has clean module boundaries, workspace isolation via `user_id` scoping, 95 passing tests, and a non-blocking design. However, it currently has **zero feature gating** — every authenticated user gets full access to alerts, health scores, anomaly detection, and unlimited retention.

This audit identifies every boundary that must be gated, maps them to a four-tier pricing model (Free / Production / Pro / Agency), and defines the implementation path for monetization without rewriting existing code.

---

## 2. Current State

### 2.1 Observability Modules

| Module | File | Gating Needed |
|--------|------|---------------|
| Event ingestion | `core/observability/ingestion.py` | No (core functionality) |
| Run tracking | `core/observability/run_tracker.py` | No (core functionality) |
| Cost engine | `core/observability/cost_engine.py` | No (used by all tiers) |
| Daily aggregation | `core/observability/metrics.py` | Yes — retention window |
| Alert engine | `core/observability/alert_engine.py` | Yes — rule count limit |
| Health scoring | `core/observability/health_score.py` | Yes — history access |
| Workspace helpers | `core/observability/workspace.py` | Yes — agent count limit |
| Notifications | `core/observability/notifications.py` | Yes — channel access |
| Constants | `core/observability/constants.py` | No (configuration) |

### 2.2 Route Endpoints Requiring Gating

| Endpoint | Current Access | Gate Required |
|----------|---------------|---------------|
| `POST /api/obs/ingest/events` | API key auth | Agent count limit |
| `POST /api/obs/ingest/heartbeat` | API key auth | Agent count limit |
| `GET /api/obs/metrics/agents` | Session auth | Retention window filter |
| `GET /api/obs/metrics/agent/<id>` | Session auth | Retention window filter |
| `GET /api/obs/metrics/overview` | Session auth | Retention window filter |
| `GET /api/obs/events` | Session auth | Retention window filter |
| `GET /api/obs/alerts/rules` | Session auth | None (read) |
| `POST /api/obs/alerts/rules` | Session auth | Rule count limit |
| `GET /api/obs/alerts/events` | Session auth | None (read) |
| `GET /api/obs/health/agent/<id>` | Session auth | History depth limit |
| `GET /api/obs/health/overview` | Session auth | Feature gate (tier check) |
| `GET /api/obs/api-keys` | Session auth | None (read) |
| `POST /api/obs/api-keys` | Session auth | Key count limit (future) |

### 2.3 Models

| Model | Records | Retention Impact |
|-------|---------|-----------------|
| `ObsEvent` | Append-only, high volume | Primary retention target |
| `ObsRun` | One per pipeline run | Secondary retention target |
| `ObsAgentDailyMetrics` | One per agent per day | Retention window filter |
| `ObsAlertRule` | User-created | Count limit per tier |
| `ObsAlertEvent` | Auto-generated on fire | Retention follows rules |
| `ObsAgentHealthDaily` | One per agent per day | History depth limit |
| `ObsLlmPricing` | Reference data | No retention needed |
| `ObsApiKey` | User-created | No retention needed |

---

## 3. Existing Tier Infrastructure

The app already has a two-tier model (Free / Pro at $15/mo) with:

- `User.subscription_tier` field (`free`, `pro`, legacy `starter`/`team` mapped to `pro`)
- `User.effective_tier` property for backward compatibility
- `User.is_premium()` — checks tier + active subscription
- `SubscriptionPlan` model with feature flags per tier
- Full Stripe webhook lifecycle (create, update, cancel, payment)
- Tier gating pattern: `user.can_access_*()` methods on User model
- Provider/channel gating via tier hierarchy dict in route files

**Key insight:** The observability layer needs its own tier system (`workspace_tiers` table) separate from the existing User subscription, because:
1. Observability tiers have different dimensions (retention, agent limits, alert rules) vs app tiers (max agents, analytics, feed access)
2. Future SaaS expansion requires workspace-level billing, not user-level
3. An external customer may have a different observability tier than their app tier
4. Decoupling allows independent pricing iteration

---

## 4. Feature Boundaries to Gate

### 4.1 Retention Duration

| Tier | Retention | Implementation |
|------|-----------|----------------|
| Free | 7 days | Filter `created_at >= now() - 7d` on all queries |
| Production | 30 days | Filter `created_at >= now() - 30d` |
| Pro | 90 days | Filter `created_at >= now() - 90d` |
| Agency | 180 days | Filter `created_at >= now() - 180d` |

**Enforcement points:**
- `GET /api/obs/events` — add `WHERE created_at >= cutoff`
- `GET /api/obs/metrics/agents` — filter date range to retention window
- `GET /api/obs/metrics/agent/<id>` — filter date range + recent events
- `GET /api/obs/metrics/overview` — week summary stays within 7d (all tiers)
- `aggregate_daily()` — no change (aggregation is full; queries are filtered)
- Background cleanup job — soft-delete or archive events past retention

### 4.2 Number of Agents

| Tier | Agent Limit |
|------|-------------|
| Free | 2 |
| Production | 10 |
| Pro | 50 |
| Agency | Unlimited (9999) |

**Enforcement points:**
- `POST /api/obs/ingest/events` — reject events for agents beyond limit
- `POST /api/obs/ingest/heartbeat` — reject heartbeats beyond limit
- Count distinct `agent_id` in `ObsEvent` for user (or use `Agent` model count)
- Note: The app-level `User.get_max_agents()` already limits agent creation (1 free, 999 pro). The observability agent limit is separate — it gates how many agents can be *monitored*, not created.

### 4.3 Number of Alert Rules

| Tier | Alert Rule Limit |
|------|-----------------|
| Free | 0 (alerts disabled) |
| Production | 3 |
| Pro | Unlimited (9999) |
| Agency | Unlimited (9999) |

**Enforcement points:**
- `POST /api/obs/alerts/rules` — check count before creation
- `evaluate_alerts()` — only process rules for workspaces with alerts enabled
- Free tier: return 403 on rule creation attempt

### 4.4 Health Score History

| Tier | Health History |
|------|--------------|
| Free | Today only (no history) |
| Production | 7 days |
| Pro | 30 days |
| Agency | 90 days |

**Enforcement points:**
- `GET /api/obs/health/agent/<id>` — clamp `from` date to allowed window
- `GET /api/obs/health/overview` — available to all tiers (today only)
- `compute_agent_health()` — runs for all tiers (storage is cheap; access is gated)

### 4.5 Anomaly Detection

| Tier | Anomaly Detection |
|------|-------------------|
| Free | Disabled |
| Production | Disabled |
| Pro | Enabled |
| Agency | Enabled |

**Current implementation:** The `cost_anomaly_score` component in health scoring already computes cost anomaly (stddev-based). Gating means:
- Health score still computes for all tiers (minus anomaly component for non-Pro)
- Anomaly-specific alerts (future) gated to Pro+
- Anomaly breakdown hidden from health API response for non-Pro

### 4.6 Slack Notifications

| Tier | Slack Notifications |
|------|-------------------|
| Free | Disabled |
| Production | Enabled |
| Pro | Enabled |
| Agency | Enabled + priority |

**Enforcement points:**
- `dispatch_alert_notification()` — check tier before dispatching
- Free tier: alerts fire but don't notify (in-app only)
- Future: webhook/email channels gated similarly

### 4.7 Additional Gated Features

| Feature | Free | Production | Pro | Agency |
|---------|------|------------|-----|--------|
| Multi-workspace | No | No | No | Yes |
| Priority processing | No | No | No | Yes |
| Custom alert cooldowns | No | Default 6h | Configurable | Configurable |
| Batch ingestion | 100/req | 500/req | 1000/req | 1000/req |
| API keys | 1 | 3 | 10 | Unlimited |

---

## 5. Workspace Isolation Assessment

### Current State

Isolation is implemented via `user_id` scoping throughout:
- `workspace.py` maps `workspace_id = user_id` (v1)
- `scope_query()` applies `user_id` filter to all queries
- `verify_agent_ownership()` and `verify_api_key_ownership()` check ownership
- All route endpoints filter by `session['user_id']` or API key's `user_id`

### Gaps for Productization

1. **No `workspace_id` column** — All obs tables use `user_id` directly. Multi-workspace (Agency tier) requires adding `workspace_id` to obs tables or creating a workspace-user mapping table. For now, `workspace_id == user_id` is sufficient.

2. **No tier lookup per workspace** — Need `workspace_tiers` table linking workspace to tier config.

3. **No limit enforcement middleware** — Currently no centralized check. Each endpoint must individually verify limits. A `verify_workspace_limits()` helper is needed.

---

## 6. API Key Model Assessment

### Current State

- `ObsApiKey` model with SHA256 hashing, `obsk_` prefix
- Scoped to `user_id` (workspace)
- Supports creation, lookup, revocation
- `last_used_at` tracking

### Gaps for Productization

1. **No key count limit** — Any user can create unlimited API keys. Need per-tier limit.
2. **No rate limiting per key** — Ingestion has no per-key throttle. Future consideration.
3. **No key scoping** — Keys grant full workspace access. Future: read-only vs read-write keys.

---

## 7. Proposed Tier Model

### `workspace_tiers` Table

```
workspace_id        INTEGER  PK, FK(users.id)
tier_name           VARCHAR  'free' | 'production' | 'pro' | 'agency'
agent_limit         INTEGER  2 | 10 | 50 | 9999
retention_days      INTEGER  7 | 30 | 90 | 180
alert_rule_limit    INTEGER  0 | 3 | 9999 | 9999
health_history_days INTEGER  0 | 7 | 30 | 90
anomaly_detection   BOOLEAN  false | false | true | true
slack_notifications BOOLEAN  false | true | true | true
multi_workspace     BOOLEAN  false | false | false | true
priority_processing BOOLEAN  false | false | false | true
max_api_keys        INTEGER  1 | 3 | 10 | 9999
max_batch_size      INTEGER  100 | 500 | 1000 | 1000
updated_at          DATETIME
```

### Seed Data

| Field | Free | Production | Pro | Agency |
|-------|------|------------|-----|--------|
| agent_limit | 2 | 10 | 50 | 9999 |
| retention_days | 7 | 30 | 90 | 180 |
| alert_rule_limit | 0 | 3 | 9999 | 9999 |
| health_history_days | 0 | 7 | 30 | 90 |
| anomaly_detection | false | false | true | true |
| slack_notifications | false | true | true | true |
| multi_workspace | false | false | false | true |
| priority_processing | false | false | false | true |
| max_api_keys | 1 | 3 | 10 | 9999 |
| max_batch_size | 100 | 500 | 1000 | 1000 |

---

## 8. Implementation Impact Map

### Phase 1 — Pricing Tier System
- **New file:** `alembic/versions/011_add_workspace_tiers.py` (migration)
- **Modified:** `models.py` (add `WorkspaceTier` model)
- **New file:** `core/observability/tier_enforcement.py` (middleware)
- **Modified:** `core/observability/workspace.py` (add tier lookup)
- **Risk:** Low — additive only

### Phase 2 — Retention Enforcement
- **Modified:** `routes/observability_routes.py` (add retention filter to 5 endpoints)
- **New function:** `core/observability/retention.py` (cleanup job)
- **Risk:** Medium — modifies query behavior. Must not break existing tests.

### Phase 3 — Feature Gating
- **Modified:** `routes/observability_routes.py` (add tier checks to 4 endpoints)
- **Modified:** `core/observability/alert_engine.py` (skip rules for gated tiers)
- **Modified:** `core/observability/notifications.py` (check tier before dispatch)
- **New tests:** `tests/test_tier_enforcement.py`
- **Risk:** Medium — changes access patterns. Existing tests must pass unchanged.

### Phase 4 — Billing Readiness
- **New endpoints:** `POST /api/obs/admin/tier` (admin tier update)
- **New endpoint:** `POST /api/obs/webhooks/billing` (stub for future Stripe)
- **Modified:** `routes/observability_routes.py`
- **Risk:** Low — additive only

### Phase 5 — Documentation
- **New files:** 3 markdown docs
- **Risk:** None

---

## 9. Test Impact Assessment

### Existing Tests (95 passing)

All existing tests operate as a single user with no tier restrictions. After gating:

- Tests that create alert rules will need a workspace tier that allows alerts
- Tests that query metrics will get retention-filtered results
- Tests that check health scores will need appropriate tier

**Strategy:** Add a test fixture that seeds a `WorkspaceTier` with `tier_name='pro'` for all existing test users. This preserves current behavior (all features available) while testing the infrastructure.

### New Tests Required

| Test | Phase |
|------|-------|
| Free tier cannot create alert rules | 3 |
| Free tier events filtered to 7 days | 2 |
| Production tier limited to 3 alert rules | 3 |
| Agent count limit enforced on ingestion | 3 |
| Health history clamped to tier window | 3 |
| Anomaly detection hidden for non-Pro | 3 |
| Tier upgrade dynamically changes limits | 4 |
| Missing tier defaults to free | 1 |
| Retention cleanup job respects tier | 2 |

---

## 10. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Breaking existing tests | High | Seed pro tier for test users |
| Retention filter changes query results | Medium | Add retention as query param, default to tier window |
| Alert rules silently disabled for free | Medium | Return clear 403 with upgrade message |
| Performance impact of tier lookup per request | Low | Cache tier config in-memory (TTL 60s) |
| Migration on production DB | Low | Additive migration only (new table) |
| Existing users lose features | High | Default all existing users to `production` tier (grandfather) |

---

## 11. Decisions Required Before Phase 1

1. **Grandfathering:** Should existing users get `free` or `production` tier? Recommendation: `production` (30-day retention, 3 alerts) to avoid breaking existing workflows.

2. **Tier coupling:** Should observability tier be linked to app subscription tier (`User.subscription_tier`)? Recommendation: No — keep separate. An admin endpoint can sync them if desired.

3. **Enforcement strictness:** Should over-limit agents have events silently dropped or rejected with 4xx? Recommendation: Reject with `403` and clear message.

4. **Retention cleanup:** Soft-delete (add `archived_at` column) or hard-delete? Recommendation: Hard-delete with a 24-hour grace period. Events past retention + 24h are deleted by cleanup job.

---

## 12. File Inventory

Files that will be created or modified across all phases:

### New Files
```
alembic/versions/011_add_workspace_tiers.py
core/observability/tier_enforcement.py
core/observability/retention.py
tests/test_tier_enforcement.py
docs/observability/productization-audit.md       (this file)
docs/observability/pricing-model.md
docs/observability/tier-enforcement.md
docs/observability/upgrade-path.md
```

### Modified Files
```
models.py                                         (add WorkspaceTier model)
core/observability/__init__.py                    (export tier functions)
core/observability/workspace.py                   (add tier lookup)
core/observability/notifications.py               (add tier check)
routes/observability_routes.py                    (add gating to endpoints)
```

### Unchanged Files
```
core/observability/ingestion.py                   (no changes needed)
core/observability/run_tracker.py                 (no changes needed)
core/observability/cost_engine.py                 (no changes needed)
core/observability/metrics.py                     (no changes needed)
core/observability/alert_engine.py                (minimal change — skip gated)
core/observability/health_score.py                (no changes needed)
core/observability/constants.py                   (no changes needed)
observability_service.py                          (backward-compat shim, unchanged)
tests/test_observability_v2.py                    (existing tests unchanged)
```
