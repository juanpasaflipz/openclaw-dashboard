# Control Plane API v1

> Phase 0 — specification only. No code changes.

Base path: `/api/v1`
Auth: `Authorization: Bearer <workspace_api_key>` (see integration-contract.md)
Content-Type: `application/json`
All list endpoints support `?page=1&per_page=50` (max 100).
All timestamps are ISO 8601 UTC.

---

## 1. Agents

Manage agent registration and lifecycle within a workspace.

### 1.1 List agents

```
GET /api/v1/agents
```

Query params:
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `is_active` | bool | — | Filter by active status |
| `agent_type` | string | — | Filter by type (`direct`, `external`, `nautilus`) |

Response `200`:
```json
{
  "agents": [
    {
      "id": 42,
      "name": "Research Bot",
      "description": "Performs web research",
      "agent_type": "external",
      "is_active": true,
      "role": "worker",
      "created_at": "2026-01-15T10:30:00Z",
      "updated_at": "2026-01-20T14:00:00Z"
    }
  ],
  "pagination": { "page": 1, "per_page": 50, "total": 3 }
}
```

**Classification: CORE REQUIRED**

---

### 1.2 Get agent

```
GET /api/v1/agents/{agent_id}
```

Response `200`: Single agent object (same shape as list item, plus `llm_config`, `identity_config`, `last_connected_at`, `last_error`).

**Classification: CORE REQUIRED**

---

### 1.3 Create agent

```
POST /api/v1/agents
```

Body:
```json
{
  "name": "Research Bot",
  "description": "Performs web research",
  "agent_type": "external",
  "personality": "Thorough and methodical researcher",
  "llm_config": { "provider": "openai", "model": "gpt-4o" },
  "identity_config": { "tone": "professional" }
}
```

Required fields: `name`.
Response `201`: Created agent object.

**Classification: CORE REQUIRED**

---

### 1.4 Update agent

```
POST /api/v1/agents/{agent_id}
```

Body: Partial object — only supplied fields are updated. Cannot change `agent_type` after creation.

Response `200`: Updated agent object.

> Note: POST instead of PUT/PATCH for Vercel compatibility.

**Classification: CORE REQUIRED**

---

### 1.5 Delete agent

```
POST /api/v1/agents/{agent_id}/delete
```

Soft-deletes (sets `is_active = false`). Active tasks assigned to this agent are canceled.

Response `200`:
```json
{ "deleted": true, "agent_id": 42 }
```

**Classification: CORE REQUIRED**

---

## 2. Tasks

Inter-agent task coordination. Tasks follow the state machine: `queued -> running -> completed|failed`, with `blocked` and `canceled` as terminal/interrupt states.

### 2.1 Create task

```
POST /api/v1/tasks
```

Body:
```json
{
  "title": "Summarize Q4 earnings report",
  "assigned_to_agent_id": 42,
  "created_by_agent_id": 10,
  "parent_task_id": null,
  "input": { "document_url": "https://...", "format": "markdown" },
  "priority": 1,
  "due_at": "2026-02-15T00:00:00Z",
  "idempotency_key": "task-abc-123"
}
```

Required fields: `title`, `assigned_to_agent_id`.

Response `201`:
```json
{
  "task": {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "title": "Summarize Q4 earnings report",
    "status": "queued",
    "assigned_to_agent_id": 42,
    "created_by_agent_id": 10,
    "parent_task_id": null,
    "input": { "document_url": "https://...", "format": "markdown" },
    "output": null,
    "priority": 1,
    "due_at": "2026-02-15T00:00:00Z",
    "created_at": "2026-02-14T12:00:00Z",
    "updated_at": "2026-02-14T12:00:00Z"
  }
}
```

**Classification: CORE REQUIRED**

---

### 2.2 List tasks

```
GET /api/v1/tasks
```

Query params:
| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter: `queued`, `running`, `blocked`, `completed`, `failed`, `canceled` |
| `assigned_to_agent_id` | int | Tasks assigned to this agent |
| `created_by_agent_id` | int | Tasks created by this agent |
| `parent_task_id` | string | Subtasks of a parent |

Response `200`: `{ "tasks": [...], "pagination": {...} }`

**Classification: CORE REQUIRED**

---

### 2.3 Get task

```
GET /api/v1/tasks/{task_id}
```

Response includes the task object plus `events` array (last 100 TaskEvent records, most recent first).

**Classification: CORE REQUIRED**

---

### 2.4 Task transitions

All transitions are POST. The backend enforces the state machine and runs risk checks on `start`.

```
POST /api/v1/tasks/{task_id}/start
POST /api/v1/tasks/{task_id}/complete
POST /api/v1/tasks/{task_id}/fail
POST /api/v1/tasks/{task_id}/cancel
POST /api/v1/tasks/{task_id}/assign
```

**Start** — no body required. Returns `200` with updated task or `409` if risk check blocks.

**Complete** body:
```json
{
  "output": { "summary": "..." }
}
```

**Fail** body:
```json
{
  "error_message": "Upstream API returned 503"
}
```

**Cancel** — no body required.

**Assign** body:
```json
{
  "assigned_to_agent_id": 55
}
```

All return `200` with updated task, `409 Conflict` if transition is invalid, or `403` if role enforcement blocks.

**Classification: CORE REQUIRED**

---

### 2.5 Task events (read-only)

```
GET /api/v1/tasks/{task_id}/events
```

Query params: `event_type`, `agent_id`, `page`, `per_page`.

Returns append-only event log:
```json
{
  "events": [
    {
      "id": 1001,
      "task_id": "f47ac10b-...",
      "agent_id": 42,
      "event_type": "started",
      "payload": {},
      "created_at": "2026-02-14T12:01:00Z"
    }
  ],
  "pagination": { "page": 1, "per_page": 50, "total": 5 }
}
```

Valid event types: `created`, `assigned`, `started`, `progress`, `tool_call`, `tool_result`, `completed`, `failed`, `escalated`, `blocked`, `canceled`.

**Classification: CORE REQUIRED**

---

## 3. Messages

Agent-to-agent and user-to-agent messaging, optionally linked to tasks.

### 3.1 Send message

```
POST /api/v1/messages
```

Body:
```json
{
  "from_agent_id": 10,
  "to_agent_id": 42,
  "task_id": "f47ac10b-...",
  "thread_id": null,
  "content": "Please include revenue breakdown by region.",
  "idempotency_key": "msg-xyz-456"
}
```

Required fields: `content`, and at least one of `from_agent_id` or `from_user` (implied by API key).

Response `201`:
```json
{
  "message": {
    "id": 5001,
    "task_id": "f47ac10b-...",
    "thread_id": null,
    "from_agent_id": 10,
    "to_agent_id": 42,
    "role": "agent",
    "content": "Please include revenue breakdown by region.",
    "created_at": "2026-02-14T12:05:00Z"
  }
}
```

**Classification: CORE REQUIRED**

---

### 3.2 List messages

```
GET /api/v1/messages
```

Query params (at least one required):
| Param | Type | Description |
|-------|------|-------------|
| `task_id` | string | Messages for a specific task |
| `thread_id` | string | Messages in a thread |
| `agent_id` | int | Messages sent by or to this agent |

Response `200`: `{ "messages": [...], "pagination": {...} }`

**Classification: CORE REQUIRED**

---

## 4. Governance

Policy change requests, approvals, delegation grants, and audit trail.

### 4.1 Submit policy change request

```
POST /api/v1/governance/requests
```

Body:
```json
{
  "agent_id": 42,
  "policy_id": 7,
  "requested_changes": {
    "threshold_value": "150.00",
    "action_type": "alert_only"
  },
  "reason": "Current daily spend cap of $50 is too low for batch processing runs."
}
```

Required fields: `agent_id`, `requested_changes`, `reason`.

Response `201`:
```json
{
  "request": {
    "id": 301,
    "agent_id": 42,
    "policy_id": 7,
    "status": "pending",
    "requested_changes": { ... },
    "reason": "...",
    "requested_at": "2026-02-14T12:10:00Z",
    "expires_at": "2026-02-21T12:10:00Z"
  }
}
```

**Classification: CORE REQUIRED**

---

### 4.2 List requests

```
GET /api/v1/governance/requests
```

Query params: `status` (`pending`, `approved`, `denied`, `expired`, `applied`), `agent_id`.

Response `200`: `{ "requests": [...], "pagination": {...} }`

**Classification: CORE REQUIRED**

---

### 4.3 Approve request

```
POST /api/v1/governance/requests/{request_id}/approve
```

Body:
```json
{
  "mode": "one_time",
  "delegation_duration_minutes": null
}
```

`mode` is `one_time` (apply immediately) or `delegate` (create a time-bound DelegationGrant).

If `mode == "delegate"`, required fields: `delegation_duration_minutes`, optional: `max_spend_delta`, `max_model_upgrade`.

Response `200`:
```json
{
  "request": { "id": 301, "status": "approved", ... },
  "delegation_grant": null
}
```

**Classification: CORE REQUIRED**

---

### 4.4 Deny request

```
POST /api/v1/governance/requests/{request_id}/deny
```

Body (optional):
```json
{
  "reason": "Budget freeze in effect."
}
```

Response `200`: Updated request with `status: "denied"`.

**Classification: CORE REQUIRED**

---

### 4.5 Apply delegation

```
POST /api/v1/governance/delegations/apply
```

Used by an agent to exercise an active delegation grant.

Body:
```json
{
  "grant_id": 15,
  "agent_id": 42,
  "changes": {
    "threshold_value": "120.00"
  }
}
```

Returns `200` with the updated policy and a new GovernanceAuditLog entry, or `403` if the grant is expired/revoked/exceeded.

**Classification: CORE REQUIRED**

---

### 4.6 List active delegations

```
GET /api/v1/governance/delegations
```

Query params: `agent_id`, `active` (bool, default `true`).

Response `200`:
```json
{
  "delegations": [
    {
      "id": 15,
      "agent_id": 42,
      "allowed_changes": { ... },
      "max_spend_delta": "100.00",
      "valid_from": "2026-02-14T12:10:00Z",
      "valid_to": "2026-02-15T12:10:00Z",
      "active": true
    }
  ]
}
```

**Classification: CORE REQUIRED**

---

### 4.7 Revoke delegation

```
POST /api/v1/governance/delegations/{grant_id}/revoke
```

Response `200`: Updated grant with `active: false`, `revoked_at` set.

**Classification: CORE REQUIRED**

---

### 4.8 Rollback policy change

```
POST /api/v1/governance/rollback/{audit_id}
```

Reverts a policy to the `before_snapshot` stored in the referenced GovernanceAuditLog entry.

Response `200`: Updated policy plus new audit log entry recording the rollback.

**Classification: OPTIONAL** (power-user feature)

---

### 4.9 Query audit trail

```
GET /api/v1/governance/audit
```

Query params: `agent_id`, `event_type`, `from` (ISO date), `to` (ISO date).

Response `200`:
```json
{
  "entries": [
    {
      "id": 901,
      "agent_id": 42,
      "actor_id": 1,
      "event_type": "request_approved",
      "details": { ... },
      "created_at": "2026-02-14T12:11:00Z"
    }
  ],
  "pagination": { ... }
}
```

**Classification: CORE REQUIRED**

---

## 5. Observability

Event ingestion (write path) and metric/run queries (read path). Authenticated via the same workspace API key, or via a dedicated ObsApiKey if provisioned.

### 5.1 Ingest event

```
POST /api/v1/observability/events
```

Body:
```json
{
  "event_type": "llm_call",
  "status": "success",
  "agent_id": 42,
  "run_id": "a1b2c3d4-...",
  "model": "gpt-4o",
  "tokens_in": 1500,
  "tokens_out": 800,
  "cost_usd": 0.045,
  "latency_ms": 2300,
  "payload": { "prompt_tokens": 1500, "completion_tokens": 800 },
  "idempotency_key": "evt-run123-step4"
}
```

Required fields: `event_type`.
Valid event types: `run_started`, `run_finished`, `action_started`, `action_finished`, `tool_call`, `tool_result`, `llm_call`, `error`, `metric`, `heartbeat`.
Valid status values: `success`, `error`, `info`.

`idempotency_key` maps to `dedupe_key`. Duplicate keys return `200` with the existing event (no re-insert).

Response `201`:
```json
{
  "event": {
    "uid": "e5f6a7b8-...",
    "event_type": "llm_call",
    "status": "success",
    "created_at": "2026-02-14T12:20:00Z"
  }
}
```

**Classification: CORE REQUIRED**

---

### 5.2 Ingest event batch

```
POST /api/v1/observability/events/batch
```

Body:
```json
{
  "events": [
    { "event_type": "llm_call", "agent_id": 42, ... },
    { "event_type": "tool_call", "agent_id": 42, ... }
  ]
}
```

Max batch size governed by workspace tier (`max_batch_size`, default 100).

Response `200`:
```json
{
  "accepted": 2,
  "rejected": []
}
```

**Classification: CORE REQUIRED**

---

### 5.3 Start run

```
POST /api/v1/observability/runs
```

Body:
```json
{
  "agent_id": 42,
  "model": "gpt-4o",
  "metadata": { "task_id": "f47ac10b-..." }
}
```

Response `201`:
```json
{
  "run": {
    "run_id": "a1b2c3d4-...",
    "agent_id": 42,
    "status": "running",
    "started_at": "2026-02-14T12:30:00Z"
  }
}
```

**Classification: CORE REQUIRED**

---

### 5.4 Finish run

```
POST /api/v1/observability/runs/{run_id}/finish
```

Body:
```json
{
  "status": "success",
  "tokens_in": 4500,
  "tokens_out": 2100,
  "cost_usd": 0.13,
  "latency_ms": 8500,
  "tool_calls_count": 3,
  "error_message": null
}
```

Response `200`: Updated run object with `finished_at` set.

**Classification: CORE REQUIRED**

---

### 5.5 List runs

```
GET /api/v1/observability/runs
```

Query params: `agent_id`, `status` (`running`, `success`, `error`), `from`, `to`, `page`, `per_page`.

Response `200`: `{ "runs": [...], "pagination": {...} }`

**Classification: CORE REQUIRED**

---

### 5.6 Get run

```
GET /api/v1/observability/runs/{run_id}
```

Response includes run object plus associated events.

**Classification: CORE REQUIRED**

---

### 5.7 Query events

```
GET /api/v1/observability/events
```

Query params: `agent_id`, `event_type`, `run_id`, `status`, `from`, `to`, `page`, `per_page`.

Date range is clamped to workspace retention window.

Response `200`: `{ "events": [...], "pagination": {...} }`

**Classification: CORE REQUIRED**

---

### 5.8 Query daily metrics

```
GET /api/v1/observability/metrics/daily
```

Query params: `agent_id` (required), `from` (ISO date), `to` (ISO date).

Response `200`:
```json
{
  "metrics": [
    {
      "date": "2026-02-13",
      "agent_id": 42,
      "total_events": 150,
      "total_tokens_in": 45000,
      "total_tokens_out": 22000,
      "total_cost_usd": 1.35,
      "avg_latency_ms": 2100,
      "error_count": 2,
      "error_rate": 0.013
    }
  ]
}
```

**Classification: OPTIONAL**

---

### 5.9 Get agent health score

```
GET /api/v1/observability/health/{agent_id}
```

Query params: `date` (ISO date, default today).

Response `200`:
```json
{
  "agent_id": 42,
  "date": "2026-02-14",
  "overall_score": 87,
  "breakdown": {
    "error_rate_score": 95,
    "latency_score": 80,
    "cost_efficiency_score": 90,
    "activity_score": 85
  }
}
```

**Classification: OPTIONAL**

---

### 5.10 Alert rules CRUD

```
GET    /api/v1/observability/alerts/rules
POST   /api/v1/observability/alerts/rules
POST   /api/v1/observability/alerts/rules/{rule_id}
POST   /api/v1/observability/alerts/rules/{rule_id}/delete
```

Create/update body:
```json
{
  "name": "High daily cost",
  "agent_id": 42,
  "rule_type": "cost_per_day",
  "threshold": "10.00",
  "window_minutes": 1440,
  "cooldown_minutes": 360,
  "is_enabled": true
}
```

Valid rule types: `cost_per_day`, `error_rate`, `no_heartbeat`.

**Classification: OPTIONAL**

---

### 5.11 List fired alerts

```
GET /api/v1/observability/alerts/events
```

Query params: `agent_id`, `rule_type`, `from`, `to`, `acknowledged` (bool).

Response `200`: `{ "alerts": [...], "pagination": {...} }`

**Classification: OPTIONAL**

---

## 6. Webhooks (Events Out)

Register HTTP endpoints to receive platform events. The platform pushes events to registered URLs.

### 6.1 Register webhook

```
POST /api/v1/webhooks
```

Body:
```json
{
  "url": "https://my-service.example.com/hooks/greenmonkey",
  "events": ["task.completed", "task.failed", "governance.request_created", "obs.alert_fired"],
  "secret": "whsec_mysharedsecret123"
}
```

Required fields: `url`, `events`.

If `secret` is provided, every delivery includes `X-Signature-256` header (HMAC-SHA256 of the raw body using the secret).

Response `201`:
```json
{
  "webhook": {
    "id": 50,
    "url": "https://my-service.example.com/hooks/greenmonkey",
    "events": ["task.completed", "task.failed", "governance.request_created", "obs.alert_fired"],
    "is_active": true,
    "created_at": "2026-02-14T13:00:00Z"
  }
}
```

**Classification: OPTIONAL**

---

### 6.2 List webhooks

```
GET /api/v1/webhooks
```

Response `200`: `{ "webhooks": [...] }`

**Classification: OPTIONAL**

---

### 6.3 Update webhook

```
POST /api/v1/webhooks/{webhook_id}
```

Body: Partial — update `url`, `events`, `secret`, `is_active`.

**Classification: OPTIONAL**

---

### 6.4 Delete webhook

```
POST /api/v1/webhooks/{webhook_id}/delete
```

Response `200`: `{ "deleted": true }`

**Classification: OPTIONAL**

---

### 6.5 Available event types

| Event | Trigger | Payload includes |
|-------|---------|------------------|
| `agent.created` | Agent registered | agent object |
| `agent.updated` | Agent config changed | agent object (after) |
| `agent.deleted` | Agent soft-deleted | `{ agent_id }` |
| `task.created` | Task queued | task object |
| `task.started` | Task moved to running | task object |
| `task.completed` | Task finished successfully | task object with output |
| `task.failed` | Task errored | task object with error |
| `task.blocked` | Risk check blocked task | task object, risk event |
| `task.canceled` | Task canceled | task object |
| `message.created` | New agent/user message | message object |
| `governance.request_created` | PCR submitted | request object |
| `governance.request_approved` | PCR approved | request object, grant (if delegated) |
| `governance.request_denied` | PCR denied | request object |
| `governance.delegation_applied` | Agent exercised grant | audit entry |
| `governance.delegation_revoked` | Grant revoked | grant object |
| `obs.alert_fired` | Alert threshold breached | alert event object |
| `obs.run_finished` | Run completed/failed | run object |

### 6.6 Delivery format

Every webhook delivery is a POST with:

```
POST {registered_url}
Content-Type: application/json
X-Webhook-ID: dlv_a1b2c3d4
X-Webhook-Event: task.completed
X-Webhook-Timestamp: 1739538000
X-Signature-256: sha256=<hmac_hex>   (only if secret configured)
```

Body:
```json
{
  "id": "dlv_a1b2c3d4",
  "event": "task.completed",
  "workspace_id": 1,
  "timestamp": "2026-02-14T13:00:00Z",
  "data": {
    "task": { ... }
  }
}
```

Delivery expects a `2xx` response within 10 seconds. Retries follow the schedule in integration-contract.md.

**Classification: OPTIONAL** (webhook infrastructure)

---

## 7. Error Responses

All errors use a consistent envelope:

```json
{
  "error": {
    "code": "TASK_INVALID_TRANSITION",
    "message": "Cannot start a task with status 'completed'.",
    "details": {
      "current_status": "completed",
      "attempted_transition": "start"
    }
  }
}
```

See integration-contract.md section 5 for the full error code table.

---

## 8. Classification Summary

| Endpoint group | Classification |
|---|---|
| Agents CRUD (1.1–1.5) | **CORE REQUIRED** |
| Tasks lifecycle (2.1–2.5) | **CORE REQUIRED** |
| Messages (3.1–3.2) | **CORE REQUIRED** |
| Governance requests + approvals (4.1–4.7) | **CORE REQUIRED** |
| Governance rollback (4.8) | OPTIONAL |
| Governance audit (4.9) | **CORE REQUIRED** |
| Observability ingest (5.1–5.4) | **CORE REQUIRED** |
| Observability query (5.5–5.7) | **CORE REQUIRED** |
| Observability daily metrics (5.8) | OPTIONAL |
| Observability health scores (5.9) | OPTIONAL |
| Observability alerts (5.10–5.11) | OPTIONAL |
| Webhooks (6.1–6.6) | OPTIONAL |

**CORE REQUIRED** = Must be implemented for a functional external tool integration.
**OPTIONAL** = Enhances the platform but external tools can operate without it.
