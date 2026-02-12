# Observability v2 — Acceptance Checklist

Generated: 2026-02-11

## Test Results

```
95 passed, 0 failed — full suite (auth + observability v1 + observability v2 + stripe)
```

Run: `python -m pytest tests/ -v`

---

## Phase 1: Subsystem Extraction

| # | Criterion | Status |
|---|-----------|--------|
| 1.1 | `core/observability/` package with 9 submodules exists | PASS |
| 1.2 | `observability_service.py` is a backward-compatible re-export shim | PASS |
| 1.3 | All 39 original v1 tests pass without modification | PASS |
| 1.4 | Routes import from `core.observability`, not monolith | PASS |
| 1.5 | No new dependencies introduced | PASS |

## Phase 2: Cost Engine

| # | Criterion | Status |
|---|-----------|--------|
| 2.1 | `calculate_cost()` returns `Decimal`, not `float` | PASS |
| 2.2 | Accumulating 10,000 micro-costs yields zero float drift | PASS |
| 2.3 | Longest-prefix matching selects correct model pricing | PASS |
| 2.4 | Exact match is preferred over prefix match | PASS |
| 2.5 | Unknown provider returns `Decimal(0)` | PASS |
| 2.6 | `invalidate_pricing_cache()` forces fresh DB lookup | PASS |
| 2.7 | Backward-compat `calculate_cost()` wrapper in shim returns float | PASS |

## Phase 3: Alert Engine Hardening

| # | Criterion | Status |
|---|-----------|--------|
| 3.1 | Time guard stops evaluation before Vercel 60s timeout | PASS |
| 3.2 | `dispatch_alert_notification()` routes to Slack when configured | PASS |
| 3.3 | Notification channel abstraction supports 'slack' type | PASS |
| 3.4 | Cron `/api/obs/cron/evaluate-alerts` endpoint functional | PASS |

## Phase 4: Health Score

| # | Criterion | Status |
|---|-----------|--------|
| 4.1 | Perfect agent (all success, good latency) scores ~100 | PASS |
| 4.2 | 50% error rate agent scores <= 80 (success_rate = 20/40) | PASS |
| 4.3 | Score is persisted to `obs_agent_health_daily` table | PASS |
| 4.4 | Re-computation is idempotent (no duplicate rows) | PASS |
| 4.5 | No metrics for the day returns None (not 0) | PASS |
| 4.6 | `GET /api/obs/health/agent/<id>` returns score history | PASS |
| 4.7 | `GET /api/obs/health/overview` returns today's scores | PASS |
| 4.8 | Alembic migration `010_add_health_score.py` creates table | PASS |

## Phase 5: Workspace Isolation

| # | Criterion | Status |
|---|-----------|--------|
| 5.1 | User A cannot see User B's events | PASS |
| 5.2 | API keys are scoped to their owner | PASS |
| 5.3 | Metrics are scoped per user | PASS |
| 5.4 | Alert rules are scoped per user | PASS |
| 5.5 | `verify_agent_ownership()` rejects cross-user access | PASS |

## Phase 6: Integration

| # | Criterion | Status |
|---|-----------|--------|
| 6.1 | Full lifecycle: emit -> aggregate -> health -> verify | PASS |
| 6.2 | Cron aggregate endpoint triggers aggregation + health scores | PASS |
| 6.3 | Cron evaluate-alerts endpoint fires alerts | PASS |
| 6.4 | All 95 tests pass (0 failures) | PASS |

---

## Bug Found & Fixed During QA

**UTC/local date mismatch**: Events store `created_at` via `datetime.utcnow()`, but aggregation and health score functions defaulted to `date.today()` (local time). When server timezone is behind UTC (e.g. PST), events fall outside the query window. Fixed by using `datetime.utcnow().date()` consistently in:
- `core/observability/metrics.py` — `aggregate_daily()` default
- `core/observability/health_score.py` — `compute_agent_health()` and `compute_all_health_scores()` defaults
- `routes/observability_routes.py` — cron endpoints and health API endpoints

---

## Files Modified/Created

### New Files (13)
- `core/__init__.py`
- `core/observability/__init__.py`
- `core/observability/constants.py`
- `core/observability/cost_engine.py`
- `core/observability/ingestion.py`
- `core/observability/run_tracker.py`
- `core/observability/metrics.py`
- `core/observability/notifications.py`
- `core/observability/alert_engine.py`
- `core/observability/health_score.py`
- `core/observability/workspace.py`
- `alembic/versions/010_add_health_score.py`
- `tests/test_observability_v2.py`

### Modified Files (4)
- `observability_service.py` — rewritten as backward-compatible shim
- `routes/observability_routes.py` — imports from core.observability, health endpoints added
- `models.py` — `ObsAgentHealthDaily` model added
- `server.py` — `ObsAgentHealthDaily` import added

### Documentation (2)
- `docs/observability/architecture-review.md` — Phase 0 audit
- `docs/observability/acceptance-checklist.md` — this file

---

## Local Run Instructions

```bash
# Install dependencies (no new packages added)
pip install -r requirements.txt

# Run full test suite
python -m pytest tests/ -v

# Run only v2 tests
python -m pytest tests/test_observability_v2.py -v

# Run locally
python server.py

# Apply migration (production)
alembic upgrade 010
```

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| `observability_service.py` shim could diverge from core | Low | Shim is read-only re-exports; all logic lives in core |
| UTC date fix could affect existing aggregated data | Low | Only affects default parameter; explicit date params unaffected |
| Health score formula may need tuning | Medium | Weights are constants in `constants.py`, easy to adjust |
| Slack notification failures could go silent | Low | Errors are logged; alert event is recorded regardless |
| Vercel 45s time guard may be too conservative | Low | Configurable via `MAX_EVALUATION_SECONDS` constant |
