# @greenmonkey/sdk

Node.js SDK for the Green Monkey Control Plane API. Typed client with built-in retries, idempotency, and convenience helpers for multi-agent orchestration.

## Install

```bash
cd sdk/node
npm install
```

## Quick Start

```typescript
import { GreenMonkeyClient } from "@greenmonkey/sdk";

const gm = new GreenMonkeyClient({
  apiKey: "gm_your_api_key",
  baseUrl: "https://your-deployment.vercel.app",
});

// Register an agent
const agent = await gm.registerAgent({
  name: "My Agent",
  agent_type: "external",
});

// Create a task (idempotency key auto-generated)
const task = await gm.createTask({
  title: "Analyze dataset",
  assigned_to_agent_id: agent.id,
  input: { dataset: "sales_q4.csv" },
});

// Send a message between agents
await gm.sendMessage({
  from_agent_id: agent.id,
  to_agent_id: 42,
  task_id: task.id,
  content: "Starting analysis now.",
});

// Emit an observability event
await gm.emitEvent({
  event_type: "llm_call",
  status: "success",
  agent_id: agent.id,
  model: "gpt-4o",
  tokens_in: 1500,
  tokens_out: 800,
});

// Request a policy change
await gm.requestPolicyChange({
  agent_id: agent.id,
  requested_changes: { daily_spend_cap: "50.00" },
  reason: "Need higher cap for batch processing.",
});
```

## Client Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `apiKey` | `string` | **required** | API key (`gm_...` format) |
| `baseUrl` | `string` | **required** | Base URL of the Green Monkey deployment |
| `maxRetries` | `number` | `5` | Max retry attempts for 429/5xx |
| `timeoutMs` | `number` | `30000` | Request timeout in milliseconds |

## Resource Clients

The client exposes typed resource namespaces for full API access:

```typescript
gm.agents     // .list(), .get(), .create(), .update(), .delete()
gm.tasks      // .create(), .list(), .get(), .start(), .complete(), .fail(), .cancel(), .assign(), .listEvents()
gm.messages   // .send(), .list()
gm.governance // .createRequest(), .listRequests(), .approve(), .deny(), .listDelegations(), .revokeDelegation(), .applyDelegation(), .listAudit()
gm.observability // .ingestEvent(), .ingestBatch(), .listEvents(), .startRun(), .finishRun(), .listRuns(), .getRun()
```

## Convenience Helpers

These top-level methods auto-generate idempotency keys and provide a streamlined API:

| Method | Description |
|--------|-------------|
| `registerAgent(params)` | Create and return a new agent |
| `createTask(params)` | Create a task with auto-idempotency key |
| `sendMessage(params)` | Send a message with auto-idempotency key |
| `emitEvent(params)` | Ingest an observability event with auto-idempotency key |
| `requestPolicyChange(params)` | Submit a governance request with auto-idempotency key |

## Retries & Backoff

The client automatically retries on:
- **429 Too Many Requests** - respects `Retry-After` header
- **5xx Server Errors** - exponential backoff with jitter

Non-retryable errors (400, 401, 403, 404, 409, 422) are thrown immediately.

Backoff formula: `min(1s * 2^attempt + random(0-1s), 30s)`, max 5 attempts.

## Idempotency

All write endpoints (`createTask`, `sendMessage`, `emitEvent`, `requestPolicyChange`) accept an optional `idempotency_key`. If omitted, a unique key is auto-generated. If you provide your own, it will be reused across retries to ensure exactly-once semantics.

## Error Handling

```typescript
import { ApiRequestError, NetworkError, TimeoutError } from "@greenmonkey/sdk";

try {
  await gm.tasks.start(taskId);
} catch (err) {
  if (err instanceof ApiRequestError) {
    console.log(err.status);  // HTTP status code
    console.log(err.code);    // e.g. "TASK_INVALID_TRANSITION"
    console.log(err.message); // Human-readable message
    console.log(err.details); // Optional field-level details
  } else if (err instanceof NetworkError) {
    console.log("Network failure:", err.cause);
  } else if (err instanceof TimeoutError) {
    console.log("Request timed out");
  }
}
```

## Run the Example

The example demonstrates multi-agent collaboration: a Coordinator creates tasks, a Researcher gathers data, and a Writer produces a report.

```bash
cd sdk/node
npm install
export GM_API_KEY="gm_your_key"
export GM_BASE_URL="http://localhost:5000"
npm run example
```

## Build

```bash
npm run build    # Compiles to dist/
```
