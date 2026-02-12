# Risk Policy & Intervention Engine — Architecture

**Status:** PHASE 0 — Architecture Review
**Author:** Chief Systems Architect
**Date:** 2026-02-11

---

## 1. Motivation

The existing observability subsystem tracks events, aggregates metrics, computes health scores, and fires alerts. However, alerts are **notification-only** — they tell a human something is wrong but cannot act on it. The risk engine closes this gap: it evaluates configurable policies, detects breaches, and executes interventions (throttle, downgrade, pause) **asynchronously**, **deterministically**, and **reversibly**.

---

## 2. Existing System — Integration Point Map

### 2.1 Cost Engine (`core/observability/cost_engine.py`)

| What we read | How |
|---|---|
| Aggregated daily cost per workspace/agent | `ObsEvent.cost_usd` summed via SQL, same query pattern used by `alert_engine._evaluate_rule_metric('cost_per_day')` |
| Real-time cost since midnight | Direct query: `SUM(cost_usd) WHERE user_id=? AND created_at >= today` |

**Integration:** The risk evaluator will issue its own cost query against `obs_events`. It does **not** call `calculate_cost()` (that runs at ingestion time). We read the already-calculated `cost_usd` column.

### 2.2 Daily Metrics (`core/observability/metrics.py`)

| What we read | How |
|---|---|
| Pre-aggregated daily totals | `ObsAgentDailyMetrics` rows (total_cost_usd, failed_runs, total_runs, etc.) |

**Integration:** For future policies (error_rate_cap, token_rate_cap), the evaluator can read from `ObsAgentDailyMetrics` for historical data. For real-time, it queries `ObsEvent` directly.

### 2.3 Health Score (`core/observability/health_score.py`)

| Relationship | Notes |
|---|---|
| Read-only | The risk engine does not modify health scores. A paused agent may stop generating events, which naturally degrades health — that is expected. |

**Integration:** None required. Health score is a downstream consumer.

### 2.4 Alert Engine (`core/observability/alert_engine.py`)

| Relationship | Notes |
|---|---|
| Parallel, not dependent | Alert engine fires notifications. Risk engine fires interventions. They share the same metric queries but operate independently. |
| No modification | Risk engine does not modify `obs_alert_rules` or `obs_alert_events`. |

**Integration:** Both systems can coexist on the same cron schedule. An alert rule for `cost_per_day > $5` (notification) and a risk policy for `daily_spend_cap = $10` (pause agent) are complementary, not conflicting.

### 2.5 Workspace Isolation (`core/observability/workspace.py`)

| What we use | How |
|---|---|
| `get_workspace_id(user_id)` | All risk tables include `workspace_id` column. All queries scoped. |
| `verify_agent_ownership(agent_id, user_id)` | Validate agent belongs to workspace before intervention. |

**Integration:** Risk tables follow the same `user_id`-based isolation pattern as all other observability tables.

### 2.6 Tier Enforcement (`core/observability/tier_enforcement.py`)

| Relationship | Notes |
|---|---|
| Read-only | Risk engine checks tier to determine if risk policies are available for the workspace's tier. |
| No modification | Risk engine does not modify `WorkspaceTier`. |

**Integration:** Risk policies should be tier-gated (e.g., free tier gets 0 risk policies, production tier gets 1, pro gets unlimited). This will be enforced at the route layer, same pattern as `check_alert_rule_limit()`.

### 2.7 Agent Model (`models.py: Agent`)

| What we modify | How |
|---|---|
| `Agent.is_active` | Set to `False` for `pause_agent` intervention. |
| `Agent.llm_config` | Modify `model` field for `model_downgrade` intervention. |

**Integration:** The intervention executor is the **only** component that modifies agent state, and only from the async worker — never during an HTTP request.

---

## 3. Subsystem Design

```
core/risk_engine/
    __init__.py              # Public API exports
    policy.py                # Policy CRUD helpers, threshold types
    evaluator.py             # Breach detection, risk_event creation
    interventions.py         # Action execution (pause, downgrade, throttle)
    enforcement_worker.py    # Async loop: evaluate → execute
    audit_log.py             # Audit trail read/write helpers
```

### 3.1 Data Flow

```
                   ┌─────────────────────────────────────────────┐
                   │          ENFORCEMENT WORKER (async)          │
                   │                                             │
                   │  ┌──────────┐      ┌──────────────────┐    │
 cron/manual ─────►│  │ EVALUATOR │─────►│ risk_events      │    │
                   │  │           │      │ (status=pending) │    │
                   │  └──────────┘      └────────┬─────────┘    │
                   │                             │               │
                   │                    ┌────────▼─────────┐    │
                   │                    │ EXECUTOR          │    │
                   │                    │ (interventions)   │    │
                   │                    └────────┬─────────┘    │
                   │                             │               │
                   │              ┌──────────────┼───────────┐  │
                   │              │              │            │  │
                   │         ┌────▼────┐  ┌─────▼─────┐ ┌───▼──┐
                   │         │Agent    │  │risk_audit  │ │risk_ │
                   │         │is_active│  │_log        │ │events│
                   │         │llm_conf │  │(snapshot)  │ │=exec │
                   │         └─────────┘  └───────────┘ └──────┘
                   └─────────────────────────────────────────────┘

  Reads from:
    ├── obs_events (cost_usd sums)
    ├── obs_agent_daily_metrics (future: error rates, token rates)
    └── risk_policies (thresholds, action types, cooldowns)
```

### 3.2 Module Responsibilities

#### `policy.py` — Policy Layer

Defines policy structure and CRUD helpers. Does **not** evaluate or enforce.

- `get_active_policies(workspace_id) -> list[RiskPolicy]`
- `get_policy(policy_id, workspace_id) -> RiskPolicy | None`
- Policy types: `daily_spend_cap` (v1), `error_rate_cap` (future), `token_rate_cap` (future)
- Action types: `alert_only`, `throttle`, `model_downgrade`, `pause_agent`

#### `evaluator.py` — Breach Detection

Reads metrics, compares against policy thresholds, creates `risk_events`. Does **not** execute actions.

- `evaluate_policies(workspace_id=None) -> int` — Evaluate all active policies (or for a specific workspace). Returns count of new risk_events created.
- `_evaluate_daily_spend(policy) -> Decimal | None` — Query real-time daily spend.
- `_check_cooldown(policy) -> bool` — Respect cooldown window.
- `_check_duplicate(policy, breach_value) -> bool` — Prevent duplicate pending events.

**Idempotency guarantee:** Before creating a risk_event, check for existing `pending` or `executed` event for the same (policy_id, date). If found, skip.

#### `interventions.py` — Action Executor

Processes pending risk_events. Executes the action, records audit trail, marks event complete.

- `execute_pending_events(max_events=50) -> int` — Process pending risk_events. Returns count executed.
- `_execute_alert_only(event) -> dict` — Dispatch notification (reuse `dispatch_alert_notification`).
- `_execute_throttle(event) -> dict` — Reduce agent rate config (future, no-op in v1).
- `_execute_model_downgrade(event) -> dict` — Switch agent to cheaper model.
- `_execute_pause_agent(event) -> dict` — Set `Agent.is_active = False`.
- `_snapshot_agent_state(agent) -> dict` — Capture current state before modification.
- `_mark_executed(event, result) -> None` — Update event status, write audit log.

**Reversibility:** Every intervention stores a `previous_state` snapshot in `risk_audit_log`, enabling manual or automated rollback.

**Duplicate prevention:** Events are processed only if `status == 'pending'`. The executor uses a `SELECT ... FOR UPDATE` pattern (or optimistic check-and-set) to prevent concurrent execution.

#### `enforcement_worker.py` — Async Worker

Orchestrates periodic evaluation and execution. Never runs inside HTTP request cycles.

- `run_enforcement_cycle() -> dict` — Run one full evaluate-then-execute cycle. Returns summary.
- `run_evaluation_only() -> int` — Run evaluator only (for testing).
- `run_execution_only() -> int` — Run executor only (for testing).

**Deployment:** Called from a cron endpoint (`POST /api/obs/internal/enforce-risk`), same pattern as existing `/api/obs/internal/evaluate-alerts`. The worker runs synchronously within the cron request but is **async relative to user API requests**.

#### `audit_log.py` — Audit Trail

All state changes are logged with before/after snapshots.

- `log_intervention(event_id, action_type, agent_id, previous_state, new_state, result) -> RiskAuditLog`
- `get_audit_trail(workspace_id, policy_id=None, agent_id=None, limit=100) -> list[RiskAuditLog]`

---

## 4. Database Schema

### 4.1 `risk_policies`

```
Column               Type                  Notes
─────────────────────────────────────────────────────
id                   INTEGER PK AUTO
workspace_id         INTEGER FK(users.id)  NOT NULL, indexed
agent_id             INTEGER FK(agents.id) NULL (NULL = workspace-wide)
policy_type          VARCHAR(50)           NOT NULL ('daily_spend_cap', 'error_rate_cap', 'token_rate_cap')
threshold_value      DECIMAL(12,4)         NOT NULL (no floats)
action_type          VARCHAR(50)           NOT NULL ('alert_only', 'throttle', 'model_downgrade', 'pause_agent')
cooldown_minutes     INTEGER               NOT NULL DEFAULT 360
is_enabled           BOOLEAN               NOT NULL DEFAULT TRUE
created_at           DATETIME              NOT NULL DEFAULT utcnow
updated_at           DATETIME              NOT NULL DEFAULT utcnow

UNIQUE(workspace_id, agent_id, policy_type)  -- one policy per type per scope
INDEX(workspace_id, is_enabled)
```

### 4.2 `risk_events`

```
Column               Type                  Notes
─────────────────────────────────────────────────────
id                   INTEGER PK AUTO
uid                  VARCHAR(36) UNIQUE    UUID for deduplication
policy_id            INTEGER FK(risk_policies.id) NOT NULL
workspace_id         INTEGER FK(users.id)  NOT NULL
agent_id             INTEGER FK(agents.id) NULL
policy_type          VARCHAR(50)           NOT NULL (denormalized for query speed)
breach_value         DECIMAL(12,4)         NOT NULL (the metric value that triggered)
threshold_value      DECIMAL(12,4)         NOT NULL (snapshot of threshold at detection)
action_type          VARCHAR(50)           NOT NULL (snapshot of action at detection)
status               VARCHAR(20)           NOT NULL DEFAULT 'pending'
                                           ('pending', 'executed', 'skipped', 'failed')
evaluated_at         DATETIME              NOT NULL DEFAULT utcnow
executed_at          DATETIME              NULL
execution_result     JSON                  NULL (executor output)
dedupe_key           VARCHAR(100) UNIQUE   NULL (policy_id + date for daily dedup)

INDEX(workspace_id, status)
INDEX(policy_id, status)
INDEX(status, evaluated_at)
```

**Deduplication key format:** `f"{policy_id}:{date_str}"` for daily policies. Ensures exactly one event per policy per day.

### 4.3 `risk_audit_log`

```
Column               Type                  Notes
─────────────────────────────────────────────────────
id                   INTEGER PK AUTO
event_id             INTEGER FK(risk_events.id) NOT NULL
workspace_id         INTEGER FK(users.id)  NOT NULL
agent_id             INTEGER FK(agents.id) NULL
action_type          VARCHAR(50)           NOT NULL
previous_state       JSON                  NOT NULL (snapshot before intervention)
new_state            JSON                  NOT NULL (snapshot after intervention)
result               VARCHAR(20)           NOT NULL ('success', 'failed', 'skipped')
error_message        TEXT                  NULL
created_at           DATETIME              NOT NULL DEFAULT utcnow

INDEX(workspace_id, created_at)
INDEX(event_id)
```

---

## 5. Design Principles & Constraints

### 5.1 Asynchronous Only

The risk engine **never** runs during HTTP request processing. All evaluation and execution happens in the enforcement worker, triggered by cron or manual admin endpoint.

**Why:** Interventions modify agent state. Doing this mid-request could cause race conditions, partial state, or user-visible latency.

### 5.2 Deterministic

Given the same policy configuration and metric state, the evaluator always produces the same result. No randomness, no time-dependent sampling, no probabilistic thresholds.

**Implementation:** Queries use `>=` comparison of `Decimal` values. Cooldown uses `last event evaluated_at + cooldown_minutes > now` — deterministic given wall clock.

### 5.3 Auditable

Every intervention writes to `risk_audit_log` with full before/after snapshots. The audit trail is append-only — no updates or deletes.

**Queryable by:** workspace, agent, policy, date range.

### 5.4 Idempotent

Running the enforcement cycle multiple times produces the same outcome:

1. **Evaluator:** Checks for existing pending/executed event for (policy_id, date) before creating a new one. Uses `dedupe_key` unique constraint.
2. **Executor:** Only processes events with `status = 'pending'`. Uses optimistic concurrency (check status before update) to prevent double-execution.

### 5.5 Reversible

Every action stores a `previous_state` snapshot. Reversal can be:
- **Manual:** Admin reviews audit log, restores agent state.
- **Automatic (future):** When policy is disabled or threshold raised, pending events can be auto-skipped.

### 5.6 No Float Math

All threshold comparisons use `Decimal`. Policy `threshold_value` is `DECIMAL(12,4)`. Breach values from cost queries are already `Decimal` (from the cost engine). No `float()` conversion in comparison paths.

### 5.7 No Observability Core Modifications

The risk engine is a **consumer** of observability data. It reads `obs_events`, `obs_agent_daily_metrics`, and uses `workspace.py` helpers. It does not modify any observability table, module, or behavior.

---

## 6. Interaction with Existing Alert Engine

| Concern | Alert Engine | Risk Engine |
|---|---|---|
| Purpose | Notify humans | Take automated action |
| Data source | Same (`obs_events`, metrics) | Same |
| Output | `obs_alert_events` + Slack | `risk_events` + agent state change + `risk_audit_log` |
| Triggered by | Cron (`/api/obs/internal/evaluate-alerts`) | Cron (`/api/obs/internal/enforce-risk`) |
| Cooldown | Per-rule `cooldown_minutes` | Per-policy `cooldown_minutes` |
| Scope | User-defined alert rules | Admin/user-defined risk policies |
| Overlap | Both can detect `cost_per_day` exceeding a threshold | Alert at $5 (warn), risk policy at $10 (pause). Different thresholds, complementary. |

**No coupling:** The risk engine does not read from or write to `obs_alert_rules` or `obs_alert_events`. They are independent subsystems.

---

## 7. Cron Integration

New endpoint added to the existing cron pattern:

```
POST /api/obs/internal/enforce-risk
Authorization: Bearer <CRON_SECRET>
```

Suggested schedule: **Every 5 minutes** (more aggressive than alert evaluation at 15min, because interventions are time-sensitive).

The endpoint calls `run_enforcement_cycle()` which:
1. Runs `evaluate_policies()` — creates pending risk_events for breached policies.
2. Runs `execute_pending_events()` — processes pending events, executes interventions.
3. Returns summary JSON.

Time-guarded to 45 seconds (same pattern as alert engine) to stay within Vercel's 60s limit.

---

## 8. V1 Scope — `daily_spend_cap` Only

Phase 5 implements one end-to-end guardrail:

| Aspect | V1 Behavior |
|---|---|
| Policy type | `daily_spend_cap` |
| Metric source | `SUM(obs_events.cost_usd) WHERE created_at >= today AND user_id = workspace_id` (optionally filtered by `agent_id`) |
| Threshold | `Decimal` USD value |
| Action | `pause_agent` — set `Agent.is_active = False` |
| Cooldown | Default 360 minutes (6 hours) |
| Dedupe | One event per (policy_id, date) |
| Audit | Full snapshot of `Agent.is_active` and `Agent.llm_config` before/after |

Future policy types (`error_rate_cap`, `token_rate_cap`) follow the same pattern with different metric queries.

---

## 9. Testing Strategy

| Layer | Test Type | What's Verified |
|---|---|---|
| Policy | Schema/unit | CRUD, unique constraints, Decimal storage |
| Evaluator | Unit | Breach detection, cooldown respect, idempotency (no duplicates) |
| Executor | Unit | Each action type, audit log creation, state snapshots, duplicate prevention |
| Worker | Integration | Full cycle: seed agent → simulate cost → verify event → verify intervention → verify audit |
| Safety | Failure simulation | Executor crash mid-execution → restart → no duplicate action |
| Safety | Cooldown | Policy fires → cooldown active → re-evaluation skips |
| Safety | Idempotency | Multiple worker runs → same outcome |

All tests use the existing `conftest.py` fixtures (`app`, `user`, `agent`, `_clean_db`). New fixtures added for `risk_policy` and `obs_events_with_cost`.

---

## 10. File Change Summary (Planned)

### New Files

| File | Purpose |
|---|---|
| `core/risk_engine/__init__.py` | Public API exports |
| `core/risk_engine/policy.py` | Policy helpers |
| `core/risk_engine/evaluator.py` | Breach detection |
| `core/risk_engine/interventions.py` | Action execution |
| `core/risk_engine/enforcement_worker.py` | Async worker |
| `core/risk_engine/audit_log.py` | Audit trail helpers |
| `tests/test_risk_engine.py` | All risk engine tests |

### Modified Files

| File | Change |
|---|---|
| `models.py` | Add `RiskPolicy`, `RiskEvent`, `RiskAuditLog` models |
| `server.py` | Register risk engine cron route |
| `routes/observability_routes.py` | Add `/api/obs/internal/enforce-risk` cron endpoint |

### Not Modified

| File | Reason |
|---|---|
| `core/observability/*` | Read-only consumer — no modifications |
| `tests/test_observability.py` | Existing tests untouched |
| `tests/test_observability_v2.py` | Existing tests untouched |
| `tests/conftest.py` | Existing fixtures untouched (new fixtures in test file) |
