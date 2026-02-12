# 04 — Alerts

## Alert Rule Types

| Rule Type | Metric | Unit | Example |
|-----------|--------|------|---------|
| `cost_per_day` | Sum of `cost_usd` for today's events | USD | Alert if daily cost > $5.00 |
| `error_rate` | % of `run_finished` events with status=error in window | % | Alert if error rate > 20% |
| `no_heartbeat` | Minutes since last heartbeat event | minutes | Alert if no heartbeat for > 30m |

## Creating Rules

**POST /api/obs/alerts/rules** (session auth)

```json
{
  "name": "High Cost Alert",
  "rule_type": "cost_per_day",
  "threshold": 5.0,
  "agent_id": 1,
  "window_minutes": 60,
  "cooldown_minutes": 360
}
```

- `agent_id` is optional. Omit for workspace-wide rules.
- `window_minutes` applies to `error_rate` (lookback window). Default: 60.
- `cooldown_minutes` prevents repeated alerts after firing. Default: 360 (6 hours).

## Evaluation

Alert rules are evaluated by a Vercel cron job every 15 minutes:

```
POST /api/obs/internal/evaluate-alerts
Authorization: Bearer <CRON_SECRET>
```

The evaluation loop:
1. Load all enabled rules
2. Skip rules still in cooldown
3. Compute current metric value
4. If metric > threshold → fire alert
5. Record `ObsAlertEvent`, update `last_triggered_at`
6. Send Slack notification (if `SLACK_WEBHOOK_URL` configured)

## Slack Notifications

Set `SLACK_WEBHOOK_URL` in environment to receive alerts in Slack:

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx
```

Alert message format:
```
Alert 'High Cost Alert': agent #1 daily cost $5.2345 exceeds $5.0000 threshold
```

## Managing Rules

- **GET /api/obs/alerts/rules** — List all rules
- **POST /api/obs/alerts/rules/:id** — Update (`is_enabled`, `threshold`, etc.)
- **POST /api/obs/alerts/rules/:id** with `{"delete": true}` — Delete rule

## Alert Events

- **GET /api/obs/alerts/events** — List fired alerts (most recent first)
- **POST /api/obs/alerts/events/:id/acknowledge** — Mark as acknowledged
