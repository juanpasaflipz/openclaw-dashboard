# Integration Contract v1

> Phase 0 — specification only. No code changes.

This document defines the contract that external AI tools must follow to integrate with the Green Monkey Control Plane API. It covers identifiers, authentication, event schemas, idempotency, retry semantics, and error handling.

---

## 1. Required Identifiers

Every API call operates within a strict scoping hierarchy. External tools must track and supply these identifiers.

### 1.1 Identifier hierarchy

```
workspace_id (implicit from API key)
  └── agent_id (int)
       ├── task_id (UUID string)
       │    └── event entries (int PK, append-only)
       └── run_id (UUID string)
            └── event entries (int PK, append-only)
```

### 1.2 Identifier definitions

| Identifier | Type | Source | Scope | Notes |
|---|---|---|---|---|
| `workspace_id` | int | **Implicit** — derived from the API key | Top-level tenant boundary | Currently equivalent to `user_id`. Never sent by the client; always resolved server-side from the authenticated key. |
| `agent_id` | int | Returned by `POST /agents` or `GET /agents` | Workspace-scoped | Agents cannot operate across workspaces. External tools must register an agent and use its ID for all subsequent calls. |
| `task_id` | UUID string | Returned by `POST /tasks` | Workspace-scoped | Globally unique. Used for task transitions, event queries, and message linking. |
| `run_id` | UUID string | Returned by `POST /observability/runs` | Workspace-scoped | Globally unique. Groups observability events within a single execution span. |
| `request_id` | int | Returned by `POST /governance/requests` | Workspace-scoped | PolicyChangeRequest identifier. |
| `grant_id` | int | Returned by approve (delegate mode) | Workspace-scoped | DelegationGrant identifier. |
| `thread_id` | UUID string | Client-generated | Workspace-scoped | Optional grouping for messages outside of tasks. Must be a valid UUID if provided. |

### 1.3 Identifier rules

1. **workspace_id is never sent by clients.** It is derived from the API key. Any `workspace_id` field in a request body is ignored.
2. **agent_id must belong to the authenticated workspace.** Referencing an agent from another workspace returns `404`.
3. **task_id and run_id are UUIDs.** The server generates them. Clients must not generate their own task or run IDs.
4. **thread_id is client-generated.** If an external tool wants to group messages into a conversation outside of a task, it generates and manages thread IDs (UUIDs).

---

## 2. Authentication Model

### 2.1 API keys per workspace

Each workspace can provision API keys through the dashboard or the observability key management endpoints. Keys follow the existing `ObsApiKey` model.

| Property | Value |
|---|---|
| Format | `gm_` prefix + 32 random hex chars (e.g., `gm_a1b2c3d4e5f6...`) |
| Storage | SHA-256 hash stored in `ObsApiKey.key_hash`. Raw key shown once at creation. |
| Display | `ObsApiKey.key_prefix` stores first 8 chars for identification in UI. |
| Limit | Governed by `WorkspaceTier.max_api_keys` (default 1, up to 10 on higher tiers). |

### 2.2 Request authentication

```
Authorization: Bearer gm_a1b2c3d4e5f6...
```

The server:
1. Extracts the token from the `Authorization` header.
2. Computes `SHA-256(token)` and looks up `ObsApiKey.key_hash`.
3. Verifies `is_active = true`.
4. Resolves `workspace_id` from `ObsApiKey.user_id`.
5. Updates `last_used_at`.

Unauthenticated requests receive `401`. Keys for deactivated workspaces receive `403`.

### 2.3 Key lifecycle

| Operation | Method |
|---|---|
| Create key | Dashboard UI or `POST /api/v1/observability/keys` (future) |
| Rotate key | Create a new key, migrate clients, deactivate old key |
| Revoke key | Dashboard UI sets `is_active = false` |

**Classification: CORE REQUIRED** — API key authentication is the sole auth mechanism for external tools. Session-based auth (magic link) is for the dashboard UI only.

---

## 3. Event Schemas

### 3.1 Webhook delivery envelope

Every outbound webhook event uses this envelope:

```json
{
  "id": "dlv_<unique_delivery_id>",
  "event": "<event_type>",
  "workspace_id": 1,
  "timestamp": "2026-02-14T13:00:00Z",
  "data": { ... }
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique delivery ID. Prefixed with `dlv_`. Used for deduplication by receivers. |
| `event` | string | Dot-namespaced event type (e.g., `task.completed`). |
| `workspace_id` | int | The workspace that owns the resource. |
| `timestamp` | string | ISO 8601 UTC. When the event occurred (not when it was delivered). |
| `data` | object | Event-specific payload. Structure depends on `event` type. |

### 3.2 Event type catalog

#### Agent events

**`agent.created`**
```json
{
  "data": {
    "agent": {
      "id": 42,
      "name": "Research Bot",
      "agent_type": "external",
      "is_active": true,
      "created_at": "2026-02-14T12:00:00Z"
    }
  }
}
```

**`agent.updated`** — same shape, reflects post-update state.

**`agent.deleted`**
```json
{
  "data": { "agent_id": 42 }
}
```

#### Task events

**`task.created`**, **`task.started`**, **`task.completed`**, **`task.failed`**, **`task.canceled`**
```json
{
  "data": {
    "task": {
      "id": "f47ac10b-...",
      "title": "Summarize Q4 earnings",
      "status": "completed",
      "assigned_to_agent_id": 42,
      "output": { "summary": "..." },
      "created_at": "2026-02-14T12:00:00Z",
      "updated_at": "2026-02-14T12:15:00Z"
    }
  }
}
```

**`task.blocked`** — includes the triggering risk context:
```json
{
  "data": {
    "task": { ... },
    "risk_event": {
      "policy_type": "daily_spend_cap",
      "breach_value": "52.30",
      "threshold_value": "50.00"
    }
  }
}
```

#### Message events

**`message.created`**
```json
{
  "data": {
    "message": {
      "id": 5001,
      "from_agent_id": 10,
      "to_agent_id": 42,
      "task_id": "f47ac10b-...",
      "content": "Please include revenue breakdown.",
      "created_at": "2026-02-14T12:05:00Z"
    }
  }
}
```

#### Governance events

**`governance.request_created`**, **`governance.request_approved`**, **`governance.request_denied`**
```json
{
  "data": {
    "request": {
      "id": 301,
      "agent_id": 42,
      "status": "approved",
      "requested_changes": { ... },
      "reason": "..."
    },
    "delegation_grant": null
  }
}
```

**`governance.delegation_applied`**
```json
{
  "data": {
    "audit_entry": {
      "id": 901,
      "agent_id": 42,
      "event_type": "delegation_applied",
      "details": { "grant_id": 15, "changes_applied": { ... } }
    }
  }
}
```

**`governance.delegation_revoked`**
```json
{
  "data": {
    "grant": { "id": 15, "agent_id": 42, "active": false, "revoked_at": "..." }
  }
}
```

#### Observability events

**`obs.alert_fired`**
```json
{
  "data": {
    "alert": {
      "id": 2001,
      "rule_id": 88,
      "agent_id": 42,
      "rule_type": "cost_per_day",
      "metric_value": "12.50",
      "threshold_value": "10.00",
      "message": "Agent 'Research Bot' exceeded daily cost cap ($12.50 > $10.00).",
      "triggered_at": "2026-02-14T13:00:00Z"
    }
  }
}
```

**`obs.run_finished`**
```json
{
  "data": {
    "run": {
      "run_id": "a1b2c3d4-...",
      "agent_id": 42,
      "status": "success",
      "total_cost_usd": "0.13",
      "started_at": "2026-02-14T12:30:00Z",
      "finished_at": "2026-02-14T12:32:00Z"
    }
  }
}
```

---

## 4. Idempotency

### 4.1 Idempotency keys

Write endpoints that create resources accept an `idempotency_key` field in the request body.

| Endpoint | Key field | Server column | Behavior on duplicate |
|---|---|---|---|
| `POST /tasks` | `idempotency_key` | `CollaborationTask` — new `idempotency_key` column | Return `200` with existing task |
| `POST /messages` | `idempotency_key` | `AgentMessage` — new `idempotency_key` column | Return `200` with existing message |
| `POST /observability/events` | `idempotency_key` | `ObsEvent.dedupe_key` | Return `200` with existing event |
| `POST /governance/requests` | `idempotency_key` | `PolicyChangeRequest` — new `idempotency_key` column | Return `200` with existing request |

### 4.2 Key rules

1. **Format:** Arbitrary string, max 255 characters. Recommended format: `{resource}-{client_id}-{sequence}` (e.g., `task-agent42-run7-step3`).
2. **Scope:** Keys are scoped to `(workspace_id, endpoint)`. The same key on different endpoints creates separate resources.
3. **TTL:** Keys are retained for 7 days. After TTL, the same key may create a new resource.
4. **Uniqueness enforcement:** Duplicate key on the same endpoint within TTL returns the original response (status code `200`, not `201`). The request body is NOT re-evaluated — the original result is returned.
5. **Optional:** If `idempotency_key` is omitted, the request always creates a new resource.

### 4.3 Webhook delivery deduplication

Webhook receivers should deduplicate on the `id` field of the delivery envelope. The same delivery may be sent more than once due to retries.

---

## 5. Error Codes

### 5.1 HTTP status codes

| Status | Meaning | When |
|---|---|---|
| `200` | OK | Successful read, update, or idempotent duplicate |
| `201` | Created | New resource created |
| `400` | Bad Request | Malformed JSON, missing required fields, invalid field values |
| `401` | Unauthorized | Missing or invalid API key |
| `403` | Forbidden | Key is deactivated, workspace suspended, tier limit exceeded, role/delegation insufficient |
| `404` | Not Found | Resource does not exist or does not belong to this workspace |
| `409` | Conflict | Invalid state transition (e.g., starting a completed task) |
| `422` | Unprocessable Entity | Semantically invalid (e.g., assigning task to inactive agent) |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unexpected server failure |

### 5.2 Error code catalog

All error responses use the envelope:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description.",
    "details": { }
  }
}
```

| Code | HTTP | Description |
|---|---|---|
| `AUTH_MISSING` | 401 | No Authorization header |
| `AUTH_INVALID` | 401 | API key not found or malformed |
| `AUTH_DEACTIVATED` | 403 | API key is deactivated |
| `WORKSPACE_SUSPENDED` | 403 | Workspace is suspended or deleted |
| `TIER_LIMIT_EXCEEDED` | 403 | Workspace tier quota reached (details include `limit_type`) |
| `ROLE_INSUFFICIENT` | 403 | Agent's role does not permit this operation |
| `DELEGATION_EXPIRED` | 403 | Delegation grant is expired or revoked |
| `DELEGATION_EXCEEDED` | 403 | Requested change exceeds grant bounds |
| `NOT_FOUND` | 404 | Resource not found in this workspace |
| `AGENT_NOT_FOUND` | 404 | Referenced agent does not exist |
| `TASK_NOT_FOUND` | 404 | Referenced task does not exist |
| `RUN_NOT_FOUND` | 404 | Referenced run does not exist |
| `VALIDATION_ERROR` | 400 | Request body failed validation (details include field-level errors) |
| `INVALID_EVENT_TYPE` | 400 | Unrecognized observability event type |
| `TASK_INVALID_TRANSITION` | 409 | State machine does not allow this transition |
| `TASK_RISK_BLOCKED` | 409 | Risk check prevents task start (details include breach info) |
| `AGENT_INACTIVE` | 422 | Target agent is deactivated |
| `REQUEST_ALREADY_RESOLVED` | 409 | Governance request already approved/denied/expired |
| `RATE_LIMITED` | 429 | Too many requests (details include `retry_after_seconds`) |
| `INTERNAL_ERROR` | 500 | Unexpected failure |

---

## 6. Retry Semantics

### 6.1 Client-side retries (external tools calling the API)

External tools MUST implement retries for transient failures.

| Status | Retryable | Strategy |
|---|---|---|
| `429` | Yes | Respect `Retry-After` header. Exponential backoff starting at the indicated delay. |
| `500` | Yes | Exponential backoff: 1s, 2s, 4s, 8s, 16s. Max 5 attempts. |
| `502`, `503`, `504` | Yes | Same as 500. |
| `400`, `401`, `403`, `404`, `409`, `422` | No | Do not retry. Fix the request or resolve the condition. |
| Network error / timeout | Yes | Same as 500. |

**Rules:**
1. Always use exponential backoff with jitter: `delay = min(base * 2^attempt + random(0, 1s), 30s)`.
2. Maximum 5 retry attempts per request.
3. Idempotency keys MUST be reused across retries of the same logical operation.
4. Retry budget: no more than 20% of total requests should be retries. If a sustained error rate exceeds this, stop retrying and alert.

### 6.2 Server-side retries (webhook deliveries)

The platform retries failed webhook deliveries with the following schedule:

| Attempt | Delay after previous attempt |
|---|---|
| 1 (initial) | Immediate |
| 2 | 30 seconds |
| 3 | 2 minutes |
| 4 | 10 minutes |
| 5 | 1 hour |
| 6 | 4 hours |

After 6 failed attempts, the delivery is marked as `failed` and no further retries occur.

**Failure definition:** Any non-2xx response, network error, or timeout (>10 seconds).

**Ordering:** Deliveries for the same webhook URL are sent in order. A failing delivery blocks subsequent deliveries to that URL until it either succeeds or exhausts retries. Different webhook URLs are independent.

**Disable threshold:** If a webhook URL accumulates 50 consecutive failures, the webhook is automatically deactivated (`is_active = false`). The workspace owner is notified via the dashboard.

---

## 7. Rate Limits

| Scope | Limit | Window |
|---|---|---|
| Per API key | 300 requests | 1 minute |
| Per API key, write endpoints | 60 requests | 1 minute |
| Batch event ingestion | 10 requests | 1 minute |
| Governance requests | 10 requests | 1 minute |

Rate limit headers on every response:
```
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 287
X-RateLimit-Reset: 1739538060
Retry-After: 12          (only on 429 responses)
```

---

## 8. Versioning

### 8.1 URL-based versioning

The API version is embedded in the URL path: `/api/v1/...`. When breaking changes are introduced, a new version (`/api/v2/...`) is published. The previous version remains available for a deprecation period of at least 6 months.

### 8.2 What constitutes a breaking change

| Breaking (new version required) | Non-breaking (same version) |
|---|---|
| Removing a field from a response | Adding a new field to a response |
| Renaming a field | Adding a new optional request field |
| Changing a field's type | Adding a new endpoint |
| Removing an endpoint | Adding a new webhook event type |
| Changing error code semantics | Adding a new error code |
| Changing auth mechanism | Relaxing a validation rule |

### 8.3 Deprecation header

When an endpoint is deprecated, responses include:
```
Deprecation: true
Sunset: Sat, 14 Aug 2027 00:00:00 GMT
Link: </api/v2/tasks>; rel="successor-version"
```

---

## 9. Integration Checklist

External tool authors should verify the following before going live:

### CORE REQUIRED

- [ ] Obtain a workspace API key from the dashboard
- [ ] Register an agent via `POST /api/v1/agents`
- [ ] Include `Authorization: Bearer <key>` on every request
- [ ] Implement exponential backoff with jitter for 429/5xx responses
- [ ] Use idempotency keys on all write operations
- [ ] Track `task_id` and `run_id` returned by the server
- [ ] Handle all error codes in section 5.2 (at minimum: distinguish retryable vs non-retryable)
- [ ] Respect state machine transitions — do not attempt invalid transitions
- [ ] Start observability runs before executing work, finish them after
- [ ] Submit governance requests for policy changes instead of attempting direct mutation

### OPTIONAL

- [ ] Register webhooks for real-time event delivery
- [ ] Implement webhook signature verification (`X-Signature-256`)
- [ ] Deduplicate webhook deliveries using the `id` field
- [ ] Configure alert rules for cost/error monitoring
- [ ] Query daily metrics and health scores for agent monitoring
