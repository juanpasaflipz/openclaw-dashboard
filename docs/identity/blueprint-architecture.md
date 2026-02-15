# Agent Blueprint & Capability Architecture

> Phase 0 — architectural reference only. No code changes.

## 1. Problem Statement

Today, agents are configured ad-hoc: an `Agent` row holds a flat JSON `llm_config`, has no formal role constraints, and offers no tool-level permission boundary. The platform enforces risk policies and governance at the workspace tier level, but nothing prevents an agent from being reconfigured to use any model, call any tool, or operate under any risk posture — all without audit trail on the configuration itself.

This creates three gaps:

1. **No reusable profiles.** Creating a "Research Agent" pattern means manually duplicating config. There is no template or versioned definition.
2. **No capability boundaries.** The `ToolGateway` checks workspace-level tier limits, but never asks "is this agent allowed to use this specific tool or model?"
3. **No configuration governance.** Agent config changes (`llm_config`, `identity_config`) bypass the governance pipeline entirely. Only `RiskPolicy` changes require approval.

## 2. Design Goals

| # | Goal | Constraint |
|---|------|------------|
| G1 | Reusable agent profiles via **AgentBlueprint** | Must not break existing Agent CRUD |
| G2 | Fine-grained permissions via **CapabilityBundle** | Must integrate with existing ToolGateway |
| G3 | Immutable, versioned blueprint definitions | Published blueprints never mutate |
| G4 | Agent instances derived from blueprints with limited overrides | Overrides validated against capability bounds |
| G5 | Backward-compatible: existing agents work without blueprints | Implicit blueprint generation for legacy agents |
| G6 | Workspace-scoped isolation | Blueprints owned by workspace, never shared across workspaces |

## 3. Current System Audit

### 3.1 Agent Model (models.py)

The `Agent` model is a flat entity with 25+ columns. Key config fields:

| Field | Type | Purpose | Governance? |
|-------|------|---------|-------------|
| `llm_config` | JSON | `{provider, model, api_key, temperature}` | None — freely mutable |
| `identity_config` | JSON | `{personality, role, behavior}` | None |
| `agent_type` | String | `direct`, `websocket`, `http_api` | Subscription limit only |
| `is_active` | Boolean | Can be set by risk interventions | Via RiskPolicy pause_agent |

**No formal concept of:** allowed tools, allowed models, risk profile defaults, role-based hierarchy constraints, or versioned configuration.

### 3.2 Runtime Layer (core/runtime/)

| Component | What it does | What it lacks |
|-----------|-------------|---------------|
| `ExecutionContext` | Immutable (workspace_id, agent_id, run_id) — scopes every operation | No blueprint_id or capability reference |
| `ToolGateway` | Proxies tool calls through governance + observability | Only checks tier limits, never per-agent tool allowlists |
| `AgentRuntime` | Workspace-scoped session manager with messaging | No blueprint initialization, no capability seeding |
| `RuntimeSession` | Active agent handle (tools + messaging) | No capability-bounded tool listing |

### 3.3 Risk Engine (core/risk_engine/)

| Component | Relevant integration point |
|-----------|---------------------------|
| `RiskPolicy` | Per-workspace or per-agent policies (spend cap, error rate, token rate) |
| Interventions | `pause_agent`, `model_downgrade`, `alert_only`, `throttle` |
| Enforcement | Runs on cycle; separate from runtime |

**Key insight:** Risk policies operate post-hoc (detect breach, then intervene). Blueprints will define the *default risk posture* so that policies are pre-seeded at instantiation time rather than requiring manual setup.

### 3.4 Governance Layer (core/governance/)

| Component | Relevant integration point |
|-----------|---------------------------|
| `PolicyChangeRequest` | Agents can request risk policy changes (threshold, cooldown, action_type) |
| `DelegationGrant` | Time-bound autonomy for policy self-modification |
| `boundaries.py` | Immutable tier-derived limits that no change can exceed |
| Governance audit | Append-only trail for all governance events |

**Key insight:** Governance currently covers risk policy mutations only. Blueprint capability overrides will use the same approval pipeline.

### 3.5 Collaboration Layer (core/collaboration/)

| Component | Relevant integration point |
|-----------|---------------------------|
| `AgentRole` | `supervisor`, `worker`, `specialist` — optional per-agent role |
| `TeamRule` | Workspace-level hierarchy settings |
| `CollaborationTask` | Inter-agent task assignment with parent chain |
| `governance_hooks.py` | Pre-task-start risk check; observability emit on lifecycle events |

**Key insight:** AgentRole is manually assigned. Blueprints will define `role_type` as a first-class attribute, seeding the AgentRole at instantiation.

### 3.6 Tool System (agent_tools.py + ToolGateway)

Current tool access: `get_tools_for_user(workspace_id)` returns all tools available to the workspace. There is no per-agent filtering. The gateway checks `check_agent_allowed()` which only verifies tier-level agent count limits.

**Gap:** No mechanism to say "Agent X can use tools [gmail_send, calendar_read] but not [binance_trade]."

---

## 4. New Abstractions

### 4.1 AgentBlueprint

A blueprint is a **versioned, immutable template** that defines what an agent is allowed to be.

```
AgentBlueprint
├── id (UUID)
├── workspace_id (FK → users.id)
├── name (string, human-readable)
├── description (text)
├── role_type (enum: researcher, executor, supervisor, autonomous)
├── status (enum: draft, published, archived)
├── created_at (timestamp)
├── created_by (FK → users.id)
└── versions[] → AgentBlueprintVersion
```

**Lifecycle:**
```
draft ──publish──> published ──archive──> archived
                       │
                       └── clone ──> new draft
```

- `draft`: Mutable. Can be edited freely. Cannot be used to instantiate agents.
- `published`: Immutable. The source of truth for agent instances. New versions created by cloning.
- `archived`: Soft-deleted. Existing instances continue to reference it. No new instances allowed.

### 4.2 AgentBlueprintVersion

Each published snapshot is a version. Versions are append-only — they never change after creation.

```
AgentBlueprintVersion
├── id (int, PK)
├── blueprint_id (FK → agent_blueprints.id)
├── version (int, auto-incrementing per blueprint)
├── allowed_models (JSON array: ["openai/gpt-4o", "anthropic/claude-sonnet-4-5-20250929"])
├── allowed_tools (JSON array: ["gmail_send", "calendar_read", "web_search"])
├── default_risk_profile (JSON: {daily_spend_cap: 10.00, action_type: "alert_only"})
├── hierarchy_defaults (JSON: {role: "worker", can_assign_to_peers: false, can_escalate: true})
├── memory_strategy (JSON: {type: "semantic", retention_days: 30, max_embeddings: 1000})
├── escalation_rules (JSON: {on_tool_denied: "notify_supervisor", on_risk_breach: "pause"})
├── llm_defaults (JSON: {provider: "openai", model: "gpt-4o", temperature: 0.7})
├── identity_defaults (JSON: {personality: "...", system_prompt: "..."})
├── override_policy (JSON: {allowed_overrides: ["temperature", "system_prompt"], denied_overrides: ["provider", "allowed_tools"]})
├── published_at (timestamp)
├── published_by (FK → users.id)
├── changelog (text, human-readable)
│
└── UNIQUE(blueprint_id, version)
```

**Immutability contract:** Once a version row is inserted, no column may be updated. Ever. This is the foundational guarantee that makes auditing meaningful.

### 4.3 CapabilityBundle

A capability is a **named, reusable permission set** that can be attached to multiple blueprints.

```
CapabilityBundle
├── id (int, PK)
├── workspace_id (FK → users.id)
├── name (string, unique per workspace)
├── description (text)
├── tool_set (JSON array: ["gmail_send", "gmail_read", "gmail_draft"])
├── model_constraints (JSON: {allowed_providers: ["openai"], max_model_tier: "standard"})
├── risk_constraints (JSON: {max_daily_spend: 5.00, max_single_action_cost: 1.00})
├── is_system (boolean, default false)  — system bundles are read-only
├── created_at (timestamp)
├── updated_at (timestamp)
```

**Blueprint-Capability join:**
```
blueprint_capabilities (join table)
├── blueprint_version_id (FK → agent_blueprint_versions.id)
├── capability_id (FK → capability_bundles.id)
│
└── UNIQUE(blueprint_version_id, capability_id)
```

**Resolved capability:** At runtime, the effective capability for an agent is the **union** of all capabilities attached to its blueprint version. Conflicts resolve as follows:
- `tool_set`: union of all tool sets
- `model_constraints.allowed_providers`: intersection (most restrictive)
- `risk_constraints`: minimum values (most restrictive)

### 4.4 AgentInstance

An agent instance is a **running agent bound to a specific blueprint version** with optional constrained overrides.

```
AgentInstance
├── id (int, PK)
├── agent_id (FK → agents.id, unique)  — 1:1 with existing Agent
├── blueprint_id (FK → agent_blueprints.id)
├── blueprint_version (int)  — the version number at instantiation
├── workspace_id (FK → users.id)
├── overrides (JSON: limited set, validated against override_policy)
├── policy_snapshot (JSON: full resolved capability at instantiation)
├── instantiated_at (timestamp)
├── instantiated_by (FK → users.id)
├── last_policy_refresh (timestamp)
```

**Key constraint:** `agent_id` is unique — one agent maps to at most one instance binding. Agents without an instance binding are "legacy" agents (see backward compatibility).

---

## 5. Entity Relationships

```
 User (workspace)
  │
  ├── owns AgentBlueprint (N)
  │    └── has AgentBlueprintVersion (N, append-only)
  │         └── attaches CapabilityBundle (M:N via join)
  │
  ├── owns CapabilityBundle (N)
  │
  ├── owns Agent (N)  [unchanged]
  │    └── has AgentInstance (0..1)
  │         ├── references AgentBlueprint
  │         ├── references blueprint_version
  │         └── holds policy_snapshot + overrides
  │
  └── [all existing relationships preserved]
```

---

## 6. Integration Points

### 6.1 Runtime Integration (core/runtime/)

**ExecutionContext extension:**
```python
# Current
ExecutionContext(workspace_id, agent_id, run_id, created_at)

# Extended (Phase 3)
ExecutionContext(workspace_id, agent_id, run_id, created_at,
                blueprint_id=None, blueprint_version=None,
                resolved_capabilities=None)
```

The `resolved_capabilities` field is a frozen dict computed at session start from the agent's policy_snapshot. It contains:
- `allowed_tools: frozenset[str]`
- `allowed_models: frozenset[str]`
- `risk_profile: dict`

**ToolGateway enhancement:**
```python
# Current _check_governance: tier limits only
# Enhanced: tier limits + capability check

def _check_governance(self, tool_name, arguments):
    # 1. Existing tier check
    ...
    # 2. NEW: Capability check
    caps = self._ctx.resolved_capabilities
    if caps and tool_name not in caps['allowed_tools']:
        return {'error': f'Tool {tool_name} not in agent capabilities',
                'governance': True, 'capability_denied': True}
    return None
```

**AgentRuntime.start_session enhancement:**
```python
# Current: creates ExecutionContext, runs pre-start checks
# Enhanced: loads AgentInstance, resolves capabilities, seeds context

def start_session(self, user_id, agent_id):
    ctx = ExecutionContext.create(user_id, agent_id)

    # NEW: Load blueprint capabilities if instance exists
    instance = AgentInstance.query.filter_by(agent_id=agent_id).first()
    if instance:
        ctx = ctx.with_capabilities(instance.policy_snapshot)

    self._pre_start_check(ctx)
    ...
```

### 6.2 Risk Engine Integration

**At instantiation:** When an AgentInstance is created from a blueprint, the system auto-creates `RiskPolicy` rows from `default_risk_profile`:

```python
def instantiate_agent(agent_id, blueprint_id, version, workspace_id, overrides=None):
    version_row = get_blueprint_version(blueprint_id, version)

    # 1. Create AgentInstance with policy snapshot
    snapshot = resolve_capabilities(version_row)
    instance = AgentInstance(
        agent_id=agent_id,
        blueprint_id=blueprint_id,
        blueprint_version=version,
        workspace_id=workspace_id,
        overrides=validated_overrides(overrides, version_row.override_policy),
        policy_snapshot=snapshot,
    )

    # 2. Seed risk policies from blueprint defaults
    risk_profile = version_row.default_risk_profile
    if risk_profile.get('daily_spend_cap'):
        create_or_update_risk_policy(
            workspace_id=workspace_id,
            agent_id=agent_id,
            policy_type='daily_spend_cap',
            threshold_value=risk_profile['daily_spend_cap'],
            action_type=risk_profile.get('action_type', 'alert_only'),
        )

    # 3. Seed agent role from hierarchy defaults
    hierarchy = version_row.hierarchy_defaults
    if hierarchy:
        upsert_agent_role(workspace_id, agent_id, hierarchy)
```

### 6.3 Governance Integration

**Override governance:** When an agent instance requests an override beyond `override_policy.allowed_overrides`, the request is routed through the existing `PolicyChangeRequest` pipeline:

```
Agent requests override (e.g., use a model not in allowed_models)
  │
  ├── If override is in allowed_overrides → apply immediately, log audit
  │
  └── If override is NOT in allowed_overrides → create PolicyChangeRequest
       └── Workspace owner approves/denies via existing governance flow
```

**New governance event types:**
- `blueprint_published` — Blueprint version published
- `instance_created` — Agent bound to blueprint
- `instance_override_applied` — Allowed override applied
- `instance_override_requested` — Denied override sent to approval queue

### 6.4 Collaboration Integration

**Role seeding:** When an AgentInstance is created, `hierarchy_defaults.role` is used to create or update the `AgentRole` for that agent. This replaces manual role assignment for blueprint-backed agents.

**Escalation rules:** The `escalation_rules` field defines behavior when a tool is denied or a risk breach occurs:
- `on_tool_denied: "notify_supervisor"` — Creates an AgentMessage to the supervisor agent
- `on_risk_breach: "pause"` — Triggers the existing risk engine pause_agent intervention
- `on_risk_breach: "escalate"` — Creates a CollaborationTask for supervisor review

---

## 7. Capability Resolution Algorithm

When an agent session starts, capabilities must be resolved from the blueprint version's attached capability bundles:

```
Input:
  - blueprint_version.allowed_tools (blueprint-level)
  - blueprint_version.allowed_models (blueprint-level)
  - For each attached CapabilityBundle:
      - bundle.tool_set
      - bundle.model_constraints
      - bundle.risk_constraints

Resolution:

  1. Start with blueprint-level allowed_tools and allowed_models as the BASE set.

  2. For each attached capability bundle:
     a. tools = tools ∩ bundle.tool_set  (intersection — capability bundles RESTRICT)
        Exception: if blueprint allowed_tools is empty/null, use union of bundles.
     b. models = models ∩ bundle.model_constraints.allowed_providers

  3. Risk constraints: take the MINIMUM across all bundles:
     - min(all bundle.risk_constraints.max_daily_spend)
     - min(all bundle.risk_constraints.max_single_action_cost)

  4. Apply agent instance overrides (only for allowed_overrides fields):
     - e.g., temperature=0.3 overrides llm_defaults.temperature

  5. Freeze and attach to ExecutionContext.
```

**Rationale for intersection:** Capability bundles act as *permission grants*. Attaching "Email Capability" and "Calendar Capability" means the agent can use email tools AND calendar tools. But within each bundle, `model_constraints` acts as a restriction — the agent can only use models allowed by ALL bundles.

**Correction to above:** After further analysis, the more practical design is:
- `tool_set`: **union** across bundles (bundles are additive — each grants tools)
- `allowed_models`: **intersection** across bundles (bundles are restrictive on models)
- `risk_constraints`: **minimum** across bundles (most conservative wins)

The blueprint-level `allowed_tools` and `allowed_models` act as a **ceiling** — the resolved set can never exceed the blueprint-level allowlist.

---

## 8. Versioning Semantics

### 8.1 Version Numbering

Versions are monotonically increasing integers within a blueprint, starting at 1:
```
blueprint "Research Agent" v1 → v2 → v3
```

No semantic versioning. The version number indicates temporal ordering, not breaking vs non-breaking changes.

### 8.2 Immutability Guarantee

Once `AgentBlueprintVersion` row is inserted:
- No UPDATE statements are ever issued against it.
- The row is never deleted (even if blueprint is archived).
- `published_at` and `published_by` are set exactly once.

Application-level enforcement: the `publish_blueprint_version()` function inserts and returns. No `update_blueprint_version()` function exists.

### 8.3 Instance Pinning

An `AgentInstance` is pinned to a specific `(blueprint_id, blueprint_version)` pair. When a new version is published:
- Existing instances continue using their pinned version.
- The workspace owner can explicitly upgrade instances to the new version.
- Upgrading re-resolves capabilities and re-snapshots the policy.

This prevents surprise behavior changes: publishing a new blueprint version never automatically changes running agents.

### 8.4 Cloning

Cloning creates a new draft blueprint with all fields copied from the source version. The clone has its own `blueprint_id` and starts at version 0 (draft). Cloning is:
- Intra-workspace only.
- Does not copy agent instances.
- Does copy capability bundle attachments (by reference, not deep copy).

---

## 9. Backward Compatibility

### 9.1 Legacy Agents (No Blueprint)

Existing agents have no `AgentInstance` binding. They must continue to work identically.

**Rule BC1:** If `AgentInstance.query.filter_by(agent_id=X).first()` returns `None`, the agent operates in **legacy mode**: no capability restrictions, no blueprint governance. The `ToolGateway` capability check is skipped for legacy agents.

**Rule BC2:** A migration path exists to generate an **implicit blueprint** from any legacy agent's current config:
```python
def generate_implicit_blueprint(agent):
    """Create a blueprint that exactly matches the agent's current config."""
    bp = AgentBlueprint(
        workspace_id=agent.user_id,
        name=f"{agent.name} (Auto)",
        role_type=infer_role_type(agent),
        status='published',
    )
    version = AgentBlueprintVersion(
        blueprint_id=bp.id,
        version=1,
        allowed_models=["*"],  # unrestricted — matches legacy behavior
        allowed_tools=["*"],   # unrestricted
        default_risk_profile={},
        llm_defaults=agent.llm_config or {},
        identity_defaults=agent.identity_config or {},
        override_policy={"allowed_overrides": ["*"]},  # fully open
    )
    instance = AgentInstance(
        agent_id=agent.id,
        blueprint_id=bp.id,
        blueprint_version=1,
        workspace_id=agent.user_id,
        policy_snapshot=resolve_capabilities(version),
    )
```

The `"*"` wildcard in `allowed_models` and `allowed_tools` means "unrestricted" — preserving the exact current behavior.

**Rule BC3:** Implicit blueprint generation is optional and triggered by:
1. Explicit user action ("Convert to blueprint-managed agent")
2. Workspace-wide migration script
3. Never automatic or forced

### 9.2 API Backward Compatibility

All existing endpoints continue to work:

| Endpoint | Behavior with blueprint | Behavior without blueprint |
|----------|------------------------|---------------------------|
| `POST /api/agents` | Creates Agent. Optionally accepts `blueprint_id` to also create AgentInstance | Creates Agent (legacy mode) |
| `PUT /api/agents/:id` | Updates Agent fields. If instance exists, validates overrides against blueprint | Updates Agent fields (unrestricted) |
| `DELETE /api/agents/:id` | Deletes Agent + AgentInstance | Deletes Agent |
| `GET /api/agents/:id` | Returns Agent + instance + blueprint info if available | Returns Agent (unchanged) |

---

## 10. New Tables

### 10.1 agent_blueprints

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | String(36) / UUID | PK |
| `workspace_id` | Integer | FK → users.id, NOT NULL, INDEXED |
| `name` | String(200) | NOT NULL |
| `description` | Text | NULLABLE |
| `role_type` | String(50) | NOT NULL, DEFAULT 'worker' |
| `status` | String(20) | NOT NULL, DEFAULT 'draft' |
| `created_at` | DateTime | NOT NULL, DEFAULT utcnow |
| `created_by` | Integer | FK → users.id, NOT NULL |

### 10.2 agent_blueprint_versions

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, auto-increment |
| `blueprint_id` | String(36) | FK → agent_blueprints.id, NOT NULL, INDEXED |
| `version` | Integer | NOT NULL |
| `allowed_models` | JSON | NULLABLE |
| `allowed_tools` | JSON | NULLABLE |
| `default_risk_profile` | JSON | NULLABLE |
| `hierarchy_defaults` | JSON | NULLABLE |
| `memory_strategy` | JSON | NULLABLE |
| `escalation_rules` | JSON | NULLABLE |
| `llm_defaults` | JSON | NULLABLE |
| `identity_defaults` | JSON | NULLABLE |
| `override_policy` | JSON | NULLABLE |
| `published_at` | DateTime | NOT NULL, DEFAULT utcnow |
| `published_by` | Integer | FK → users.id, NOT NULL |
| `changelog` | Text | NULLABLE |
| | | UNIQUE(blueprint_id, version) |

### 10.3 capability_bundles

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, auto-increment |
| `workspace_id` | Integer | FK → users.id, NOT NULL, INDEXED |
| `name` | String(200) | NOT NULL |
| `description` | Text | NULLABLE |
| `tool_set` | JSON | NULLABLE |
| `model_constraints` | JSON | NULLABLE |
| `risk_constraints` | JSON | NULLABLE |
| `is_system` | Boolean | NOT NULL, DEFAULT false |
| `created_at` | DateTime | NOT NULL, DEFAULT utcnow |
| `updated_at` | DateTime | DEFAULT utcnow, ON UPDATE |
| | | UNIQUE(workspace_id, name) |

### 10.4 blueprint_capabilities (join table)

| Column | Type | Constraints |
|--------|------|-------------|
| `blueprint_version_id` | Integer | FK → agent_blueprint_versions.id, NOT NULL |
| `capability_id` | Integer | FK → capability_bundles.id, NOT NULL |
| | | PK(blueprint_version_id, capability_id) |

### 10.5 agent_instances

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | PK, auto-increment |
| `agent_id` | Integer | FK → agents.id, NOT NULL, UNIQUE |
| `blueprint_id` | String(36) | FK → agent_blueprints.id, NOT NULL |
| `blueprint_version` | Integer | NOT NULL |
| `workspace_id` | Integer | FK → users.id, NOT NULL, INDEXED |
| `overrides` | JSON | NULLABLE |
| `policy_snapshot` | JSON | NOT NULL |
| `instantiated_at` | DateTime | NOT NULL, DEFAULT utcnow |
| `instantiated_by` | Integer | FK → users.id, NOT NULL |
| `last_policy_refresh` | DateTime | NULLABLE |

---

## 11. File Layout

```
core/identity/
├── __init__.py
├── agent_blueprint.py        # Blueprint CRUD, versioning, cloning, publishing
├── agent_capabilities.py     # CapabilityBundle CRUD, resolution algorithm
├── blueprint_registry.py     # Query interface: list/search/filter blueprints
├── agent_instance.py         # Instantiation, override validation, policy snapshot
└── backward_compat.py        # Implicit blueprint generation for legacy agents
```

This follows the existing `core/` convention:
- `core/governance/` — governance domain
- `core/risk_engine/` — risk domain
- `core/runtime/` — runtime domain
- `core/identity/` — **NEW** identity domain (blueprints + capabilities)

---

## 12. Invariants

These invariants must hold at all times. Any code that violates them is a bug.

| # | Invariant | Enforcement |
|---|-----------|-------------|
| I1 | A published blueprint version is never updated | No UPDATE function exists. Application code only INSERTs versions. |
| I2 | An agent instance's policy_snapshot is set at creation and on explicit refresh | Only `instantiate_agent()` and `refresh_instance_policy()` write this field. |
| I3 | Capability resolution at runtime matches the stored policy_snapshot | The snapshot is the source of truth. Re-resolution is only for upgrade/refresh. |
| I4 | Agent instance overrides are validated against override_policy | `validate_overrides()` is called before any override write. |
| I5 | Blueprint workspace_id matches all related entities | Checked at creation: instance.workspace_id == blueprint.workspace_id == agent.user_id |
| I6 | Legacy agents (no instance) have unrestricted capabilities | ToolGateway skips capability check when resolved_capabilities is None. |
| I7 | Archiving a blueprint does not affect existing instances | Instances pin to (blueprint_id, version), not to blueprint status. |
| I8 | All blueprint/instance mutations are logged to GovernanceAuditLog | Uses existing `log_governance_event()` infrastructure. |
| I9 | Capability bundles use workspace-scoped unique names | DB constraint: UNIQUE(workspace_id, name). |
| I10 | Risk policies seeded from blueprints go through standard risk_engine creation | No bypass of `core/risk_engine/policy.py` functions. |

---

## 13. Phase Execution Plan

| Phase | Scope | Depends on | Deliverables |
|-------|-------|------------|--------------|
| **0** | Architecture design | — | This document |
| **1** | Schema + core logic | Phase 0 | Tables, Blueprint CRUD, versioning, cloning, instantiation, unit tests |
| **2** | Capability system | Phase 1 | CapabilityBundle CRUD, resolution, ToolGateway integration, capability tests |
| **3** | Runtime integration | Phase 2 | ExecutionContext extension, AgentRuntime blueprint init, risk seeding, integration tests |
| **4** | API surface | Phase 3 | REST endpoints, API docs |
| **5** | Backward compatibility | Phase 4 | Implicit blueprint generation, migration script |

---

## 14. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking existing agent CRUD | Low | High | All new tables are additive. Agent model unchanged. Legacy mode default. |
| Performance: capability resolution on every session start | Medium | Low | Policy snapshot cached on AgentInstance. Resolution only on create/refresh. |
| Complexity: too many JSON fields on versions | Medium | Medium | JSON schemas validated at write time. TypedDict validation in Python. |
| Governance overhead for overrides | Low | Low | `override_policy.allowed_overrides` enables immediate apply for safe fields. Only restricted overrides hit the approval queue. |
| Migration complexity for existing agents | Low | Medium | Migration is opt-in (Rule BC3). Implicit blueprints use `"*"` wildcards to preserve behavior. |

---

## 15. Open Questions (To Resolve Before Phase 1)

1. **Blueprint sharing across workspaces:** Should we support a "marketplace" or "template library" where blueprints can be published globally? **Current answer: No.** Workspace-scoped only in v1. Cross-workspace sharing is a future concern.

2. **Capability bundle versioning:** Should bundles themselves be versioned (like blueprints)? **Current answer: No.** Bundles are mutable. The blueprint version captures a snapshot of the bundle attachment at publish time. If a bundle changes later, existing published versions are unaffected because the version's `allowed_tools`/`allowed_models` are stored directly on the version row, not as a reference to bundle state.

3. **Maximum capabilities per blueprint:** Should there be a hard limit? **Current answer:** Defer to tier enforcement. The join table has no practical limit, but we may add a tier-gated cap later.

4. **Tool name registry:** The capability system references tools by string name (e.g., `"gmail_send"`). We need a canonical tool name registry to validate these strings. **Current answer:** Use the existing `agent_tools.py` tool registry as the source of truth. Validation at blueprint publish time.
