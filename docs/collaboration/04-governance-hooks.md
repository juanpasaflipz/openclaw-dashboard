# Phase 4 — Governance & Risk Integration

Hooks that connect the collaboration task system to the existing risk engine,
observability pipeline, and governance audit trail. All hooks are **best-effort**
— they never raise and never block task operations (except pre-start risk checks
which can block a task from starting).

---

## Hook lifecycle

```
Task queued
    │
    ▼
POST /tasks/<id>/start
    │
    ├── pre_task_start()        ← Risk check (blocking)
    │     ├─ agent.is_active?
    │     └─ pending risk events?
    │
    ├── [BLOCKED]               ← If risk check fails
    │     ├─ TaskEvent(blocked)
    │     └─ GovernanceAuditLog(task_blocked)
    │
    ├── [RUNNING]               ← If risk check passes
    │     └─ on_task_started()  ← ObsEvent(action_started)
    │
    ▼
POST /tasks/<id>/complete
    └─ on_task_completed()      ← ObsEvent(action_finished)

POST /tasks/<id>/fail
    └─ on_task_failed()         ← ObsEvent(error)

POST /tasks/<id>/assign
    ├─ on_task_reassigned()     ← GovernanceAuditLog(task_reassigned)
    └─ on_task_escalated()      ← GovernanceAuditLog(task_escalated)
                                   (only when target is supervisor)
```

---

## Hooks

### `pre_task_start(task)` — Blocking risk check

Called before a task transitions to `running`. Returns `(ok, reason)`.

**Checks:**
1. `agent.is_active` — Agent not paused by risk intervention
2. No pending `RiskEvent` for the assigned agent

**If blocked:**
- Task status set to `blocked` (not `running`)
- `TaskEvent` with `event_type='blocked'` emitted
- `GovernanceAuditLog` with `event_type='task_blocked'` recorded
- Response returns `409` with `blocked: true` and the reason

**Recovery:** Once the risk event is resolved (status changes from `pending`),
the task can be re-started via `POST /tasks/<id>/start` (blocked → running is
a valid transition).

### `on_task_started(task)` — Post-start observability

Emits an `action_started` event to the observability pipeline with:
- `agent_id`: the assigned agent
- `payload.source`: `'collaboration'`
- `payload.task_id`: the task ID
- `dedupe_key`: `collab:start:{task_id}`

### `on_task_completed(task, output)` — Post-complete observability

Emits an `action_finished` event with `status='success'` and an optional
output summary (truncated to 500 chars).

### `on_task_failed(task, reason)` — Post-fail observability

Emits an `error` event with `status='error'` and the failure reason.

### `on_task_blocked_by_risk(task, reason)` — Governance audit

Records a `task_blocked` entry in the governance audit trail with the
task details and the blocking reason.

### `on_task_escalated(task, from_agent_id, to_agent_id)` — Escalation audit

Records a `task_escalated` entry when a task is reassigned to a supervisor.
Logged alongside the standard `task_reassigned` entry.

### `on_task_reassigned(task, from_agent_id, to_agent_id)` — Reassignment audit

Records a `task_reassigned` entry for every task reassignment.

---

## New governance audit event types

| Event Type       | When                                   | Details                     |
|------------------|----------------------------------------|-----------------------------|
| task_blocked     | Pre-start risk check fails             | task_id, reason, agent_id   |
| task_escalated   | Reassignment to a supervisor agent     | task_id, from/to agent_ids  |
| task_reassigned  | Any task reassignment                  | task_id, from/to agent_ids  |

These events flow into the existing governance audit trail and are queryable
via `GET /api/governance/audit?event_type=task_blocked`.

---

## Observability integration

Collaboration events reuse existing `VALID_EVENT_TYPES`:

| Obs Event Type    | Collaboration Trigger | Status  |
|-------------------|-----------------------|---------|
| action_started    | Task starts           | info    |
| action_finished   | Task completes        | success |
| error             | Task fails            | error   |

All events include `payload.source = 'collaboration'` and `payload.task_id`
for filtering in the observability dashboard.

---

## Best-effort resilience

All post-transition hooks wrap their bodies in try/except and print errors
to stdout without propagating. This means:

- **Observability failure** does not prevent task completion
- **Governance audit failure** does not prevent task reassignment
- **Only `pre_task_start`** can block a task, and even it falls back to
  allowing the task if the risk check itself throws an exception

---

## Files

| File | Purpose |
|------|---------|
| `core/collaboration/__init__.py` | Package init |
| `core/collaboration/governance_hooks.py` | All 7 hook functions |
| `routes/collaboration_tasks_routes.py` | Hook call sites in `_transition_task` and `reassign_task` |
| `core/governance/governance_audit.py` | Updated docstring with new event types |
| `models.py` | Added `blocked`, `canceled` to `TaskEvent.VALID_EVENT_TYPES` |
| `tests/test_collaboration_governance.py` | 17 tests |

---

## Test summary

```
tests/test_collaboration_governance.py — 17 passed

TestPreStartRiskCheck (6):
  - start allowed when agent healthy
  - start blocked when agent paused (409, status=blocked)
  - start blocked when pending risk event (409)
  - blocked task emits TaskEvent(blocked)
  - blocked task logs GovernanceAuditLog(task_blocked)
  - blocked task can be started after risk resolution

TestObservabilityEmission (3):
  - start emits action_started (mocked)
  - complete emits action_finished (mocked)
  - fail emits error event (mocked)

TestGovernanceAuditTrail (5):
  - escalation logged (task_escalated)
  - reassignment logged (task_reassigned)
  - escalation creates both reassigned + escalated
  - no escalation for non-supervisor target
  - governance audit queryable via existing API

TestBestEffortResilience (3):
  - task completes even if observability fails
  - task starts even if observability fails
  - reassignment succeeds even if audit fails
```
