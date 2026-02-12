"""
Alert engine — evaluate rules, fire alerts, dispatch notifications.

Designed to be called from cron endpoints. Restart-safe and idempotent:
- Cooldown prevents double-firing.
- Each rule is evaluated independently; one failure doesn't block others.
- Execution time is tracked and capped.
"""
import time
from datetime import datetime, timedelta
from decimal import Decimal

from core.observability.notifications import dispatch_alert_notification


# Maximum seconds to spend evaluating alerts per cron invocation.
# Prevents Vercel 60s timeout.
MAX_EVALUATION_SECONDS = 45


def evaluate_alerts(max_seconds=MAX_EVALUATION_SECONDS):
    """
    Check all enabled alert rules. Returns count of alerts fired.
    Respects max_seconds to avoid cron timeout.
    """
    from models import db, ObsAlertRule

    rules = ObsAlertRule.query.filter_by(is_enabled=True).all()
    fired = 0
    now = datetime.utcnow()
    start_time = time.monotonic()

    for rule in rules:
        # Time guard
        elapsed = time.monotonic() - start_time
        if elapsed > max_seconds:
            print(f"[obs] Alert evaluation time limit reached ({elapsed:.1f}s). "
                  f"Processed {fired} of {len(rules)} rules.")
            break

        try:
            # Cooldown check
            if rule.last_triggered_at:
                cooldown_end = rule.last_triggered_at + timedelta(minutes=rule.cooldown_minutes)
                if now < cooldown_end:
                    continue

            metric_value = _evaluate_rule_metric(rule, now)
            if metric_value is None:
                continue

            threshold = float(rule.threshold)

            if metric_value > threshold:
                _fire_alert(rule, metric_value, threshold, now)
                fired += 1

        except Exception as e:
            print(f"[obs] alert eval failed rule={rule.id}: {e}")

    return fired


def _evaluate_rule_metric(rule, now):
    """Compute current metric value for a rule. Returns float or None."""
    from models import db, ObsEvent

    if rule.rule_type == 'cost_per_day':
        today = now.date()
        q = db.session.query(db.func.sum(ObsEvent.cost_usd)).filter(
            ObsEvent.user_id == rule.user_id,
            ObsEvent.created_at >= datetime.combine(today, datetime.min.time()),
        )
        if rule.agent_id:
            q = q.filter(ObsEvent.agent_id == rule.agent_id)
        result = q.scalar()
        return float(result) if result else 0.0

    elif rule.rule_type == 'error_rate':
        window_start = now - timedelta(minutes=rule.window_minutes)
        q = ObsEvent.query.filter(
            ObsEvent.user_id == rule.user_id,
            ObsEvent.created_at >= window_start,
            ObsEvent.event_type == 'run_finished',
        )
        if rule.agent_id:
            q = q.filter(ObsEvent.agent_id == rule.agent_id)
        runs = q.all()
        if not runs:
            return None  # No data — don't alert
        errors = len([r for r in runs if r.status == 'error'])
        return (errors / len(runs)) * 100

    elif rule.rule_type == 'no_heartbeat':
        q = ObsEvent.query.filter(
            ObsEvent.user_id == rule.user_id,
            ObsEvent.event_type == 'heartbeat',
        )
        if rule.agent_id:
            q = q.filter(ObsEvent.agent_id == rule.agent_id)
        last = q.order_by(ObsEvent.created_at.desc()).first()
        if not last:
            return float(rule.threshold) + 1  # No heartbeat ever -> trigger
        minutes_since = (now - last.created_at).total_seconds() / 60
        return minutes_since

    return None


def _fire_alert(rule, metric_value, threshold, now):
    """Record alert event and send notifications (tier-gated)."""
    from models import db, ObsAlertEvent

    message = _build_alert_message(rule, metric_value, threshold)

    alert_event = ObsAlertEvent(
        rule_id=rule.id,
        user_id=rule.user_id,
        agent_id=rule.agent_id,
        metric_value=Decimal(str(round(metric_value, 4))),
        threshold_value=Decimal(str(threshold)),
        rule_type=rule.rule_type,
        message=message,
    )
    db.session.add(alert_event)
    rule.last_triggered_at = now
    db.session.commit()

    print(f"[obs] ALERT FIRED: {message}")

    # Dispatch notifications — gated by tier
    from core.observability.tier_enforcement import check_slack_notifications
    if check_slack_notifications(rule.user_id):
        results = dispatch_alert_notification(message)
        if results.get('slack'):
            alert_event.notified_slack = True
            db.session.commit()


def _build_alert_message(rule, metric_value, threshold):
    agent_label = f"agent #{rule.agent_id}" if rule.agent_id else "workspace"
    if rule.rule_type == 'cost_per_day':
        return (f"Alert '{rule.name}': {agent_label} daily cost "
                f"${metric_value:.4f} exceeds ${threshold:.4f} threshold")
    elif rule.rule_type == 'error_rate':
        return (f"Alert '{rule.name}': {agent_label} error rate "
                f"{metric_value:.1f}% exceeds {threshold:.1f}% threshold")
    elif rule.rule_type == 'no_heartbeat':
        return (f"Alert '{rule.name}': {agent_label} no heartbeat for "
                f"{metric_value:.0f} minutes (threshold: {threshold:.0f}m)")
    return f"Alert '{rule.name}': metric {metric_value} > threshold {threshold}"
