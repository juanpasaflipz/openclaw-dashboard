# Phase 0 -- Architecture Review for Multi-Agent Collaboration

> **Date:** 2026-02-12
> **Status:** Audit complete -- no code changes
> **Scope:** Identify current constraints, propose collaboration design, and list every file touched per phase

---

## 1. Current Agent Model

**File:** `models.py:300-335`

```
Agent
  id              Integer PK
  user_id         FK -> users.id  (workspace scope)
  name            String(100)
  description     Text
  avatar_emoji    String(10) default '🤖'
  avatar_url      String(500)
  personality     Text
  moltbook_api_key String(255)
  is_active       Boolean default True
  is_default      Boolean default False
  llm_config      JSON   {provider, model, api_key, temperature, ...}
  identity_config JSON   {personality, role, behavior, ...}
  moltbook_config JSON   {api_key, default_submolt, ...}
  total_posts     Integer default 0
  last_post_at    DateTime
  created_at      DateTime
  updated_at      DateTime
```

**Relationships (backref):** superpowers, agent_actions, analytics_snapshots,
post_analytics, obs_events, obs_runs, obs_daily_metrics, obs_health_scores,
obs_alert_rules.

**Agent routes** (`routes/agent_routes.py`):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/agents` | List user's agents (tier-limited count) |
| POST | `/api/agents` | Create agent (tier-checked) |
| GET | `/api/agents/<id>` | Get single agent |
| PUT | `/api/agents/<id>` | Update agent |
| DELETE | `/api/agents/<id>` | Delete agent |
| POST | `/api/agents/<id>/clone` | Clone agent (line 235) |
| GET | `/api/agents/<id>/export` | Export agent as JSON |

**Key constraint:** Every query filters by `user_id` for workspace isolation.
Clone already exists at `agent_routes.py:235-278` -- copies name, description,
avatar_emoji, llm_config, identity_config, moltbook_config; enforces tier
agent_limit.

---

## 2. Workspace / Multi-Tenancy Model

**Current design: workspace_id == user_id (single-tenant v1)**

Abstraction layer at `core/observability/workspace.py`:

```python
def get_workspace_id(user_id):
    return user_id       # v1 identity mapping

def scope_query(query, model_class, user_id):
    return query.filter(model_class.user_id == get_workspace_id(user_id))

def verify_agent_ownership(agent_id, user_id):
    return Agent.query.filter_by(id=agent_id, user_id=get_workspace_id(user_id)).first()
```

**Tier system** (`models.py:976-1044`, `core/observability/tier_enforcement.py`):

| Tier | agent_limit | retention_days | alert_rules | api_keys | multi_workspace |
|------|-------------|----------------|-------------|----------|-----------------|
| free | 2 | 7 | 0 | 1 | No |
| production | 10 | 30 | 3 | 3 | No |
| pro | 50 | 90 | 9999 | 10 | No |
| agency | 9999 | 180 | 9999 | 9999 | Yes |

**Implication for collaboration:** The collaboration framework will scope all
new tables with `workspace_id` (FK -> users.id) to remain consistent with the
existing pattern. When multi-workspace lands, the `get_workspace_id()` mapping
changes in one place.

---

## 3. Risk & Governance Systems

### 3a. Risk Policy Engine

**Models** (`models.py:1088-1207`):
- `RiskPolicy` -- per-agent or workspace-wide policies (daily_spend_cap, error_rate_cap, token_rate_cap)
- `RiskEvent` -- detected breaches (status: pending -> executed/skipped/failed)
- `RiskAuditLog` -- append-only intervention audit with before/after snapshots

**Core modules:**
- `core/risk_engine/policy.py` -- CRUD for policies
- `core/risk_engine/evaluator.py` -- metric evaluation + dedupe + cooldown
- `core/risk_engine/interventions.py` -- action execution (alert, pause, model_downgrade, throttle)
- `core/risk_engine/enforcement_worker.py` -- time-budgeted cron cycle (45s budget for Vercel)

**Action types with escalation-only constraint:**
```
alert_only (0) < throttle (1) < model_downgrade (2) < pause_agent (3)
```

### 3b. Policy Delegation (Human-Approved)

**Models** (`models.py:1214-1310`):
- `PolicyChangeRequest` -- agents submit; humans approve/deny/expire
- `DelegationGrant` -- time-bound autonomy grants with allowed_changes envelope

**Core modules:**
- `core/governance/requests.py` -- request creation with 15-min cooldown
- `core/governance/approvals.py` -- one_time or delegate approval modes
- `core/governance/delegation.py` -- agent self-apply within grant envelope
- `core/governance/rollback.py` -- policy change reversal with boundary re-validation
- `core/governance/boundaries.py` -- immutable workspace boundaries (tier-derived)
- `core/governance/governance_audit.py` -- append-only governance event log

**Governance routes** (`routes/governance_routes.py`):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/governance/request` | Submit policy change |
| GET | `/api/governance/requests` | List requests |
| GET | `/api/governance/pending` | List pending |
| POST | `/api/governance/approve/<id>` | Approve (one_time or delegate) |
| POST | `/api/governance/deny/<id>` | Deny |
| POST | `/api/governance/delegate/apply` | Agent self-apply grant |
| GET | `/api/governance/delegations` | List active grants |
| POST | `/api/governance/delegations/<id>/revoke` | Revoke grant |
| POST | `/api/governance/rollback/<id>` | Rollback policy change |
| GET | `/api/governance/audit` | Query audit trail |
| POST | `/api/governance/internal/expire` | Cron: expire stale items |

### 3c. Governance Audit Trail

**Model** (`models.py:1313-1343`): `GovernanceAuditLog`

Event types: `request_submitted`, `request_expired`, `request_approved`,
`request_denied`, `change_applied`, `change_rolled_back`, `grant_created`,
`grant_expired`, `grant_revoked`, `grant_used`, `boundary_violation`.

---

## 4. Observability Layer

**Models** (`models.py:700-880`):

| Model | Purpose |
|-------|---------|
| `ObsApiKey` | Hashed API keys for event ingestion |
| `ObsEvent` | Append-only event log (cost, tokens, latency) |
| `ObsRun` | Single agent run aggregation |
| `ObsAgentDailyMetrics` | Pre-aggregated daily metrics |
| `ObsAlertRule` | User-defined alert thresholds |
| `ObsAlertEvent` | Fired alert history |
| `ObsLlmPricing` | Reference LLM token costs |
| `ObsAgentHealthDaily` | Composite daily health score |

**Ingestion** (`core/observability/ingestion.py`): `emit_event()` and
`emit_event_batch()` -- never raises, swallows errors.

**Tier enforcement** (`core/observability/tier_enforcement.py`): Cached tier
lookup (60s TTL), hard limits on agent count, batch size, retention window.

**Collaboration hook point:** Task start/complete events should use `emit_event()`
to flow into the existing observability pipeline. Cost tracking per agent remains
agent-scoped via `agent_id` on `ObsEvent`.

---

## 5. Agent Actions (Approval Queue)

**Model** (`models.py:462-520`): `AgentAction`

Fields: user_id, agent_id, action_type, service_type, action_data (JSON),
status (pending/approved/rejected/executed/failed), ai_reasoning, ai_confidence.

**Routes** (`routes/agent_actions_routes.py`):
- AI proposes action -> stored as `status='pending'`
- Human approves/rejects in dashboard
- If approved, backend executes via action_type+service_type dispatch

**Relevance:** The task system follows a similar pattern (agent proposes work,
state machine tracks lifecycle) but decouples execution from the approval queue.
Agent actions remain for external service calls; tasks are for inter-agent work.

---

## 6. External Agents

**Model** (`models.py:627-670`): `ExternalAgent`

Third-party agent registrations with connection_url, auth_config, agent_type
(websocket, http_api, marketplace).

**Routes** (`routes/external_agents_routes.py`): CRUD for external agents.

**Relevance:** The collaboration framework handles internal Agent-to-Agent
coordination. External agents remain a separate integration path.

---

## 7. Frontend Architecture

### Tab System

**Navigation** (`dashboard.html:43-147`): Dropdown-based hierarchy with
`data-tab` attributes and `data-group` for parent groups.

**Groups:** agents, workbench, integrations, social, account.

**Tab switching** (`static/js/dashboard-main.js:76-122`): `switchTab(tabName)`
clears all active states, activates matching nav button + content div, calls
tab-specific init function.

**Group mapping** (`dashboard-main.js:37-64`): `TAB_GROUP_MAP` dict maps
tab IDs to their parent group.

### Rendering Pattern

- No framework -- vanilla JS with template literals
- `fetch()` with `credentials: 'include'` for all API calls
- `.map()` + `.join('')` for list rendering
- Dynamic modal creation via `insertAdjacentHTML`
- Global state variables (no store)
- `API_BASE = window.location.origin + '/api'`

### Adding a New Tab

1. Add `<button class="topnav-dropdown-item" data-tab="tab-id">` to nav group
2. Add `<div class="tab-content" id="tab-id">` to content area
3. Add `'tab-id': 'group-name'` to `TAB_GROUP_MAP`
4. Add `if (tabName === 'tab-id') initTabId();` to `switchTab()`
5. Implement `initTabId()` with fetch + render pattern

---

## 8. Database & Migration Strategy

- **ORM:** Flask-SQLAlchemy
- **Local:** SQLite (`openclaw.db`)
- **Production:** Neon PostgreSQL with SSL, connection pooling (pool_size=5, max_overflow=10)
- **Table creation:** `db.create_all()` via `/api/admin/init-db` endpoint
- **Migrations:** Alembic in `/alembic/` directory
- **Current versions:** 002, 004, 006, 008, 010, 011

**Next migration:** `012_add_collaboration_tasks.py`

### Route Registration

30 modules registered in `server.py:69-118` via `register_X_routes(app)` or
`app.register_blueprint(bp)`. New collaboration routes follow the same pattern.

### Auth Pattern

Magic link email auth. `@require_auth` decorator checks `session.get('user_id')`.
All handlers use `user_id = session.get('user_id')` for workspace scoping.

---

## 9. Constraints for Collaboration Design

### Hard Constraints (from existing architecture)

| # | Constraint | Source |
|---|-----------|--------|
| C1 | workspace_id == user_id (v1) | `workspace.py:12-14` |
| C2 | All queries must filter by workspace_id | Universal pattern |
| C3 | Agent tier limits enforced at creation | `tier_enforcement.py` |
| C4 | Risk policies are per-agent or workspace-wide | `models.py:1091` |
| C5 | Cost events flow through `ObsEvent` with agent_id | `ingestion.py` |
| C6 | Governance audit is append-only | `governance_audit.py` |
| C7 | No Alembic auto-run -- manual migration needed | `server.py:842` |
| C8 | PUT is unreliable on Vercel -- prefer POST | CLAUDE.md |
| C9 | Vercel has 60s function timeout | `enforcement_worker.py` |
| C10 | Frontend is vanilla JS, no build step | CLAUDE.md |

### Design Principles for Collaboration

| # | Principle | Rationale |
|---|----------|-----------|
| P1 | Agents MUST NOT call each other directly | Maintains autonomy + auditability |
| P2 | Collaboration via persisted Tasks + Messages | Durable, observable, replayable |
| P3 | All costs remain agent-scoped | Per-agent risk envelopes stay valid |
| P4 | Hierarchy is optional and human-defined | No implicit authority |
| P5 | No breaking changes to existing tables | Incremental schema evolution |
| P6 | Workspace isolation on all new tables | Consistent with C2 |

---

## 10. Proposed Design Overview

### New Tables (4 core + 2 hierarchy)

```
tasks                    -- Inter-agent work items
  id                     UUID PK
  workspace_id           FK -> users.id
  created_by_agent_id    FK -> agents.id  nullable
  created_by_user_id     FK -> users.id   nullable
  assigned_to_agent_id   FK -> agents.id
  parent_task_id         FK -> tasks.id   nullable  (delegation chain)
  title                  String
  input                  JSON
  output                 JSON  nullable
  status                 Enum(queued,running,blocked,completed,failed,canceled)
  priority               Integer default 0
  due_at                 DateTime nullable
  created_at             DateTime
  updated_at             DateTime

task_events              -- Append-only lifecycle log
  id                     Integer PK
  task_id                FK -> tasks.id
  workspace_id           FK -> users.id
  agent_id               FK -> agents.id nullable
  event_type             String  (created,assigned,started,progress,
                                  tool_call,tool_result,completed,
                                  failed,escalated)
  payload                JSON
  created_at             DateTime

agent_messages           -- Collaboration messages
  id                     Integer PK
  workspace_id           FK -> users.id
  task_id                FK -> tasks.id  nullable
  thread_id              String(36)      nullable  (UUID for free threads)
  from_agent_id          FK -> agents.id nullable
  to_agent_id            FK -> agents.id nullable
  from_user_id           FK -> users.id  nullable
  role                   Enum(system,agent,user)
  content                Text
  created_at             DateTime

agent_roles              -- Optional hierarchy
  id                     Integer PK
  workspace_id           FK -> users.id
  agent_id               FK -> agents.id
  role                   Enum(supervisor,worker,specialist)
  can_assign_to_peers    Boolean default False
  can_escalate_to_supervisor Boolean default True
  UniqueConstraint(workspace_id, agent_id)

team_rules               -- Workspace-level team settings
  workspace_id           FK -> users.id  PK
  allow_peer_assignment  Boolean default False
  default_supervisor_agent_id  FK -> agents.id nullable
```

### New Route Modules

| File | Prefix | Phase |
|------|--------|-------|
| `routes/collaboration_tasks_routes.py` | `/api/tasks` | 1 |
| `routes/collaboration_messages_routes.py` | `/api/messages` | 2 |
| `routes/collaboration_team_routes.py` | `/api/team` | 3 |

### Governance Integration Points

- **Before task start:** Check assigned agent's risk envelope (is_active,
  budget headroom via `evaluate_policies`). If blocked, set task status to
  `blocked` and create `policy_change_request` if needed.
- **On task complete:** Log cost/token events via `emit_event()` with the
  assigned agent's `agent_id`.
- **Escalation:** When a worker escalates to supervisor, log to both
  `task_events` and `GovernanceAuditLog`.

---

## 11. File Touch Plan (by Phase)

### Phase 1 -- Task System

| Action | File |
|--------|------|
| CREATE | `alembic/versions/012_add_collaboration_tasks.py` |
| CREATE | `routes/collaboration_tasks_routes.py` |
| EDIT | `models.py` -- add Task, TaskEvent models |
| EDIT | `routes/__init__.py` -- export new registration function |
| EDIT | `server.py` -- import + register collaboration_tasks routes |
| CREATE | `tests/test_collaboration_tasks.py` |
| CREATE | `docs/collaboration/01-tasks.md` |

### Phase 2 -- Messaging

| Action | File |
|--------|------|
| CREATE | `alembic/versions/013_add_agent_messages.py` |
| CREATE | `routes/collaboration_messages_routes.py` |
| EDIT | `models.py` -- add AgentMessage model |
| EDIT | `routes/__init__.py` -- export new registration function |
| EDIT | `server.py` -- import + register collaboration_messages routes |
| CREATE | `tests/test_collaboration_messages.py` |
| CREATE | `docs/collaboration/02-messages.md` |

### Phase 3 -- Hierarchy

| Action | File |
|--------|------|
| CREATE | `alembic/versions/014_add_agent_roles.py` |
| CREATE | `routes/collaboration_team_routes.py` |
| EDIT | `models.py` -- add AgentRole, TeamRule models |
| EDIT | `routes/__init__.py` -- export new registration function |
| EDIT | `server.py` -- import + register collaboration_team routes |
| EDIT | `routes/collaboration_tasks_routes.py` -- enforce role-based assignment |
| CREATE | `tests/test_collaboration_team.py` |
| CREATE | `docs/collaboration/03-hierarchy.md` |

### Phase 4 -- Governance Integration

| Action | File |
|--------|------|
| CREATE | `core/collaboration/governance_hooks.py` |
| EDIT | `routes/collaboration_tasks_routes.py` -- call governance hooks on start/complete |
| EDIT | `core/governance/governance_audit.py` -- add collaboration event types |
| CREATE | `tests/test_collaboration_governance.py` |
| CREATE | `docs/collaboration/04-governance-hooks.md` |

### Phase 5 -- UI

| Action | File |
|--------|------|
| EDIT | `dashboard.html` -- add Tasks tab, Team tab in nav + content |
| EDIT | `static/js/dashboard-main.js` -- add TAB_GROUP_MAP entries, switchTab cases, init/render functions |

### Phase 6 -- End-to-End QA

| Action | File |
|--------|------|
| CREATE | `tests/test_collaboration_e2e.py` |
| CREATE | `docs/collaboration/99-acceptance.md` |

---

## 12. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| UUID primary keys on `tasks` differ from integer PKs elsewhere | Use String(36) column with `uuid.uuid4()` default; SQLite-compatible |
| Large task_events table growth | Index on (task_id, created_at); leverage existing retention cleanup patterns |
| Task status race conditions | All state transitions are POST endpoints with db-level status checks (optimistic locking via WHERE status=expected) |
| Vercel 60s timeout for task operations | Task endpoints only change state -- no synchronous execution of work |
| Governance check latency on task start | Cache tier lookups (already 60s TTL); evaluator is lightweight |
| Frontend complexity growth | New tabs follow exact existing pattern; no new JS framework needed |

---

## 13. Summary

The existing codebase provides strong extension points for collaboration:

1. **Agent model** is mature with cloning, risk policies, and observability already wired.
2. **Workspace isolation** is consistent (user_id scoping) with a clean abstraction layer.
3. **Governance/risk** systems provide ready-made hooks for task-level enforcement.
4. **Observability pipeline** (`emit_event`) can track collaboration events without new infrastructure.
5. **Frontend patterns** are well-established and straightforward to extend.
6. **Alembic migrations** provide safe, incremental schema evolution.

The collaboration framework adds 5 new tables and 3 new route modules without
modifying any existing table schemas. All integration is through new code paths
that call existing governance and observability APIs.
