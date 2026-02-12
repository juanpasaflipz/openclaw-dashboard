# Phase 2 — Collaboration Messaging

Asynchronous message passing between agents, users, and the system.
Messages can be linked to a collaboration task (forming a task thread) or
grouped by a free-form `thread_id`.

---

## Data model

### `agent_messages`

| Column          | Type         | Notes                                    |
|-----------------|--------------|------------------------------------------|
| id              | Integer PK   | Auto-increment                           |
| workspace_id    | Integer FK   | `users.id` — workspace scoping           |
| task_id         | String(36)   | FK `collaboration_tasks.id`, nullable    |
| thread_id       | String(36)   | Free-form thread grouping, nullable      |
| from_agent_id   | Integer FK   | `agents.id`, nullable                    |
| to_agent_id     | Integer FK   | `agents.id`, nullable                    |
| from_user_id    | Integer FK   | `users.id`, set when `role='user'`       |
| role            | String(10)   | `system` / `agent` / `user`              |
| content         | Text         | Message body (required, non-empty)       |
| created_at      | DateTime     | Auto-set on insert                       |

Indexes: `(task_id, created_at)`, `(thread_id, created_at)`, `(workspace_id, created_at)`.

---

## API

### POST /api/messages — Send a message

```bash
# Agent-to-agent in a free thread
curl -X POST $BASE/api/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "content": "Hello from Agent A",
    "from_agent_id": 1,
    "to_agent_id": 2,
    "role": "agent",
    "thread_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  }'

# User instruction on a task
curl -X POST $BASE/api/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "content": "Please run the analysis",
    "to_agent_id": 1,
    "task_id": "task-uuid-here",
    "role": "user"
  }'

# System notification
curl -X POST $BASE/api/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "content": "Task deadline approaching",
    "task_id": "task-uuid-here",
    "role": "system"
  }'
```

**Request body:**

| Field           | Required | Description                                 |
|-----------------|----------|---------------------------------------------|
| content         | yes      | Message text (non-empty)                    |
| role            | yes      | `agent`, `user`, or `system`                |
| thread_id       | no       | Free-form UUID grouping                     |
| task_id         | no       | Link to a collaboration task                |
| from_agent_id   | no       | Sender agent (must belong to workspace)     |
| to_agent_id     | no       | Recipient agent (must belong to workspace)  |

**Validation:**
- `content` must be non-empty after trimming.
- `role` must be one of: `agent`, `user`, `system`.
- `task_id`, `from_agent_id`, `to_agent_id` are validated against the workspace.
- When `role=user`, `from_user_id` is auto-set to the authenticated user.

**Response:** `201 Created`
```json
{
  "success": true,
  "message": {
    "id": 1,
    "workspace_id": 42,
    "task_id": null,
    "thread_id": "aaaa-bbbb-...",
    "from_agent_id": 1,
    "to_agent_id": 2,
    "from_user_id": null,
    "role": "agent",
    "content": "Hello from Agent A",
    "created_at": "2026-02-12T14:30:00"
  }
}
```

**Error codes:** `400` (missing content, invalid role), `401` (unauthenticated), `404` (agent/task not in workspace).

---

### GET /api/messages — List messages

```bash
# By task
curl "$BASE/api/messages?task_id=task-uuid-here"

# By thread
curl "$BASE/api/messages?thread_id=aaaa-bbbb-..."

# With filters
curl "$BASE/api/messages?task_id=task-uuid&role=system"
curl "$BASE/api/messages?task_id=task-uuid&agent_id=2"
```

**Query params:**

| Param     | Required            | Description                          |
|-----------|---------------------|--------------------------------------|
| task_id   | one of task/thread  | Filter by collaboration task         |
| thread_id | one of task/thread  | Filter by free-form thread           |
| role      | no                  | Filter by role (agent/user/system)   |
| agent_id  | no                  | Filter by agent (from or to)         |

**Response:** `200 OK`
```json
{
  "success": true,
  "messages": [ ... ],
  "count": 3
}
```

Messages are ordered chronologically (oldest first), capped at 200 per request.

**Error codes:** `400` (neither task_id nor thread_id provided), `401` (unauthenticated).

---

## Workspace isolation

All messages are scoped by `workspace_id`:
- Cannot send `from_agent_id` or `to_agent_id` referencing agents outside the workspace (404).
- Cannot link to a `task_id` outside the workspace (404).
- Cannot read messages from another workspace (filtered out).

---

## Threading model

Two threading strategies coexist:

1. **Task threads** — set `task_id` to link messages to a collaboration task. All participants in that task share the thread.
2. **Free threads** — set `thread_id` (any UUID) for ad-hoc conversations not tied to a specific task.

Both can be used simultaneously on the same message.

---

## Files

| File | Purpose |
|------|---------|
| `models.py` | `AgentMessage` model with `VALID_ROLES` and `to_dict()` |
| `routes/collaboration_messages_routes.py` | POST + GET endpoints |
| `alembic/versions/013_add_agent_messages.py` | Migration |
| `tests/test_collaboration_messages.py` | 18 tests (send, list, isolation) |

---

## Test summary

```
tests/test_collaboration_messages.py  — 18 passed

TestSendMessage (8):
  - agent-to-agent, user message, system message, task-linked
  - missing content (400), invalid role (400), invalid task (404)
  - requires auth (401)

TestListMessages (6):
  - filter by task_id, thread_id
  - requires task or thread param (400)
  - filter by role, filter by agent_id
  - chronological ordering

TestMessageIsolation (4):
  - cannot see other workspace messages
  - cannot send to/from other workspace agents (404)
  - cannot link to other workspace task (404)
```
