# Domain Model

> Phase 0 — architectural reference only. No code changes.

## 1. Entity Map

```
 User (1)
  ├── owns Agent (N)
  │    ├── has AgentRole (0..1)
  │    ├── creates AgentAction (N)  [approval queue]
  │    ├── emits ObsEvent (N)
  │    ├── scoped by RiskPolicy (N)
  │    ├── assigned CollaborationTask (N)
  │    └── sends AgentMessage (N)
  ├── owns Superpower (N)  [per service_type]
  ├── owns UserModelConfig (N)  [per feature slot]
  ├── owns ChatConversation (N)
  │    └── has ChatMessage (N)
  ├── owns MemoryEmbedding (N)
  ├── has CreditTransaction (N)
  ├── has MagicLink (N)
  └── scoped by WorkspaceTier (0..1)

 PolicyChangeRequest (submitted by Agent, approved by User)
  └── produces DelegationGrant (0..1)

 ObsRun (groups ObsEvent by run)
 ObsAlertRule (owned by User)
  └── fires ObsAlertEvent (N)
```

---

## 2. Entities, IDs, and Ownership

### Control Plane Entities

| Entity | PK | Owner FK | Natural Key / Alt ID | Notes |
|---|---|---|---|---|
| **User** | `id` (int) | — | `email` (unique) | Root owner of all user-scoped data |
| **MagicLink** | `id` (int) | `user_id` | `token` (unique) | 15-min TTL, single-use |
| **CreditTransaction** | `id` (int) | `user_id` | — | Append-only ledger |
| **Agent** | `id` (int) | `user_id` | `moltbook_api_key` (unique, optional) | Central managed entity |
| **AgentAction** | `id` (int) | `user_id` + `agent_id` | — | Status: pending → approved → executed/failed |
| **CollaborationTask** | `id` (int) | `user_id` | — | Assigned to `agent_id`. Parent chain via `parent_task_id`. |
| **TaskEvent** | `id` (int) | (via task) | — | Append-only. Links to `task_id`. |
| **AgentMessage** | `id` (int) | `user_id` | — | Linked to optional `task_id` or `thread_id` |
| **AgentRole** | `id` (int) | `user_id` + `agent_id` | — | One role per agent per workspace |
| **TeamRule** | `id` (int) | `user_id` | — | One rule-set per workspace |

### Governance Entities

| Entity | PK | Owner FK | Natural Key / Alt ID | Notes |
|---|---|---|---|---|
| **PolicyChangeRequest** | `id` (int) | `user_id` + `agent_id` | — | Status: pending → approved/denied/expired → applied |
| **DelegationGrant** | `id` (int) | `user_id` + `agent_id` | — | Time-bound. `expires_at` enforced. |
| **GovernanceAuditLog** | `id` (int) | `user_id` | — | Append-only. `before_snapshot` / `after_snapshot`. |

### Risk Engine Entities

| Entity | PK | Owner FK | Natural Key / Alt ID | Notes |
|---|---|---|---|---|
| **RiskPolicy** | `id` (int) | `user_id` | — | Scoped to optional `agent_id`. Types: daily_spend_cap, error_rate_cap, token_rate_cap. |
| **RiskEvent** | `id` (int) | `user_id` | — | Append-only breach record. |
| **RiskAuditLog** | `id` (int) | `user_id` | — | Append-only intervention record. |

### Observability Entities

| Entity | PK | Owner FK | Natural Key / Alt ID | Notes |
|---|---|---|---|---|
| **ObsApiKey** | `id` (int) | `user_id` | `key_hash` (unique) | Hashed; prefix stored for display. |
| **ObsEvent** | `id` (int) | `user_id` | `uid` (unique UUID) | Append-only. Immutable after insert. |
| **ObsRun** | `id` (int) | `user_id` | `run_id` (unique UUID) | Groups events. Status: running → completed/failed. |
| **ObsAgentDailyMetrics** | `id` (int) | `user_id` + `agent_id` | date + agent_id (unique) | Pre-aggregated daily rollup. |
| **ObsAlertRule** | `id` (int) | `user_id` | — | Metric + operator + threshold. |
| **ObsAlertEvent** | `id` (int) | `user_id` | — | Append-only. Links to `rule_id`. |
| **ObsLlmPricing** | `id` (int) | — | `provider` + `model` (unique) | Reference table. Not user-scoped. |
| **ObsAgentHealthDaily** | `id` (int) | `user_id` + `agent_id` | date + agent_id (unique) | Composite health score. |
| **WorkspaceTier** | `id` (int) | `user_id` | — | One per workspace. Tiers: free, production, pro, agency. |

### Integration Entities

| Entity | PK | Owner FK | Natural Key / Alt ID | Notes |
|---|---|---|---|---|
| **Superpower** | `id` (int) | `user_id` | `service_type` per user (unique) | Encrypted OAuth tokens. |
| **ConfigFile** | `id` (int) | `user_id` | `filename` per user (unique) | Generic config storage (serverless compat). |

### AI Workbench Entities

| Entity | PK | Owner FK | Natural Key / Alt ID | Notes |
|---|---|---|---|---|
| **UserModelConfig** | `id` (int) | `user_id` | `feature` per user (unique) | LLM settings per feature slot. |
| **ChatConversation** | `id` (int) | `user_id` | `conversation_id` (unique UUID) | Optional `agent_id` link. |
| **ChatMessage** | `id` (int) | (via conversation) | — | Role: user/assistant/system. |
| **MemoryEmbedding** | `id` (int) | `user_id` | — | Vector embeddings for semantic search. |
| **WebBrowsingResult** | `id` (int) | `user_id` | — | Cached web research. |

### Monetization Entities

| Entity | PK | Owner FK | Natural Key / Alt ID | Notes |
|---|---|---|---|---|
| **SubscriptionPlan** | `id` (int) | — | `name` (unique) | Reference table. free / pro. |
| **CreditPackage** | `id` (int) | — | — | Reference table. |
| **PostHistory** | `id` (int) | `user_id` + `agent_id` | — | Moltbook post tracking. |

### Moltbook Entities

| Entity | PK | Owner FK | Natural Key / Alt ID | Notes |
|---|---|---|---|---|
| **MoltbookFeedCache** | `id` (int) | `user_id` | `cache_key` (unique) | TTL-based feed cache. |
| **UserUpvote** | `id` (int) | `user_id` | — | Tracks upvoted posts. |
| **AnalyticsSnapshot** | `id` (int) | `agent_id` | date + agent_id (unique) | Daily analytics rollup. |
| **PostAnalytics** | `id` (int) | `agent_id` | `post_id` per agent (unique) | Per-post metrics. |

---

## 3. Ownership Rules

### Rule O1: User-scoped isolation

Every entity with a `user_id` FK is **owned** by that user. Queries **must** always filter by `user_id` from the authenticated session. No endpoint returns data across users (except admin endpoints).

### Rule O2: Agent-scoped delegation

Agents act on behalf of their owning user. An agent's `user_id` determines which `Superpower` tokens, `RiskPolicy` rules, and `WorkspaceTier` limits apply. An agent cannot access another user's resources.

### Rule O3: Workspace = User

Currently, "workspace" is equivalent to a single user account. `WorkspaceTier`, `TeamRule`, and all collaboration entities are scoped to one `user_id`. Multi-user workspaces are a future concern.

### Rule O4: Reference tables are global

`SubscriptionPlan`, `CreditPackage`, and `ObsLlmPricing` are system-level reference data. Not user-scoped.

---

## 4. Isolation Rules

### Rule I1: Tenant isolation at query level

Every DB query on user-scoped tables **must** include `WHERE user_id = :current_user_id`. This is enforced in core module functions, not trusted to routes alone.

### Rule I2: Agent isolation within a workspace

Agents within the same workspace (user) can collaborate (tasks, messages). Agents across different workspaces **cannot** interact — no cross-user agent messaging or task assignment.

### Rule I3: Credential isolation

`Superpower.access_token_encrypted` and `refresh_token_encrypted` are decrypted **only** inside adapter code at point-of-use. Decrypted tokens are never logged, serialized to JSON responses, or stored in secondary tables.

### Rule I4: Audit log immutability

`GovernanceAuditLog`, `RiskAuditLog`, `TaskEvent`, and `ObsEvent` rows are never updated or deleted at the application layer. Retention policies (if any) are handled by background jobs, never by user-facing API calls.

### Rule I5: Tier-bound resource limits

`WorkspaceTier` defines quotas (events/day, agents, retention days). Core modules enforce these limits before accepting writes — not in routes.

---

## 5. State Machines

### 5.1 AgentAction Lifecycle

```
                ┌──────────┐
                │ pending   │
                └─────┬─────┘
           approve    │     reject
          ┌───────────┼───────────┐
          v           │           v
   ┌──────────┐       │    ┌──────────┐
   │ approved  │       │    │ rejected  │
   └─────┬─────┘       │    └──────────┘
         │ execute      │
    ┌────┴────┐         │
    v         v         │
┌────────┐ ┌────────┐   │
│executed│ │ failed  │   │
└────────┘ └────────┘   │
```

### 5.2 CollaborationTask Lifecycle

```
 ┌────────┐
 │ queued  │
 └───┬────┘
     │ start (risk check passes)
     v
 ┌────────┐
 │running  │──── fail ───> ┌────────┐
 └───┬────┘               │ failed  │
     │                     └────────┘
     │ complete
     v
 ┌───────────┐
 │ completed  │
 └───────────┘

 Any state ── cancel ──> ┌──────────┐
                         │ canceled  │
                         └──────────┘

 running ── risk breach ──> ┌─────────┐
                            │ blocked  │
                            └─────────┘
```

### 5.3 PolicyChangeRequest Lifecycle

```
 ┌─────────┐
 │ pending  │──── deny ────> ┌────────┐
 └────┬────┘                │ denied  │
      │                      └────────┘
      │ approve
      v
 ┌──────────┐
 │ approved  │──── apply (via delegation) ──> ┌─────────┐
 └──────────┘                                │ applied  │
                                              └─────────┘
 pending ── expire (cron) ──> ┌─────────┐
                              │ expired  │
                              └─────────┘
```

### 5.4 ObsRun Lifecycle

```
 ┌─────────┐
 │ running  │
 └────┬────┘
      ├── finish(success) ──> ┌───────────┐
      │                       │ completed  │
      │                       └───────────┘
      └── finish(error) ────> ┌────────┐
                              │ failed  │
                              └────────┘
```

---

## 6. Event Flow

Events flow through the system in a consistent pattern:

```
 Agent / User Action
       │
       v
 ┌─────────────────────┐
 │  API Route           │  validates input, authenticates
 └──────────┬──────────┘
            │
            v
 ┌─────────────────────┐
 │  Core Module         │  enforces rules, mutates state
 │  (governance / risk  │
 │   / tasks / obs)     │
 └──────────┬──────────┘
            │
     ┌──────┼──────────────┐
     │      │              │
     v      v              v
  State   Audit Log     ObsEvent
  Change  (append)      (append)
     │
     v
 ┌─────────────────────┐
 │  Alert Engine        │  evaluates rules post-write
 └──────────┬──────────┘
            │ (if threshold breached)
            v
 ┌─────────────────────┐
 │  Risk Engine         │  evaluates policies, may intervene
 └──────────┬──────────┘
            │ (if intervention needed)
            v
 ┌─────────────────────┐
 │  Notification        │  Slack webhook / future: multi-channel
 └─────────────────────┘
```

### Key Event Types

| Event Type | Source | Sink | Side Effects |
|---|---|---|---|
| `llm_call` | Agent via ObsEvent | Observability pipeline | Cost tracking, daily metrics, alert evaluation |
| `tool_call` | Agent via ObsEvent | Observability pipeline | Latency tracking |
| `risk_breach` | Risk evaluator | RiskEvent + RiskAuditLog | Intervention (throttle/downgrade/pause) |
| `policy_change_request` | Agent via governance | PolicyChangeRequest + GovernanceAuditLog | Awaits human approval |
| `delegation_applied` | Agent via governance | GovernanceAuditLog | Policy mutated under grant |
| `task_transition` | Collaboration engine | TaskEvent | Risk check on start; may block |
| `agent_action_proposed` | Agent | AgentAction (pending) | Awaits human approval |
| `agent_action_executed` | Approval handler | AgentAction (executed) + adapter call | Side effect in external service |

---

## 7. Domain Boundaries Summary

```
┌──────────────────────────────────────────────────────┐
│                    CONTROL PLANE                      │
│                                                      │
│  Identity    Tasks    Governance   Risk   Observ.    │
│  ┌──────┐  ┌──────┐  ┌─────────┐ ┌────┐ ┌───────┐  │
│  │User  │  │Collab│  │PCR      │ │Pol │ │Event  │  │
│  │Magic │  │Task  │  │Deleg.   │ │Eval│ │Run    │  │
│  │Link  │  │Event │  │Audit    │ │Aud │ │Metric │  │
│  │Credit│  │Msg   │  │Rollback │ │Int │ │Alert  │  │
│  │Tier  │  │Role  │  │Boundary │ │    │ │Health │  │
│  └──────┘  └──────┘  └─────────┘ └────┘ └───────┘  │
│                                                      │
│  ── writes only through owning module ──             │
│  ── audit logs are append-only ──                    │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│                 INTEGRATION ADAPTERS                  │
│                                                      │
│  Gmail  Calendar  Drive  Notion  Binance  GitHub     │
│  Slack  Discord   Telegram  Spotify  Todoist Dropbox │
│                                                      │
│  ── translate vendor APIs ──                         │
│  ── never mutate core state directly ──              │
│  ── removable without breaking core ──               │
└──────────────────────────────────────────────────────┘
```
