# Human-Approved Policy Delegation System — Architecture

**Status:** PHASE 0 — Architecture Design (No Code)
**Date:** 2026-02-12
**Extends:** Risk Policy & Intervention Engine (`core/risk_engine/`)

---

## 1. Motivation

The existing risk engine enforces policies **automatically** — when a threshold is breached, interventions fire without human review. Policies themselves are created through direct database manipulation or future admin endpoints, with no mechanism for agents to request policy adjustments or for humans to delegate bounded autonomy.

This creates two gaps:

1. **Agents cannot request changes.** An agent hitting a spend cap cannot ask for a temporary increase. A human must notice the intervention, navigate to the policy, and manually adjust it — an entirely out-of-band process.

2. **There is no bounded delegation.** An admin cannot say "Agent X may increase its own daily spend cap by up to $5 for the next 2 hours." All policy mutation is unrestricted or nonexistent — there is no middle ground.

The Human-Approved Policy Delegation System closes both gaps by introducing:
- A **request pipeline** for agents to propose policy changes.
- A **human approval gate** that is never bypassable.
- **Delegation grants** that give agents bounded, time-limited autonomy.
- **Immutable workspace boundaries** that no delegation can exceed.
- A **governance audit log** that records every request, approval, application, and rollback.

---

## 2. Existing System — What We Build On

### 2.1 Risk Engine (unchanged, read-only consumer)

| Component | Location | Relationship |
|---|---|---|
| `policy.py` | `core/risk_engine/policy.py` | We read policies. We never bypass the policy layer. |
| `evaluator.py` | `core/risk_engine/evaluator.py` | Unchanged. Evaluates policies as-is. |
| `interventions.py` | `core/risk_engine/interventions.py` | Unchanged. Executes pending events. |
| `enforcement_worker.py` | `core/risk_engine/enforcement_worker.py` | Unchanged. Cron-triggered orchestrator. |
| `audit_log.py` | `core/risk_engine/audit_log.py` | Unchanged. We add a separate governance audit log. |

**Principle:** The governance layer sits *above* the risk engine. It modifies `RiskPolicy` rows through a controlled pipeline. The risk engine continues to read and enforce whatever policies exist — it is unaware of governance.

### 2.2 Workspace Isolation (`core/observability/workspace.py`)

- `workspace_id == user_id` (v1 identity mapping).
- All governance tables include `workspace_id`.
- All queries are workspace-scoped.
- No cross-workspace data leakage.

### 2.3 Tier System (`models.py: WorkspaceTier`)

Workspace tiers define hard limits (agent count, retention, API keys, etc.). The governance system introduces a new concept: **immutable boundaries** — workspace-level caps that no delegation can exceed. These are derived from but independent of the tier system.

### 2.4 Existing Approval Pattern (`models.py: AgentAction`)

The `AgentAction` model implements a `pending -> approved -> executed` lifecycle for AI-proposed actions (emails, trades). The governance system follows the same pattern but for **policy changes** rather than external actions.

| Concern | AgentAction (existing) | PolicyChangeRequest (new) |
|---|---|---|
| Who proposes | AI agent | AI agent |
| What is proposed | External action (email, trade) | Policy modification (threshold change) |
| Who approves | Human (dashboard) | Human (admin/owner) |
| What happens on approval | Action executes | Policy updates OR delegation grant created |
| Reversibility | Depends on action | Always (policy snapshot stored) |

---

## 3. New Subsystem Design

```
core/governance/
    __init__.py               # Public API exports
    requests.py               # Policy change request CRUD
    approvals.py              # Human approval/denial logic
    delegation.py             # Delegation grant management + enforcement
    boundaries.py             # Immutable workspace boundary checks
    governance_audit.py       # Governance-specific audit trail
```

### 3.1 Data Flow

```
                    AGENT RUNTIME
                         │
                         ▼
              ┌─────────────────────┐
              │  POST /api/gov/     │
              │  request            │
              │  (agent submits     │
              │   policy change)    │
              └────────┬────────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │ policy_change_      │
              │ requests            │
              │ (status=pending)    │
              └────────┬────────────┘
                       │
            ┌──────────┴──────────┐
            │                     │
            ▼                     ▼
    HUMAN DENIES          HUMAN APPROVES
    (status=denied)       (chooses mode)
                          ┌───────┴───────┐
                          │               │
                          ▼               ▼
                   ONE-TIME APPLY   DELEGATION GRANT
                          │               │
                          ▼               ▼
                   ┌──────────┐    ┌──────────────┐
                   │ Validate │    │ delegation_  │
                   │ against  │    │ grants       │
                   │ immutable│    │ (time-bound) │
                   │ bounds   │    └──────┬───────┘
                   └────┬─────┘           │
                        │                 ▼
                        ▼          ┌──────────────┐
                   ┌──────────┐   │ Agent uses    │
                   │ Mutate   │   │ grant to self-│
                   │ RiskPol. │   │ apply changes │
                   │ (atomic) │   │ within bounds │
                   └────┬─────┘   └──────┬───────┘
                        │                │
                        ▼                ▼
                   ┌──────────────────────────┐
                   │ governance_audit_log     │
                   │ (every state transition) │
                   └──────────────────────────┘

  Immutable boundary check applies to ALL paths:
    ├── One-time apply
    ├── Delegation grant creation
    └── Agent self-apply via delegation
```

### 3.2 Module Responsibilities

#### `requests.py` — Policy Change Request Pipeline

Handles the creation and lifecycle of agent-submitted policy change requests.

- `create_request(workspace_id, agent_id, requested_changes, reason) -> PolicyChangeRequest`
- `get_requests(workspace_id, status=None, limit=50) -> list`
- `get_request(request_id, workspace_id) -> PolicyChangeRequest | None`
- `expire_stale_requests(max_age_hours=24) -> int`

**Requested changes format (JSON diff):**
```json
{
  "policy_id": 42,
  "field": "threshold_value",
  "current_value": "10.0000",
  "requested_value": "15.0000"
}
```

Only `threshold_value` and `action_type` fields are mutable via requests. `policy_type`, `workspace_id`, and `agent_id` are structural — cannot be changed through delegation.

**Cooldown:** A workspace can submit at most 1 request per policy per 15 minutes (configurable). Prevents request-spam.

#### `approvals.py` — Human Approval Gate

Processes human decisions on pending requests. This is the **only** module that transitions requests from `pending` to `approved`/`denied`.

- `approve_request(request_id, workspace_id, approver_id, mode, delegation_params=None) -> dict`
- `deny_request(request_id, workspace_id, approver_id, reason=None) -> dict`

**Approval modes:**

| Mode | Behavior | Result |
|---|---|---|
| `one_time` | Apply the requested change immediately | Policy mutated, snapshot stored, audit logged |
| `delegate` | Create a time-bound delegation grant | Grant created, agent can self-apply within bounds |

**Critical constraints:**
- `approver_id != agent_id` — an agent cannot approve its own request.
- Approver must be the workspace owner or an admin.
- All approvals are validated against immutable boundaries before execution.

#### `delegation.py` — Delegation Grant Management

Manages time-bound, bounded autonomy grants.

- `create_grant(workspace_id, agent_id, allowed_changes, duration_minutes, ...) -> DelegationGrant`
- `get_active_grants(workspace_id, agent_id=None) -> list`
- `apply_delegated_change(grant_id, workspace_id, agent_id, requested_change) -> dict`
- `expire_grants() -> int` — called by cron to deactivate expired grants.
- `revoke_grant(grant_id, workspace_id) -> bool` — human-initiated revocation.

**Grant enforcement:**
1. Grant must be `active=True` and `valid_from <= now <= valid_to`.
2. Requested change must fall within `allowed_changes` constraints.
3. Resulting policy state must not exceed workspace immutable boundaries.
4. Grants do not stack — applying a change via one grant does not expand another grant's bounds.

#### `boundaries.py` — Immutable Workspace Boundaries

Defines and enforces hard limits that no delegation can exceed.

- `get_workspace_boundaries(workspace_id) -> dict`
- `validate_against_boundaries(workspace_id, policy_id, field, new_value) -> (bool, str|None)`
- `IMMUTABLE_BOUNDARIES` — default hard caps per tier

**Immutable boundary concept:**

| Boundary | Source | Example | Can agent exceed? | Can human exceed? |
|---|---|---|---|---|
| `max_daily_spend_cap` | Derived from tier | Free: $50, Pro: $500 | Never | Never (tier upgrade required) |
| `min_cooldown_minutes` | System constant | 30 minutes | Never | Never |
| `forbidden_action_downgrades` | System constant | Cannot change `pause_agent` to `alert_only` | Never | Never |

Boundaries are enforced at three points:
1. When a human approves a one-time change.
2. When a human creates a delegation grant (grant bounds cannot exceed workspace bounds).
3. When an agent applies a change via a delegation grant.

#### `governance_audit.py` — Governance Audit Trail

Append-only log for all governance events. Separate from `risk_audit_log` (which tracks interventions).

- `log_governance_event(workspace_id, agent_id, event_type, details) -> GovernanceAuditLog`
- `get_governance_trail(workspace_id, event_type=None, limit=100) -> list`

---

## 4. Database Schema

### 4.1 `policy_change_requests`

```
Column               Type                  Notes
─────────────────────────────────────────────────────
id                   INTEGER PK AUTO
workspace_id         INTEGER FK(users.id)  NOT NULL, indexed
agent_id             INTEGER FK(agents.id) NOT NULL (the requesting agent)
policy_id            INTEGER FK(risk_policies.id) NULL (NULL = new policy request)
requested_changes    JSON                  NOT NULL (diff: field, current, requested)
reason               TEXT                  NOT NULL (agent's justification)
status               VARCHAR(20)           NOT NULL DEFAULT 'pending'
                                           ('pending', 'approved', 'denied', 'expired', 'applied')
requested_at         DATETIME              NOT NULL DEFAULT utcnow
reviewed_by          INTEGER FK(users.id)  NULL (the human who acted)
reviewed_at          DATETIME              NULL
expires_at           DATETIME              NULL (auto-expire stale requests)
policy_snapshot      JSON                  NULL (snapshot of policy state at request time)

INDEX(workspace_id, status)
INDEX(agent_id, status)
INDEX(status, requested_at)     -- for expiration queries
```

**Status lifecycle:**
```
pending ──┬──> approved ──> applied
          ├──> denied
          └──> expired
```

- `pending`: Submitted by agent, awaiting human review.
- `approved`: Human approved but change not yet applied (intermediate state for delegation mode).
- `denied`: Human rejected the request.
- `expired`: Request sat `pending` beyond `expires_at` without human action.
- `applied`: The requested change was applied to the policy (terminal state).

### 4.2 `delegation_grants`

```
Column               Type                  Notes
─────────────────────────────────────────────────────
id                   INTEGER PK AUTO
workspace_id         INTEGER FK(users.id)  NOT NULL, indexed
agent_id             INTEGER FK(agents.id) NOT NULL (the delegated agent)
request_id           INTEGER FK(policy_change_requests.id) NULL (originating request)
granted_by           INTEGER FK(users.id)  NOT NULL (the human who granted)
allowed_changes      JSON                  NOT NULL (constraint envelope)
max_spend_delta      DECIMAL(12,4)         NULL (max threshold increase allowed)
max_model_upgrade    VARCHAR(50)           NULL (highest model tier allowed)
duration_minutes     INTEGER               NOT NULL
valid_from           DATETIME              NOT NULL DEFAULT utcnow
valid_to             DATETIME              NOT NULL (computed: valid_from + duration)
active               BOOLEAN               NOT NULL DEFAULT TRUE
revoked_at           DATETIME              NULL
revoked_by           INTEGER FK(users.id)  NULL

INDEX(workspace_id, agent_id, active)
INDEX(active, valid_to)          -- for expiration queries
```

**`allowed_changes` JSON schema:**
```json
{
  "policy_id": 42,
  "fields": {
    "threshold_value": {
      "max_value": "20.0000",
      "min_value": "10.0000"
    }
  }
}
```

The grant defines an **envelope** — the agent can adjust `threshold_value` to any value within `[min_value, max_value]`, but never beyond. The envelope itself must be within workspace immutable boundaries.

**Lifecycle:**
- `active=True, now <= valid_to`: Grant is usable.
- `active=True, now > valid_to`: Expired — cron sets `active=False`.
- `active=False, revoked_at != NULL`: Human revoked.
- `active=False, revoked_at == NULL`: Expired naturally.

### 4.3 `governance_audit_log`

```
Column               Type                  Notes
─────────────────────────────────────────────────────
id                   INTEGER PK AUTO
workspace_id         INTEGER FK(users.id)  NOT NULL
agent_id             INTEGER FK(agents.id) NULL
actor_id             INTEGER FK(users.id)  NULL (human who acted, NULL for system events)
event_type           VARCHAR(50)           NOT NULL
details              JSON                  NOT NULL
created_at           DATETIME              NOT NULL DEFAULT utcnow

INDEX(workspace_id, created_at)
INDEX(workspace_id, event_type)
```

**Event types:**
```
request_submitted     — agent submitted a policy change request
request_expired       — request auto-expired
request_approved      — human approved (one-time or delegation)
request_denied        — human denied
change_applied        — policy was mutated (includes before/after snapshot)
change_rolled_back    — policy was reverted to previous state
grant_created         — delegation grant was created
grant_expired         — grant expired naturally
grant_revoked         — human revoked a grant
grant_used            — agent applied a change via grant
boundary_violation    — a request or application was rejected by boundary check
```

**`details` JSON always contains:**
```json
{
  "request_id": 1,
  "policy_id": 42,
  "reason": "...",
  "policy_before": { ... },
  "policy_after": { ... }
}
```

Fields vary by event type, but `policy_before` / `policy_after` are always present for mutation events, ensuring full reversibility.

---

## 5. Immutable Boundary System

### 5.1 Boundary Definitions

Boundaries are **hard caps** derived from the workspace tier and system constants. They cannot be exceeded by any mechanism — not by agent requests, not by human approval, not by delegation grants.

```python
# System constants (never changeable at runtime)
SYSTEM_BOUNDARIES = {
    'min_cooldown_minutes': 30,       # No policy can have < 30 min cooldown
    'max_policies_per_workspace': 50,  # Hard cap on policy count
}

# Tier-derived boundaries
TIER_BOUNDARIES = {
    'free':       {'max_daily_spend_cap': Decimal('50.00')},
    'production': {'max_daily_spend_cap': Decimal('200.00')},
    'pro':        {'max_daily_spend_cap': Decimal('500.00')},
    'agency':     {'max_daily_spend_cap': Decimal('2000.00')},
}
```

### 5.2 Enforcement Points

| Enforcement Point | What Is Checked | On Failure |
|---|---|---|
| `approve_request()` (one-time) | Requested value within boundary | Approval rejected, audit logged |
| `create_grant()` | Grant envelope within boundary | Grant not created, audit logged |
| `apply_delegated_change()` | Final policy value within boundary | Application rejected, audit logged |

### 5.3 Structural Immutability

Certain policy fields are **structurally immutable** — they define the policy's identity and cannot be changed via the governance pipeline:

| Field | Mutable via governance? | Reason |
|---|---|---|
| `policy_type` | No | Changes the fundamental nature of the policy |
| `workspace_id` | No | Would break workspace isolation |
| `agent_id` | No | Would change the policy's scope |
| `threshold_value` | Yes | The primary tunable parameter |
| `action_type` | Restricted | Can only escalate (e.g., `alert_only` -> `pause_agent`), never de-escalate |
| `cooldown_minutes` | Yes | Subject to `min_cooldown_minutes` boundary |
| `is_enabled` | No | Disabling a policy removes a safety net; must be done by human directly |

---

## 6. Safety Invariants

These invariants must hold at all times. Tests will verify each one.

### 6.1 No Silent Mutation

**Invariant:** Every mutation to a `RiskPolicy` row that originates from an agent must pass through the request pipeline. Direct policy mutation by agent code is forbidden.

**Enforcement:** The governance module is the only code path that modifies `RiskPolicy` in response to agent requests. The risk engine's `policy.py` is read-only. Agent routes do not have write access to `risk_policies`.

### 6.2 Human Authority Preserved

**Invariant:** No policy change is applied without explicit human approval (either direct approval or pre-authorized delegation).

**Enforcement:** `approve_request()` and `create_grant()` require `approver_id` that is verified as the workspace owner or admin. Agents cannot call approval endpoints (session-based auth, not API-key auth).

### 6.3 Boundary Inviolability

**Invariant:** No policy value can exceed workspace immutable boundaries, regardless of who requests or approves it.

**Enforcement:** `validate_against_boundaries()` is called in all three mutation paths (one-time apply, grant creation, delegated apply). There is no bypass.

### 6.4 Time-Bounded Delegation

**Invariant:** Every delegation grant has a finite duration. No perpetual grants.

**Enforcement:** `duration_minutes` is required and capped (max 1440 = 24 hours). `valid_to` is computed as `valid_from + duration`. Cron expires stale grants.

### 6.5 No Grant Stacking

**Invariant:** An agent cannot combine multiple grants to exceed any single grant's bounds.

**Enforcement:** Each `apply_delegated_change()` validates the resulting policy value against the specific grant's `allowed_changes` envelope AND workspace boundaries. The current policy state is irrelevant to the grant's bounds — the grant defines absolute limits, not relative ones.

### 6.6 Full Auditability

**Invariant:** Every state transition — request, approval, denial, application, expiration, revocation, rollback, boundary violation — is recorded in `governance_audit_log` with timestamps, actor IDs, and before/after snapshots.

**Enforcement:** `log_governance_event()` is called by every function that transitions state. The audit log is append-only (no update/delete operations).

### 6.7 Rollback Capability

**Invariant:** Any policy change applied through the governance pipeline can be reversed to its pre-change state.

**Enforcement:** `policy_snapshot` (stored in the request) and `policy_before` / `policy_after` (stored in the audit log) provide full state history. A `rollback_change(audit_entry_id)` function restores `policy_before` and logs a `change_rolled_back` event.

---

## 7. API Surface

### 7.1 Agent-Facing (API-key or session auth)

| Method | Path | Description |
|---|---|---|
| POST | `/api/governance/request` | Submit a policy change request |
| GET | `/api/governance/requests` | List own requests (scoped to workspace + agent) |

### 7.2 Human-Facing (Session auth, workspace owner/admin only)

| Method | Path | Description |
|---|---|---|
| POST | `/api/governance/approve/<request_id>` | Approve a request (one-time or delegate) |
| POST | `/api/governance/deny/<request_id>` | Deny a request |
| GET | `/api/governance/pending` | List pending requests for workspace |
| GET | `/api/governance/delegations` | List active delegation grants |
| POST | `/api/governance/delegations/<grant_id>/revoke` | Revoke a delegation grant |
| GET | `/api/governance/audit` | Query governance audit trail |
| POST | `/api/governance/rollback/<audit_id>` | Rollback a policy change |

### 7.3 Internal/Cron

| Method | Path | Description |
|---|---|---|
| POST | `/api/governance/internal/expire` | Expire stale requests and grants |

---

## 8. Integration with Existing Risk Engine

### 8.1 What Changes

| Component | Change |
|---|---|
| `risk_policies` table | Rows are now also mutated by the governance pipeline (in addition to direct admin CRUD). No schema change needed. |
| `models.py` | Three new models: `PolicyChangeRequest`, `DelegationGrant`, `GovernanceAuditLog` |
| `server.py` | Register governance routes |
| `routes/` | New `governance_routes.py` |

### 8.2 What Does NOT Change

| Component | Reason |
|---|---|
| `core/risk_engine/*` | Read-only consumer. Governance sits above it. |
| `core/observability/*` | No interaction. |
| `risk_events`, `risk_audit_log` | These track interventions, not policy changes. Separate concerns. |
| Existing tests | All 87+ risk engine tests continue to pass unchanged. |

### 8.3 Interaction Diagram

```
  AGENT ──────────────────────────────────────────────────────────┐
    │                                                              │
    │  POST /api/governance/request                                │
    │  {"policy_id": 42, "field": "threshold_value",              │
    │   "requested_value": "15.00", "reason": "need higher cap"}  │
    │                                                              │
    ▼                                                              │
  ┌────────────────────────┐                                       │
  │ policy_change_requests │                                       │
  │ status = pending       │                                       │
  └───────────┬────────────┘                                       │
              │                                                    │
              │  HUMAN reviews in dashboard                        │
              │                                                    │
              ▼                                                    │
  ┌────────────────────────┐                                       │
  │ approvals.py           │                                       │
  │ validate_against_      │                                       │
  │ boundaries()           │                                       │
  └───────────┬────────────┘                                       │
              │                                                    │
         ┌────┴────┐                                               │
         │         │                                               │
    one_time   delegate                                            │
         │         │                                               │
         ▼         ▼                                               │
  ┌──────────┐  ┌──────────────┐                                   │
  │ Mutate   │  │ delegation_  │◄──────────────────────────────────┘
  │ RiskPol. │  │ grants       │     Agent later calls:
  │ directly │  │ (time-bound) │     POST /api/governance/delegate/apply
  └──────────┘  └──────────────┘
         │              │
         ▼              ▼
  ┌─────────────────────────────┐
  │ governance_audit_log        │
  │ (append-only, every event)  │
  └─────────────────────────────┘
         │
         │  RISK ENGINE (unchanged, reads policies as-is)
         ▼
  ┌─────────────────────────────┐
  │ evaluator.py reads updated  │
  │ RiskPolicy rows normally    │
  │ — unaware of governance     │
  └─────────────────────────────┘
```

---

## 9. Rollback Mechanism

Every policy mutation stores a `policy_before` snapshot in the governance audit log. Rollback works as follows:

1. Human calls `POST /api/governance/rollback/<audit_id>`.
2. System loads the `policy_before` snapshot from the audit entry.
3. Validates the rollback against immutable boundaries (the previous state may no longer be valid if the tier changed).
4. Applies the snapshot to the `RiskPolicy` row.
5. Logs a `change_rolled_back` event in `governance_audit_log` with the rollback's own before/after snapshot.

Rollbacks are themselves auditable and reversible (a rollback can be rolled back).

---

## 10. Cron Integration

New cron job added alongside existing risk enforcement:

```
POST /api/governance/internal/expire
Authorization: Bearer <CRON_SECRET>
```

Suggested schedule: **Every 15 minutes**

The endpoint:
1. Expires pending requests older than 24 hours (`status='pending'` -> `status='expired'`).
2. Deactivates expired delegation grants (`active=True, valid_to < now` -> `active=False`).
3. Logs expiration events to `governance_audit_log`.

---

## 11. Testing Strategy

| Layer | Test Type | What Is Verified |
|---|---|---|
| Models | Schema | CRUD, constraints, JSON storage, status transitions |
| Requests | Unit | Create, list, expire, workspace isolation, cooldown |
| Approvals | Unit | Approve/deny, mode selection, self-approve blocked, admin-only |
| Boundaries | Unit | All boundary types, tier-derived limits, structural immutability |
| Delegation | Unit | Create, apply, expire, revoke, envelope enforcement, no stacking |
| Rollback | Unit | Forward/backward, boundary re-validation, audit trail |
| Governance Audit | Unit | Append-only, event types, queryable |
| Safety | Invariant | No silent mutation, human authority, boundary inviolability |
| QA | Failure sim | Crash mid-approval, expired grant attempt, boundary-exceeded request |
| Integration | E2E | Agent request -> human approve -> policy change -> risk engine sees it |
| Backwards compat | Regression | All 87+ existing risk engine tests pass unchanged |

---

## 12. File Change Summary (Planned)

### New Files

| File | Purpose |
|---|---|
| `core/governance/__init__.py` | Public API exports |
| `core/governance/requests.py` | Policy change request pipeline |
| `core/governance/approvals.py` | Human approval/denial logic |
| `core/governance/delegation.py` | Delegation grant management |
| `core/governance/boundaries.py` | Immutable boundary enforcement |
| `core/governance/governance_audit.py` | Governance audit trail |
| `routes/governance_routes.py` | REST API endpoints |
| `tests/test_governance.py` | All governance tests |
| `docs/governance/architecture.md` | This document |

### Modified Files

| File | Change |
|---|---|
| `models.py` | Add `PolicyChangeRequest`, `DelegationGrant`, `GovernanceAuditLog` models |
| `server.py` | Register governance routes, add cron endpoint |

### Not Modified

| File | Reason |
|---|---|
| `core/risk_engine/*` | Governance sits above — risk engine is unaware |
| `core/observability/*` | No interaction |
| `tests/test_risk_engine.py` | Existing tests unchanged |
| `tests/test_tier_enforcement.py` | Existing tests unchanged |
| `routes/observability_routes.py` | Risk cron endpoint unchanged |
