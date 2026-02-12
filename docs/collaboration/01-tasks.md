# Phase 1 -- Collaboration Task System

> **Status:** Implemented
> **Migration:** `012_add_collaboration_tasks`
> **Route module:** `routes/collaboration_tasks_routes.py`

---

## Overview

Tasks are the core unit of inter-agent collaboration. An agent (or user)
creates a task and assigns it to another agent. The assigned agent starts,
completes, or fails the task. Every state change is logged as an append-only
`TaskEvent`.

**Key invariant:** Agents never call each other directly. All coordination
flows through persisted tasks.

---

## Schema

### collaboration_tasks

| Column | Type | Notes |
|--------|------|-------|
| id | String(36) UUID | Primary key |
| workspace_id | FK -> users.id | Workspace isolation |
| created_by_agent_id | FK -> agents.id | Nullable (set if agent-created) |
| created_by_user_id | FK -> users.id | Nullable (set if user-created) |
| assigned_to_agent_id | FK -> agents.id | Required |
| parent_task_id | FK -> collaboration_tasks.id | Nullable (delegation chain) |
| title | String(500) | |
| input | JSON | Task input payload |
| output | JSON | Nullable, set on complete/fail |
| status | String(20) | queued, running, blocked, completed, failed, canceled |
| priority | Integer | Higher = more important (default 0) |
| due_at | DateTime | Optional deadline |
| created_at | DateTime | |
| updated_at | DateTime | |

### task_events

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| task_id | FK -> collaboration_tasks.id | |
| workspace_id | FK -> users.id | |
| agent_id | FK -> agents.id | Nullable |
| event_type | String(30) | created, assigned, started, progress, tool_call, tool_result, completed, failed, escalated |
| payload | JSON | Event-specific data |
| created_at | DateTime | |

---

## Status Machine

```
queued ──────> running ──────> completed
  │              │
  │              ├──────> failed
  │              │
  │              └──────> blocked ──> running (resume)
  │                          │
  └──────> canceled          └──> canceled
```

Valid transitions:
- `queued` -> `running`, `canceled`
- `running` -> `completed`, `failed`, `blocked`
- `blocked` -> `running`, `canceled`
- `completed`, `failed`, `canceled` -> (terminal, no further transitions)

---

## API Endpoints

### POST /api/tasks

Create a new task.

**Request:**
```json
{
  "title": "Summarize the quarterly report",
  "assigned_to_agent_id": 2,
  "created_by_agent_id": 1,
  "parent_task_id": "uuid-of-parent",
  "input": {"document_url": "https://..."},
  "priority": 5,
  "due_at": "2026-02-15T12:00:00Z"
}
```

Required: `title`, `assigned_to_agent_id`

**Response (201):**
```json
{
  "success": true,
  "task": { ... }
}
```

**curl:**
```bash
curl -X POST http://localhost:5000/api/tasks \
  -H "Content-Type: application/json" \
  -b "session=..." \
  -d '{"title":"Summarize report","assigned_to_agent_id":2}'
```

---

### GET /api/tasks

List tasks with optional filters.

**Query params:**
- `status` -- filter by status (e.g., `?status=queued`)
- `agent_id` -- tasks where agent is creator or assignee
- `assigned_to` -- tasks assigned to specific agent
- `parent_task_id` -- subtasks of a given parent

**curl:**
```bash
curl http://localhost:5000/api/tasks?status=queued -b "session=..."
```

---

### GET /api/tasks/:id

Get a single task including its event timeline.

**curl:**
```bash
curl http://localhost:5000/api/tasks/abc123-uuid -b "session=..."
```

---

### POST /api/tasks/:id/start

Transition task from `queued` or `blocked` to `running`.

**curl:**
```bash
curl -X POST http://localhost:5000/api/tasks/abc123/start \
  -H "Content-Type: application/json" \
  -b "session=..."
```

---

### POST /api/tasks/:id/complete

Transition task from `running` to `completed`. Optionally attach output.

**Request:**
```json
{
  "output": {"summary": "Report is 15 pages, key finding: ..."},
  "agent_id": 2
}
```

**curl:**
```bash
curl -X POST http://localhost:5000/api/tasks/abc123/complete \
  -H "Content-Type: application/json" \
  -b "session=..." \
  -d '{"output":{"summary":"Done"}}'
```

---

### POST /api/tasks/:id/fail

Transition task from `running` to `failed`.

**Request:**
```json
{
  "output": {"error": "Model timeout after 30s"},
  "reason": "LLM provider unreachable"
}
```

---

### POST /api/tasks/:id/cancel

Cancel a `queued` or `blocked` task.

---

### POST /api/tasks/:id/assign

Reassign a task to a different agent. If the task was `running`, it resets
to `queued`.

**Request:**
```json
{
  "assigned_to_agent_id": 3
}
```

**curl:**
```bash
curl -X POST http://localhost:5000/api/tasks/abc123/assign \
  -H "Content-Type: application/json" \
  -b "session=..." \
  -d '{"assigned_to_agent_id":3}'
```

---

## Workspace Isolation

All endpoints enforce workspace isolation via `workspace_id = session.user_id`.
A user cannot see, modify, or assign tasks belonging to another workspace.
Cross-workspace agent assignment is rejected with 404.

---

## Delegation Chains

Tasks can form parent-child hierarchies via `parent_task_id`. This models
the delegation pattern:

1. Supervisor agent receives a complex task
2. Supervisor creates subtasks assigned to worker agents
3. Workers complete subtasks independently
4. Supervisor aggregates results

Query subtasks: `GET /api/tasks?parent_task_id=<parent-uuid>`

---

## Tests

```bash
pytest tests/test_collaboration_tasks.py -v
```

Test classes:
- `TestTaskCreation` -- create by user, by agent, validation, auth
- `TestTaskRetrieval` -- list, filter, get with events
- `TestTaskTransitions` -- start, complete, fail, cancel, invalid transitions
- `TestDelegationChain` -- parent/child tasks, subtask filtering
- `TestTaskReassignment` -- reassign, reset running->queued, completed guard
- `TestWorkspaceIsolation` -- cross-workspace visibility, assignment, transitions
