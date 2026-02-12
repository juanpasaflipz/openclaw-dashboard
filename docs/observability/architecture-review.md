# Phase 0 — Architecture Review

## Current State Architecture Report

**Reviewer:** Chief Systems Architect
**Date:** 2026-02-11
**Scope:** Full audit of the AI Agent Observability & Governance layer

---

## 1. Component Inventory

### Files (Observability-Specific)

| File | Lines | Role |
|------|-------|------|
| `observability_service.py` | 495 | **Monolith service** — ingestion, cost calc, run tracking, aggregation, alert evaluation, Slack notification |
| `routes/observability_routes.py` | 566 | **Routes** — ingestion, metrics, events query, alerts CRUD, API keys, cron endpoints, pricing |
| `models.py` (lines 700-974) | ~274 | **7 ORM models:** ObsApiKey, ObsEvent, ObsRun, ObsAgentDailyMetrics, ObsAlertRule, ObsAlertEvent, ObsLlmPricing |
| `alembic/versions/008_add_observability.py` | 158 | Migration: creates all 7 `obs_*` tables |
| `scripts/seed_observability.py` | 157 | Seeds LLM pricing (24 models) + demo agents + API key |
| `scripts/generate_demo_events.py` | 269 | Generates 24h of synthetic events for demo/testing |
| `tests/test_observability.py` | 581 | 26 test cases covering API keys, ingestion, metrics, alerts, aggregation, cost calc |
| `docs/observability/` | 9 files | Design docs, API docs, acceptance criteria |

### Integration Points

| Touchpoint | File | Mechanism |
|------------|------|-----------|
| LLM call instrumentation | `llm_service.py:113` | Static `_obs_hook` callback on `LLMService` class |
| Chat pipeline full-run tracking | `routes/chatbot_routes.py:129-327` | `start_run()` / `emit_event()` / `finish_run()` wrapped around `run_llm_pipeline()` |
| Route registration | `routes/__init__.py:29` + `server.py:92` | Blueprint `obs_bp` registered at `/api/obs` |
| Cron scheduling | `vercel.json` | Two cron jobs: aggregate hourly, evaluate alerts every 15 min |

---

## 2. Data Flow Diagram

```
External Agent SDK                   Dashboard Chat Pipeline
       |                                     |
       | POST /api/obs/ingest/events         | (internal) emit_event() / start_run() / finish_run()
       v                                     v
  +---------+                          +---------+
  | API Key |                          | Session |
  | Auth    |                          | Auth    |
  +---------+                          +---------+
       |                                     |
       +-----------> obs_events <------------+
                         |
                         | (Vercel cron, hourly)
                         v
                  aggregate_daily()
                         |
                         v
              obs_agent_daily_metrics
                         |
                         | (Vercel cron, every 15 min)
                         v
                  evaluate_alerts()
                         |
                    +----+----+
                    |         |
                    v         v
           obs_alert_events  Slack webhook
```

---

## 3. Strengths of Current Implementation

1. **Clean append-only event log.** `ObsEvent` with UUID, dedupe key, and JSONB payload is a solid foundation.

2. **Dual auth model.** Bearer API key for external SDK ingestion, session auth for dashboard queries — correct separation.

3. **Pre-aggregated daily metrics.** `ObsAgentDailyMetrics` avoids raw-event scanning for dashboard KPIs.

4. **Pricing table with effective dates.** `ObsLlmPricing` supports time-varying costs and per-model granularity.

5. **Alert system with cooldown.** Three rule types (cost, error rate, heartbeat) with configurable cooldown prevents alert storms.

6. **Test coverage.** 26 test cases across all major subsystems. Fixtures are well-structured.

7. **Non-blocking instrumentation.** `emit_event()` swallows exceptions to never break the caller. LLM hook explicitly catches failures.

8. **Idempotent aggregation.** `aggregate_daily()` upserts, safe to run multiple times.

---

## 4. Architectural Weaknesses

### W1: Monolithic Service Module (CRITICAL)

**File:** `observability_service.py` (495 lines, 6 distinct responsibilities)

`observability_service.py` contains:
- Event emission + batch ingestion
- Cost calculation with in-memory pricing cache
- Run lifecycle tracking
- Daily aggregation logic
- Alert evaluation logic
- Slack notification dispatch

**Impact:** Every change to alert logic requires editing the same file as ingestion logic. Cost calculation is coupled to event emission. No ability to test aggregation in isolation without importing alert code.

**Recommendation:** Extract into `core/observability/` package with separate modules.

---

### W2: No Background Worker — Cron-Only Architecture (HIGH)

**Current:** Aggregation and alert evaluation only run when Vercel cron hits HTTP endpoints (`/api/obs/internal/aggregate` and `/api/obs/internal/evaluate-alerts`).

**Problems:**
- **Vercel Hobby cron minimum is 1 hour.** Alerts evaluated every 15 minutes requires Vercel Pro.
- **Cold start penalty.** Each cron invocation is a full serverless cold start — imports all route modules, connects to DB.
- **No retry on failure.** If a cron invocation fails (timeout, DB error), the work is simply lost until the next scheduled run.
- **60-second execution limit.** Large aggregation windows could exceed this on production data volumes.
- **No worker isolation.** Aggregation and alert evaluation share the same HTTP request context as user-facing endpoints.

**Recommendation:** The cron approach is acceptable for Vercel serverless, but needs hardening: retry logic, execution time guards, partial aggregation support, and clear documentation of Vercel plan requirements.

---

### W3: Cost Calculation Reliability (HIGH)

**Problems:**
1. **In-memory cache with TTL.** `_pricing_cache` is a module-level dict with 5-min TTL. In Vercel serverless, every cold start rebuilds this. But within a warm instance, stale pricing could be served if the DB is updated.
2. **Prefix matching fallback is fragile.** Line 70-74: `model.startswith(m)` — e.g., `gpt-4o-mini-2024` would match `gpt-4o` first if iterated in wrong order. Dict iteration order is insertion order, but the insertion order is query result order (arbitrary).
3. **Cost is computed at ingestion time.** If pricing is updated retroactively, historical events keep the old cost. No mechanism to recompute.
4. **Float accumulation.** `finish_run()` line 244: `float(run.total_cost_usd or 0) + float(cost_usd or 0)` — repeated float addition introduces drift. Should use `Decimal` throughout.
5. **No workspace-level pricing overrides.** All users share the same global pricing table.

**Recommendation:** Centralize into a dedicated cost engine with deterministic Decimal math, sorted pricing lookup, and a recompute capability.

---

### W4: Alert Engine Immaturity (MEDIUM)

**Problems:**
1. **Alerts run synchronously inside HTTP request.** `evaluate_alerts()` is called by a cron endpoint. If there are many rules, this can timeout.
2. **Full table scan per rule.** Each rule does a separate query against `obs_events` — no batch optimization.
3. **Only Slack notification.** No in-app notification push, no email, no webhook to user-defined URL.
4. **No alert severity levels.** All alerts are treated equally — no warn/critical distinction.
5. **No snooze/silence capability.** Users can only enable/disable rules, not temporarily silence them.
6. **Orphan risk.** If an `ObsAlertRule` is deleted, related `ObsAlertEvent` rows are not cascade-deleted (no `ON DELETE CASCADE` or `SET NULL`).

**Recommendation:** Extract alert evaluation into a dedicated module. Add batch metric pre-computation. Add severity levels and notification channel abstraction.

---

### W5: Multi-Workspace Isolation (MEDIUM)

**Current:** `workspace_id = user_id`. Every query in `observability_service.py` and `observability_routes.py` filters by `user_id`.

**Problems:**
1. **No explicit workspace model.** When multi-user workspaces are needed, every query needs refactoring.
2. **API keys are user-scoped, not workspace-scoped.** An API key created by User A cannot be used to ingest events for a team workspace.
3. **No query-level enforcement layer.** Each endpoint manually checks `user_id`. Easy to forget in new endpoints, causing data leakage.
4. **Pricing is global.** No per-workspace custom pricing for enterprise customers.
5. **No rate limiting on ingestion.** A single API key can flood the events table with no throttle.

**Recommendation:** Introduce a `workspace_id` column (defaulting to `user_id` for v1). Create a query-scoping helper that enforces isolation. Add per-key rate limits.

---

### W6: Missing Health Score (LOW — but premium feature)

No composite health score per agent. The dashboard shows raw metrics (runs, errors, cost) but no single "health" indicator. This is a strong candidate for a premium/gated feature.

---

### W7: No Data Retention Policy (LOW)

`obs_events` is append-only with no TTL or archival mechanism. Over time, this table will grow unbounded. For monetization, retention limits could be a tier differentiator.

---

### W8: Pricing Cache Race Condition (LOW)

Module-level `_pricing_cache` and `_pricing_cache_ts` are not thread-safe. In a multi-worker WSGI setup (unlikely in Vercel, but possible in local dev with gunicorn), concurrent requests could see partially-updated cache state.

---

## 5. Test Coverage Assessment

| Subsystem | Tests | Coverage | Gaps |
|-----------|-------|----------|------|
| API Key model | 4 | Good | - |
| Ingestion API | 7 | Good | No test for cost auto-calculation during ingestion |
| Heartbeat API | 3 | Good | - |
| Metrics API | 4 | Structural only | No test verifying metric *values* match expected |
| Events query | 3 | Good | No pagination test |
| Alert rules CRUD | 4 | Good | - |
| Alert evaluation | 5 | Good | No test for batch rule evaluation performance |
| API key management | 3 | Good | - |
| Aggregation | 2 | Core logic covered | No multi-agent aggregation test |
| Cost calculation | 2 | Basic | No test for prefix matching edge cases, no Decimal precision test |
| Pricing endpoint | 1 | Minimal | - |
| **Integration flow** | **0** | **Missing** | **No end-to-end test: seed -> ingest -> aggregate -> alert -> health** |
| **Workspace isolation** | **0** | **Missing** | **No test verifying cross-user data leakage prevention** |

---

## 6. Proposed Target Architecture

### Package Structure

```
core/
  observability/
    __init__.py           — Public API re-exports
    ingestion.py          — emit_event(), emit_event_batch(), _commit_one_by_one()
    run_tracker.py        — start_run(), finish_run()
    cost_engine.py        — calculate_cost(), _load_pricing(), pricing cache
    metrics.py            — aggregate_daily(), _aggregate_one(), _percentile()
    alert_engine.py       — evaluate_alerts(), _evaluate_rule_metric(), _fire_alert()
    health_score.py       — compute_agent_health(), HealthScoreFormula
    notifications.py      — Slack webhook, future email/webhook channels
    constants.py          — VALID_EVENT_TYPES, EVENT_STATUS_VALUES, cache TTLs
    workspace.py          — Workspace scoping helper for query isolation
```

### What Stays Where

| Component | Location | Rationale |
|-----------|----------|-----------|
| ORM models | `models.py` (bottom section) | Follows existing project convention — all models in one file |
| Route handlers | `routes/observability_routes.py` | Thin handlers that delegate to `core/observability/` |
| Alembic migration | `alembic/versions/` | Follows existing convention |
| Seed scripts | `scripts/` | Follows existing convention |
| Tests | `tests/test_observability.py` + new files | Expand existing test file, add integration test file |

### Migration Strategy

**Incremental extraction.** The current `observability_service.py` is refactored function-by-function into `core/observability/` modules. The old file is replaced with thin re-exports during transition to avoid breaking imports. Once all callers are updated, the re-export file is removed.

**Zero API breakage.** All existing `/api/obs/*` endpoints continue to work identically. Routes just import from `core.observability` instead of `observability_service`.

---

## 7. Phase-by-Phase Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| P1: Subsystem extraction | Import path breakage | Keep `observability_service.py` as re-export shim until Phase 1 complete |
| P2: Cost engine | Decimal precision changes | Add unit tests before refactoring, compare old vs new output |
| P3: Alert hardening | Cron timeout on large rule sets | Add execution time guard, process N rules per invocation |
| P4: Health score | New table + migration | Additive-only migration, backward compatible |
| P5: Workspace isolation | Query refactoring across all endpoints | Centralized helper, add isolation tests first |
| P6: QA hardening | Test complexity | Keep integration tests focused, use existing fixture patterns |

---

## 8. Vercel Deployment Considerations

| Constraint | Impact on Design |
|------------|-----------------|
| No persistent processes | Background workers must be cron-based HTTP endpoints |
| 60s execution limit | Aggregation must be time-bounded; large datasets need chunked processing |
| Cold start on every invocation | Module-level caches (`_pricing_cache`) are rebuilt each time — acceptable |
| Vercel Hobby: 1h min cron | Alert evaluation every 15 min requires Vercel Pro plan |
| No shared memory between invocations | Rate limiting via Flask-Limiter memory store is per-invocation only |
| PUT unreliable | All observability endpoints already use POST/GET |

---

## 9. Summary of Recommendations

| Priority | Recommendation | Phase |
|----------|---------------|-------|
| CRITICAL | Extract monolithic service into `core/observability/` package | P1 |
| HIGH | Centralize cost engine with Decimal-only math + sorted pricing lookup | P2 |
| HIGH | Harden alert evaluation: batch queries, execution time guards | P3 |
| MEDIUM | Add agent health score as premium feature | P4 |
| MEDIUM | Introduce workspace scoping helper + isolation tests | P5 |
| MEDIUM | Add integration test covering full seed-ingest-aggregate-alert flow | P6 |
| LOW | Add data retention cron + tier-based retention limits | Deferred |
| LOW | Thread-safe pricing cache (only matters for gunicorn local dev) | Deferred |

---

*This review is the deliverable for Phase 0. No code changes have been made. Implementation begins at Phase 1 upon approval.*
