# 99 — Acceptance Checklist

## Data Layer

- [x] `CollaborationTask` model with UUID PK, status enum, delegation chain
- [x] `TaskEvent` model — append-only lifecycle log with event types
- [x] `AgentMessage` model — task-linked and free threads
- [x] `AgentRole` model — supervisor/worker/specialist roles with unique constraint
- [x] `TeamRule` model — workspace-level team settings (PK = workspace_id)
- [x] Alembic migration `012_add_collaboration_tasks.py`
- [x] Alembic migration `013_add_agent_messages.py`
- [x] Alembic migration `014_add_agent_roles.py`
- [x] All tables scoped by `workspace_id` FK to `users.id`
- [x] Indexes on task status, workspace, assigned agent, and message threads

## Task System (Phase 1)

- [x] `POST /api/tasks` — create task (user or agent)
- [x] `GET /api/tasks` — list tasks with filters (status, agent, parent_task_id)
- [x] `GET /api/tasks/<id>` — get task with event trail
- [x] `POST /api/tasks/<id>/start` — queued/blocked → running
- [x] `POST /api/tasks/<id>/complete` — running → completed
- [x] `POST /api/tasks/<id>/fail` — running → failed
- [x] `POST /api/tasks/<id>/cancel` — queued/blocked → canceled
- [x] `POST /api/tasks/<id>/assign` — reassign to different agent
- [x] Status machine enforces valid transitions only
- [x] Invalid transitions return 409
- [x] Reassignment of running task resets to queued
- [x] Reassignment of completed/failed/canceled task returns 409
- [x] Parent task delegation chains via `parent_task_id`
- [x] All transitions emit `TaskEvent` entries

## Messaging System (Phase 2)

- [x] `POST /api/messages` — send message (agent, user, or system)
- [x] `GET /api/messages` — list messages by task_id or thread_id
- [x] Task-linked messages (via `task_id`)
- [x] Free thread messages (via `thread_id`)
- [x] Role validation (agent, user, system only)
- [x] Filters: role, agent_id
- [x] Chronological ordering
- [x] Requires task_id or thread_id for listing

## Team Hierarchy (Phase 3)

- [x] `POST /api/team/roles` — assign role to agent
- [x] `GET /api/team/roles` — list all roles
- [x] `GET /api/team/roles/<agent_id>` — get agent role
- [x] `POST /api/team/roles/<id>/delete` — remove role
- [x] `GET /api/team/rules` — get team rules
- [x] `POST /api/team/rules` — save team rules
- [x] `GET /api/team/summary` — grouped role overview + unassigned agents
- [x] Supervisors can assign to anyone
- [x] Workers can escalate to supervisor (when `can_escalate_to_supervisor`)
- [x] Workers need `can_assign_to_peers` + workspace `allow_peer_assignment`
- [x] Workers can always assign to self
- [x] Human-created tasks bypass role checks
- [x] Default supervisor must have supervisor role
- [x] Role enforcement only when `require_supervisor_for_tasks` is enabled

## Governance & Risk Integration (Phase 4)

- [x] `pre_task_start()` — blocking risk check (agent paused, pending risk events)
- [x] `on_task_started()` — emits `action_started` observability event
- [x] `on_task_completed()` — emits `action_finished` observability event
- [x] `on_task_failed()` — emits `error` observability event
- [x] `on_task_blocked_by_risk()` — logs `task_blocked` governance audit
- [x] `on_task_escalated()` — logs `task_escalated` governance audit
- [x] `on_task_reassigned()` — logs `task_reassigned` governance audit
- [x] Blocked task returns 409 with `blocked: true` and reason
- [x] Blocked task emits `TaskEvent(blocked)` with reason payload
- [x] Blocked tasks can resume after risk resolution (blocked → running)
- [x] All post-transition hooks are best-effort (never raise)
- [x] Observability failure does not block task operations
- [x] Governance audit failure does not block reassignment
- [x] All events include `payload.source = 'collaboration'`
- [x] Governance events queryable via existing `/api/governance/audit`

## UI (Phase 5)

- [x] Tasks tab added to Workbench dropdown (`collab-tasks`)
- [x] Team tab added to Workbench dropdown (`collab-team`)
- [x] `TAB_GROUP_MAP` entries for both tabs
- [x] `switchTab()` calls init functions for both tabs
- [x] Tasks tab: status filter, agent filter, status stats
- [x] Tasks tab: task card list with badges and agent names
- [x] Tasks tab: task detail modal with events and action buttons
- [x] Tasks tab: create task modal with agent/priority selection
- [x] Team tab: team rules card with auto-save checkboxes
- [x] Team tab: default supervisor dropdown (supervisor role only)
- [x] Team tab: assign role controls (agent + role + button)
- [x] Team tab: grouped team summary (supervisor/worker/specialist/unassigned)
- [x] No new CSS classes — reuses existing `.card`, `.btn-*` patterns
- [x] `escapeHtml()` for safe rendering of user content

## Workspace Isolation

- [x] Tasks invisible across workspaces (list and detail)
- [x] Cannot start/complete/fail/cancel foreign tasks
- [x] Cannot assign to foreign workspace agents
- [x] Messages invisible across workspaces
- [x] Cannot send to/from foreign workspace agents
- [x] Cannot link messages to foreign workspace tasks
- [x] Team roles scoped to workspace
- [x] Cannot assign roles to foreign agents
- [x] Cannot set foreign agent as default supervisor

## Design Principles

- [x] P1: Agents never call each other directly — all via persisted Tasks/Messages
- [x] P2: All collaboration is durable and observable
- [x] P3: Costs remain agent-scoped via observability pipeline
- [x] P4: Hierarchy is optional and human-defined
- [x] P5: No breaking changes to existing tables
- [x] P6: Workspace isolation on all new tables

## Tests

### Phase 1 — Task System (30 tests)
- [x] Task creation: by user, by agent, missing title, missing agent, invalid agent, auth
- [x] Task retrieval: list, filter by status, filter by agent, detail with events, not found
- [x] Transitions: start, complete, fail, cancel, invalid transitions, event emission
- [x] Delegation: parent_task_id, filter subtasks, invalid parent
- [x] Reassignment: reassign, running resets, completed fails, event emitted
- [x] Workspace isolation: invisible tasks, inaccessible detail, cross-workspace agent, cross-workspace transition

### Phase 2 — Messaging (18 tests)
- [x] Send: agent, user, system, task-linked, missing content, invalid role, invalid task, auth
- [x] List: by task, by thread, requires filter, filter by role, filter by agent, chronological order
- [x] Isolation: invisible messages, cross-workspace to/from, cross-workspace task link

### Phase 3 — Team Hierarchy (37 tests)
- [x] Roles: set (3 types), update, invalid, missing, get, list, delete, auth
- [x] Rules: default, set, update, supervisor, invalid supervisor, auth
- [x] Enforcement: no default, supervisor can assign, worker blocked, peer permission, escalation, self-assign, human bypass, reassign enforcement
- [x] Summary: empty, with roles, auth
- [x] Isolation: cross-workspace role, visibility, get, default supervisor

### Phase 4 — Governance (17 tests)
- [x] Risk check: healthy start, paused blocked, pending risk blocked, blocked event, audit log, recovery
- [x] Observability: started, completed, failed events
- [x] Audit trail: escalation, reassignment, both together, no false escalation, API queryable
- [x] Resilience: complete despite obs failure, start despite obs failure, reassign despite audit failure

### Phase 6 — End-to-End (20 tests)
- [x] Full lifecycle: create → start → message → complete with observability
- [x] Delegation chain: supervisor → worker → specialist → escalation back
- [x] Risk blocking: block → resolve → resume → complete
- [x] Hierarchy enforcement: peer denied, escalation allowed, supervisor all, human bypass, summary
- [x] Messaging: task/thread isolation, multi-agent conversation, user participation
- [x] Workspace isolation: tasks, messages, team config
- [x] Failure path: full event + observability trail
- [x] Cancel and recreate pattern
- [x] Concurrent tasks across agents, filtering
- [x] Team configuration changes affecting enforcement and audit

## Documentation

- [x] `docs/collaboration/00-architecture-review.md` — Phase 0 audit
- [x] `docs/collaboration/01-tasks.md` — Task system API
- [x] `docs/collaboration/02-messages.md` — Messaging system API
- [x] `docs/collaboration/03-hierarchy.md` — Team hierarchy API
- [x] `docs/collaboration/04-governance-hooks.md` — Governance integration
- [x] `docs/collaboration/05-ui.md` — Dashboard UI
- [x] `docs/collaboration/99-acceptance.md` — This checklist

## Files Created (16)

| File | Purpose |
|------|---------|
| `routes/collaboration_tasks_routes.py` | Task API endpoints |
| `routes/collaboration_messages_routes.py` | Messaging API endpoints |
| `routes/collaboration_team_routes.py` | Team hierarchy API endpoints |
| `core/collaboration/__init__.py` | Package init |
| `core/collaboration/governance_hooks.py` | 7 governance hook functions |
| `alembic/versions/012_add_collaboration_tasks.py` | Migration: tasks + task_events |
| `alembic/versions/013_add_agent_messages.py` | Migration: agent_messages |
| `alembic/versions/014_add_agent_roles.py` | Migration: agent_roles + team_rules |
| `tests/test_collaboration_tasks.py` | 30 tests |
| `tests/test_collaboration_messages.py` | 18 tests |
| `tests/test_collaboration_team.py` | 37 tests |
| `tests/test_collaboration_governance.py` | 17 tests |
| `tests/test_collaboration_e2e.py` | 20 tests |
| `docs/collaboration/00-architecture-review.md` | Architecture audit |
| `docs/collaboration/01-tasks.md` | Task system docs |
| `docs/collaboration/02-messages.md` | Messaging docs |
| `docs/collaboration/03-hierarchy.md` | Hierarchy docs |
| `docs/collaboration/04-governance-hooks.md` | Governance docs |
| `docs/collaboration/05-ui.md` | UI docs |
| `docs/collaboration/99-acceptance.md` | This checklist |

## Files Modified (5)

| File | Change |
|------|--------|
| `models.py` | Added CollaborationTask, TaskEvent, AgentMessage, AgentRole, TeamRule |
| `routes/__init__.py` | Added 3 route registration imports |
| `server.py` | Registered 3 collaboration route modules + model imports |
| `dashboard.html` | Added Tasks + Team nav items and tab content divs |
| `static/js/dashboard-main.js` | Added TAB_GROUP_MAP entries, switchTab cases, ~400 lines of task/team JS |
| `core/governance/governance_audit.py` | Updated docstring with new event types |

## Test Totals

```
Phase 1 (tasks):       30 passed
Phase 2 (messages):    18 passed
Phase 3 (hierarchy):   37 passed
Phase 4 (governance):  17 passed
Phase 6 (e2e):         20 passed
─────────────────────────────────
Total:                122 passed
```
