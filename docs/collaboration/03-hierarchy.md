# Phase 3 — Human-Defined Team Hierarchy

Optional, human-defined agent roles and workspace-level team rules that
influence task assignment enforcement. Hierarchy is **never implicit** —
agents have no authority unless a human assigns roles and enables enforcement.

---

## Data model

### `agent_roles`

| Column                      | Type       | Notes                                      |
|-----------------------------|------------|--------------------------------------------|
| id                          | Integer PK | Auto-increment                             |
| workspace_id                | Integer FK | `users.id`                                 |
| agent_id                    | Integer FK | `agents.id`                                |
| role                        | String(20) | `supervisor` / `worker` / `specialist`     |
| can_assign_to_peers         | Boolean    | Default `false`                            |
| can_escalate_to_supervisor  | Boolean    | Default `true`                             |
| created_at                  | DateTime   | Auto-set                                   |
| updated_at                  | DateTime   | Auto-set                                   |

Unique constraint: `(workspace_id, agent_id)` — one role per agent.

### `team_rules`

| Column                        | Type       | Notes                                  |
|-------------------------------|------------|----------------------------------------|
| workspace_id                  | Integer PK | `users.id` — one row per workspace     |
| allow_peer_assignment         | Boolean    | Default `false`                        |
| require_supervisor_for_tasks  | Boolean    | Default `false`                        |
| default_supervisor_agent_id   | Integer FK | `agents.id`, nullable                  |
| created_at                    | DateTime   | Auto-set                               |
| updated_at                    | DateTime   | Auto-set                               |

---

## Roles

| Role         | Can assign to peers | Can escalate to supervisor | Can assign to workers |
|--------------|--------------------|-----------------------------|----------------------|
| supervisor   | Always             | N/A                         | Always               |
| worker       | If permitted       | If permitted (default yes)  | No                   |
| specialist   | If permitted       | If permitted (default yes)  | No                   |

Agents without an assigned role are treated like workers without `can_assign_to_peers`.

---

## Enforcement rules

Enforcement is **opt-in**. When `require_supervisor_for_tasks` is `false` (the default),
any agent can assign tasks to any other agent in the workspace.

When enabled:

1. **Supervisors** can assign tasks to anyone.
2. **Workers/specialists** can:
   - Always assign to themselves.
   - Escalate to supervisors (if `can_escalate_to_supervisor` is `true`).
   - Assign to peers only if both `allow_peer_assignment` (workspace) and `can_assign_to_peers` (agent) are `true`.
3. **Human-created tasks** (no `created_by_agent_id`) bypass all role checks.
4. **Reassignment** follows the same rules when `agent_id` is provided in the payload.

---

## API

### POST /api/team/roles — Assign or update an agent role

```bash
curl -X POST $BASE/api/team/roles \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_id": 1,
    "role": "supervisor",
    "can_assign_to_peers": true,
    "can_escalate_to_supervisor": true
  }'
```

Upserts — updates if role already exists for the agent.

**Response:** `201 Created`

---

### GET /api/team/roles — List all roles in workspace

```bash
curl "$BASE/api/team/roles"
```

**Response:** `200 OK`
```json
{
  "success": true,
  "roles": [
    {
      "id": 1,
      "workspace_id": 42,
      "agent_id": 1,
      "role": "supervisor",
      "can_assign_to_peers": true,
      "can_escalate_to_supervisor": true,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "count": 1
}
```

---

### GET /api/team/roles/\<agent_id\> — Get role for a specific agent

```bash
curl "$BASE/api/team/roles/1"
```

**Response:** `200 OK` or `404` if no role assigned.

---

### POST /api/team/roles/\<agent_id\>/delete — Remove role assignment

```bash
curl -X POST "$BASE/api/team/roles/1/delete"
```

**Response:** `200 OK` or `404`.

---

### GET /api/team/rules — Get workspace team rules

```bash
curl "$BASE/api/team/rules"
```

Returns defaults if no rules configured yet.

---

### POST /api/team/rules — Update workspace team rules

```bash
curl -X POST $BASE/api/team/rules \
  -H 'Content-Type: application/json' \
  -d '{
    "allow_peer_assignment": true,
    "require_supervisor_for_tasks": true,
    "default_supervisor_agent_id": 1
  }'
```

`default_supervisor_agent_id` must reference an agent with the `supervisor` role.

---

### GET /api/team/summary — Team overview

```bash
curl "$BASE/api/team/summary"
```

**Response:** `200 OK`
```json
{
  "success": true,
  "supervisors": [ ... ],
  "workers": [ ... ],
  "specialists": [ ... ],
  "unassigned_agents": [ {"id": 3, "name": "AgentC"} ],
  "rules": { ... }
}
```

---

## Task enforcement integration

The `_check_assignment_rules()` function in `collaboration_tasks_routes.py`
is called on:

- **`POST /api/tasks`** — validates creator-to-assignee relationship.
- **`POST /api/tasks/<id>/assign`** — validates requesting agent's permissions when `agent_id` is in the payload.

Returns `403 Forbidden` with a descriptive error when the assignment violates role rules.

---

## Files

| File | Purpose |
|------|---------|
| `models.py` | `AgentRole` and `TeamRule` models |
| `routes/collaboration_team_routes.py` | Role/rules CRUD + team summary |
| `routes/collaboration_tasks_routes.py` | `_check_assignment_rules()` enforcement |
| `alembic/versions/014_add_agent_roles.py` | Migration |
| `tests/test_collaboration_team.py` | 37 tests |

---

## Test summary

```
tests/test_collaboration_team.py — 37 passed

TestAgentRoles (13):
  - set role (supervisor, worker, specialist)
  - update existing role (upsert)
  - invalid role (400), missing agent_id (400), invalid agent (404)
  - get role, get role not found
  - list roles, delete role, delete not found
  - requires auth (401)

TestTeamRules (7):
  - get default rules
  - set rules, update rules
  - set default supervisor (valid), cannot set worker as default (400)
  - cannot set invalid agent (404)
  - requires auth (401)

TestRoleEnforcement (10):
  - no enforcement by default
  - supervisor can assign to anyone
  - worker cannot assign to peer without permission (403)
  - worker can assign to peer with permission
  - worker can escalate to supervisor
  - worker cannot escalate when disabled (403)
  - worker can assign to self
  - human-created task bypasses enforcement
  - enforcement on reassign (403)
  - human-initiated reassign bypasses enforcement

TestTeamSummary (3):
  - empty summary, summary with roles, requires auth

TestTeamIsolation (4):
  - cannot set role for other workspace agent (404)
  - cannot see other workspace roles
  - cannot get other workspace agent role (404)
  - cannot set other workspace agent as default supervisor (404)
```
