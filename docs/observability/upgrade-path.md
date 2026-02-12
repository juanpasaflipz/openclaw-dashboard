# Upgrade Path — Tier Changes & Billing Integration

**Last updated:** 2026-02-11

---

## How Tier Changes Work

A workspace's tier can be changed through three mechanisms:

1. **Admin API** — `POST /api/obs/admin/tier` (immediate, manual)
2. **Billing webhook** — `POST /api/obs/webhooks/billing` (automated, event-driven)
3. **Direct DB update** — modify `workspace_tiers` row + invalidate cache

All three paths result in the same outcome: the `workspace_tiers` row is upserted and the in-memory cache is invalidated. The new limits take effect on the next request (within 60s at worst if cache invalidation is skipped).

---

## Upgrade Flow

### 1. User Hits a Limit

The user attempts a gated action and receives a 403 response:

```json
{
  "error": "Alert rules are not available on the free tier. Upgrade to create alert rules.",
  "upgrade_required": true
}
```

### 2. Frontend Shows Upgrade Prompt

The frontend checks for `upgrade_required: true` in error responses and shows a contextual upgrade CTA. The `GET /api/obs/tier` endpoint provides the user's current tier for display:

```json
{
  "tier": {
    "workspace_id": 42,
    "tier_name": "free",
    "agent_limit": 2,
    "retention_days": 7,
    "alert_rule_limit": 0,
    ...
  }
}
```

### 3. User Completes Payment (Future — Stripe)

When Stripe integration is connected, the payment flow will:
1. User selects a tier on the pricing page.
2. Stripe Checkout creates a subscription.
3. Stripe sends a webhook to `POST /api/obs/webhooks/billing`.
4. The webhook handler maps the Stripe price ID to a tier name and upserts the `workspace_tiers` row.
5. The user's limits are upgraded immediately.

### 4. Tier Applies Immediately

No restart or delay. The cache is invalidated on write, so the next API call uses the new limits.

---

## Downgrade Flow

### Voluntary Downgrade (Subscription Cancellation)

1. User cancels subscription in Stripe.
2. Stripe sends `obs_subscription.deleted` webhook.
3. Handler sets the workspace to the **free** tier.
4. Existing data is preserved but:
   - Events older than 7 days become invisible in queries.
   - The retention cleanup cron will hard-delete events past 7 days + 24h grace.
   - Alert rules remain but can't be created. Existing rules still evaluate (with free-tier features like no Slack).
   - New agents beyond 2 are rejected at ingestion, but existing agents continue working.

### Involuntary Downgrade (Payment Failure)

Same as voluntary — Stripe sends `obs_subscription.deleted` after payment recovery fails. The handler downgrades to free.

### Grace Period

The retention cleanup job applies a 24-hour grace period (`GRACE_PERIOD_HOURS = 24`). After downgrade, events are not immediately deleted — the next cron run after 24 hours past the new retention window will clean them up. This gives users time to export data or re-upgrade.

---

## Admin Tier Management

### Set or Update a Tier

```
POST /api/obs/admin/tier
Authorization: session cookie (admin user)

{
  "workspace_id": 42,
  "tier_name": "production",
  "overrides": {
    "agent_limit": 15,
    "retention_days": 45
  }
}
```

- `tier_name` is required and must be one of: `free`, `production`, `pro`, `agency`.
- `overrides` are optional. They apply on top of the tier's defaults.
- The endpoint upserts: creates the row if missing, updates if existing.
- Cache is invalidated immediately.

### View Any Workspace's Tier

```
GET /api/obs/admin/tier/<workspace_id>
Authorization: session cookie (admin user)
```

Returns the same format as `GET /api/obs/tier`.

### Custom Overrides

Admins can customize individual limits per workspace without changing the tier name. For example, a workspace on the Production tier with a custom agent limit of 15:

```json
{
  "workspace_id": 42,
  "tier_name": "production",
  "overrides": {"agent_limit": 15}
}
```

The workspace is still labeled "production" but has a non-standard agent limit. Allowed override keys:

- `agent_limit`
- `retention_days`
- `alert_rule_limit`
- `health_history_days`
- `anomaly_detection_enabled`
- `slack_notifications_enabled`
- `multi_workspace_enabled`
- `priority_processing`
- `max_api_keys`
- `max_batch_size`

---

## Billing Webhook Integration

### Endpoint

```
POST /api/obs/webhooks/billing
Authorization: Bearer <OBS_BILLING_WEBHOOK_SECRET>
```

### Authentication

The webhook accepts two auth methods:
1. `Authorization: Bearer <OBS_BILLING_WEBHOOK_SECRET>` header (recommended for Stripe).
2. `password` field in JSON body matching `ADMIN_PASSWORD` (fallback for manual testing).

In production with Stripe, this should be replaced with Stripe signature verification:

```python
stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
```

### Event Types

#### `obs_subscription.created`

A new subscription was created. Assigns the specified tier.

```json
{
  "event_type": "obs_subscription.created",
  "workspace_id": 42,
  "tier_name": "production",
  "subscription_id": "sub_xxx"
}
```

#### `obs_subscription.updated`

An existing subscription changed tiers (upgrade or plan change).

```json
{
  "event_type": "obs_subscription.updated",
  "workspace_id": 42,
  "tier_name": "pro",
  "subscription_id": "sub_xxx"
}
```

#### `obs_subscription.deleted`

Subscription was cancelled or payment failed. Downgrades to free.

```json
{
  "event_type": "obs_subscription.deleted",
  "workspace_id": 42,
  "subscription_id": "sub_xxx"
}
```

Note: `tier_name` is not required for delete events — it always downgrades to free.

### Stripe Integration Steps (Future)

1. Create Stripe products and prices for each tier.
2. Store the `price_id → tier_name` mapping (env var or DB config table).
3. Replace the current auth check with `stripe.Webhook.construct_event()`.
4. Parse the Stripe event to extract `customer`, `subscription`, and `price_id`.
5. Map `price_id` to `tier_name` and call the existing upsert logic.
6. Configure the Stripe webhook URL to `https://yourdomain.com/api/obs/webhooks/billing`.

---

## Grandfathering Strategy

### New Users

All new users start on the **free** tier (no `workspace_tiers` row — the code defaults to free).

### Existing Users (Pre-Tier System)

Existing users who were using observability before the tier system was introduced should be grandfathered to the **production** tier. This can be done via a one-time admin script:

```python
from models import db, User, WorkspaceTier

existing_users = User.query.filter(User.id.in_(
    db.session.query(ObsEvent.user_id).distinct()
)).all()

for user in existing_users:
    if not WorkspaceTier.query.filter_by(workspace_id=user.id).first():
        tier = WorkspaceTier(
            workspace_id=user.id,
            tier_name='production',
            **WorkspaceTier.TIER_DEFAULTS['production']
        )
        db.session.add(tier)

db.session.commit()
```

Or use the admin API to set tiers individually.

### Pro App Subscribers

Users who already have `User.subscription_tier == 'pro'` (app subscription) could optionally be auto-synced to the Production or Pro observability tier. This is a business decision — the two systems are intentionally decoupled, but a sync script can bridge them:

```python
pro_users = User.query.filter_by(subscription_tier='pro').all()
for user in pro_users:
    # Sync to production obs tier (or pro, depending on business rules)
    ...
```

---

## Frontend UX Patterns

### Upgrade Prompt on 403

When any API call returns `upgrade_required: true`, show a contextual modal:

```
You've reached the limit for [feature] on your current plan.

Current plan: Free
[Feature] limit: [current limit]

Upgrade to Production to get:
- 10 monitored agents
- 30-day retention
- 3 alert rules
- Slack notifications

[Upgrade Now] [Maybe Later]
```

### Tier Badge in Dashboard

Use `GET /api/obs/tier` to display the current tier name and key limits in the observability dashboard header. Show retention window prominently so users understand their data boundary.

### Feature Gating UI

For features gated by tier (anomaly detection, alerts on free):
- Show the feature in the UI but in a disabled/locked state.
- Show what tier unlocks it: "Anomaly Detection — Available on Pro plan".
- Don't hide features entirely — users need to see what they're missing.

### Approaching Limits

Track current usage against limits:
- "2 of 2 agents monitored" (at limit — show upgrade CTA)
- "1 of 3 alert rules used" (under limit — show progress)
- "5 of 7 retention days used" (approaching — no action needed)

---

## API Reference

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/obs/tier` | GET | Session | View own tier config |
| `/api/obs/admin/tier` | POST | Admin session | Set/update any workspace tier |
| `/api/obs/admin/tier/<id>` | GET | Admin session | View any workspace tier |
| `/api/obs/webhooks/billing` | POST | Bearer token | Billing event handler |
