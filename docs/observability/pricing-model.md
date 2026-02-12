# Observability Pricing Model

**Last updated:** 2026-02-11

---

## Overview

The observability layer uses a four-tier pricing model that controls access to monitoring features independently from the main application subscription (`User.subscription_tier`). Each workspace gets a row in the `workspace_tiers` table that defines its limits. Missing rows default to the **Free** tier.

Tier configuration is stored per-workspace in the database. All enforcement reads from `WorkspaceTier.TIER_DEFAULTS` (the canonical source of truth in `models.py`), with the option for admin-applied custom overrides.

---

## Tier Definitions

### Free

The default tier for all new workspaces. Provides basic monitoring to let users evaluate the platform.

- **Target:** Individual developers exploring agent monitoring
- **Goal:** Let users see value before committing

### Production

The entry paid tier. Covers the needs of a single production agent deployment with meaningful retention and alerting.

- **Target:** Solo developers or small teams running agents in production
- **Goal:** First revenue tier — enough features to be indispensable

### Pro

Full-featured tier for teams running multiple agents with advanced diagnostics.

- **Target:** Teams with 5-50 agents, need anomaly detection and deep history
- **Goal:** High-value tier for power users

### Agency

Enterprise-grade tier for organizations managing agent fleets across multiple workspaces.

- **Target:** Agencies, consultancies, or teams managing many client deployments
- **Goal:** Unlock multi-workspace and priority processing

---

## Feature Matrix

| Feature | Free | Production | Pro | Agency |
|---------|------|------------|-----|--------|
| **Monitored agents** | 2 | 10 | 50 | Unlimited |
| **Data retention** | 7 days | 30 days | 90 days | 180 days |
| **Alert rules** | None | 3 | Unlimited | Unlimited |
| **Health score history** | Today only | 7 days | 30 days | 90 days |
| **Anomaly detection** | No | No | Yes | Yes |
| **Slack notifications** | No | Yes | Yes | Yes |
| **API keys** | 1 | 3 | 10 | Unlimited |
| **Batch ingestion size** | 100/req | 500/req | 1,000/req | 1,000/req |
| **Multi-workspace** | No | No | No | Yes |
| **Priority processing** | No | No | No | Yes |

---

## Canonical Defaults (Source of Truth)

All tier defaults live in `models.py` → `WorkspaceTier.TIER_DEFAULTS`:

```python
TIER_DEFAULTS = {
    'free': dict(
        agent_limit=2, retention_days=7, alert_rule_limit=0,
        health_history_days=0, anomaly_detection_enabled=False,
        slack_notifications_enabled=False, multi_workspace_enabled=False,
        priority_processing=False, max_api_keys=1, max_batch_size=100,
    ),
    'production': dict(
        agent_limit=10, retention_days=30, alert_rule_limit=3,
        health_history_days=7, anomaly_detection_enabled=False,
        slack_notifications_enabled=True, multi_workspace_enabled=False,
        priority_processing=False, max_api_keys=3, max_batch_size=500,
    ),
    'pro': dict(
        agent_limit=50, retention_days=90, alert_rule_limit=9999,
        health_history_days=30, anomaly_detection_enabled=True,
        slack_notifications_enabled=True, multi_workspace_enabled=False,
        priority_processing=False, max_api_keys=10, max_batch_size=1000,
    ),
    'agency': dict(
        agent_limit=9999, retention_days=180, alert_rule_limit=9999,
        health_history_days=90, anomaly_detection_enabled=True,
        slack_notifications_enabled=True, multi_workspace_enabled=True,
        priority_processing=True, max_api_keys=9999, max_batch_size=1000,
    ),
}
```

To change a tier's defaults, edit this dict. All enforcement functions read from it via `get_workspace_tier()`.

---

## Limit Dimensions

### Monitored Agents (`agent_limit`)

Counts **distinct `agent_id` values** across all `ObsEvent` rows for the workspace. When at the limit, new (previously-unseen) agents are rejected at ingestion. Existing agents are always allowed.

### Data Retention (`retention_days`)

Controls how far back metrics queries and event listings can reach. The retention window is enforced in two places:

1. **Query-time filtering:** All read endpoints clamp date ranges to the retention window.
2. **Background cleanup:** A cron job (`POST /api/obs/internal/retention-cleanup`) hard-deletes events and runs older than `retention_days + 24h` (grace period).

### Alert Rules (`alert_rule_limit`)

Limits how many `ObsAlertRule` rows the workspace can create. Free tier has 0 (alerts disabled entirely). The cron-based alert evaluator processes all enabled rules regardless — the limit only gates creation.

### Health Score History (`health_history_days`)

Controls how many days of `ObsAgentHealthDaily` scores the health endpoints return. Set to 0 for today-only access. Health scores are **computed for all tiers** (storage is cheap); access is gated.

### Anomaly Detection (`anomaly_detection_enabled`)

When disabled, the `cost_anomaly` component is stripped from health score API responses. The underlying score computation still runs (to avoid recomputation if the user upgrades), but the data is hidden.

### Slack Notifications (`slack_notifications_enabled`)

When disabled, alert events are still created in the database (viewable in-dashboard), but `dispatch_alert_notification()` is not called. Users see alerts; they just don't get Slack pings.

### API Keys (`max_api_keys`)

Limits active `ObsApiKey` count. Only active keys count — revoked keys don't.

### Batch Ingestion Size (`max_batch_size`)

Maximum number of events per `POST /api/obs/ingest/events` request. Exceeding the limit returns 403 for the entire batch (not partial acceptance).

### Multi-Workspace (`multi_workspace_enabled`)

Reserved for Agency tier. Currently `workspace_id == user_id` (v1). When enabled, a workspace-user mapping table will support multiple workspaces per user.

### Priority Processing (`priority_processing`)

Reserved for Agency tier. When enabled, the workspace's alert evaluation and aggregation are processed first in cron jobs.

---

## Design Decisions

### Why a Separate Tier Table?

The observability tier is **decoupled from the app subscription** (`User.subscription_tier`):

1. Observability dimensions (retention, agent limits) differ from app dimensions (max agents, analytics).
2. Independent pricing iteration — changing obs pricing doesn't affect app billing.
3. Future SaaS expansion requires workspace-level billing, not user-level.
4. External customers may have different obs and app tiers.

### Why DB-Stored Limits (Not Code Constants)?

Every limit lives in the `workspace_tiers` row, not in code:

- Admin can apply custom overrides per workspace (e.g., a customer on Production tier with 15 agents instead of 10).
- Tier changes take effect immediately after DB update + cache invalidation.
- A single source of truth avoids drift between code branches.

### Why 9999 Instead of NULL for "Unlimited"?

Integer comparisons (`count >= limit`) work without special-casing NULL. 9999 is the practical unlimited sentinel. No workspace will realistically have 9999 agents or alert rules.

---

## Suggested Pricing (Not Yet Implemented)

| Tier | Suggested Price | Billing |
|------|----------------|---------|
| Free | $0 | — |
| Production | $15/mo | Monthly |
| Pro | $49/mo | Monthly |
| Agency | $149/mo | Monthly or annual |

These are recommendations. Actual pricing should be validated with user research and will be configured via Stripe price IDs mapped to tier names in the billing webhook handler.
