"""
Risk evaluator — detect policy breaches and create pending risk events.

Reads observability metrics, compares against policy thresholds, and creates
risk_events with status='pending'. Does NOT execute interventions — that is
the executor's job (interventions.py).

All threshold comparisons use Decimal. No float math.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal


def evaluate_policies(workspace_id=None):
    """Evaluate all active risk policies. Creates pending risk_events for breaches.

    Args:
        workspace_id: If provided, evaluate only policies for this workspace.
                      If None, evaluate all enabled policies.

    Returns:
        int: Count of new risk_events created.
    """
    from core.risk_engine.policy import get_active_policies

    policies = get_active_policies(workspace_id=workspace_id)
    created = 0

    for policy in policies:
        try:
            if _process_policy(policy):
                created += 1
        except Exception as e:
            from models import db
            db.session.rollback()
            print(f"[risk] evaluate failed policy={policy.id}: {e}")

    return created


def _process_policy(policy):
    """Evaluate a single policy. Returns True if a new risk_event was created."""
    now = datetime.utcnow()

    # 1. Cooldown check
    if _is_in_cooldown(policy, now):
        return False

    # 2. Compute current metric value
    metric_value = _evaluate_metric(policy, now)
    if metric_value is None:
        return False

    # 3. Threshold comparison (Decimal, no floats)
    threshold = Decimal(str(policy.threshold_value))
    if metric_value <= threshold:
        return False

    # 4. Idempotency: check for existing event
    dedupe_key = _build_dedupe_key(policy, now)
    if _has_existing_event(dedupe_key):
        return False

    # 5. Create pending risk_event
    _create_risk_event(policy, metric_value, threshold, dedupe_key, now)
    return True


def _evaluate_metric(policy, now):
    """Dispatch to the correct metric evaluator based on policy_type.

    Returns:
        Decimal or None (None means no data / not applicable).
    """
    if policy.policy_type == 'daily_spend_cap':
        return _evaluate_daily_spend(policy, now)
    # Future: error_rate_cap, token_rate_cap
    return None


def _evaluate_daily_spend(policy, now):
    """Query real-time daily spend from obs_events.

    Returns:
        Decimal: Total cost_usd since midnight for the policy's scope.
    """
    from models import db, ObsEvent

    today = now.date()
    day_start = datetime.combine(today, datetime.min.time())

    q = db.session.query(db.func.sum(ObsEvent.cost_usd)).filter(
        ObsEvent.user_id == policy.workspace_id,
        ObsEvent.created_at >= day_start,
    )
    if policy.agent_id is not None:
        q = q.filter(ObsEvent.agent_id == policy.agent_id)

    result = q.scalar()
    if result is None:
        return Decimal('0')
    return Decimal(str(result))


def _is_in_cooldown(policy, now):
    """Check if the policy is within its cooldown window.

    Looks at the most recent risk_event for this policy to determine if
    cooldown_minutes have elapsed since the last evaluation.

    Returns:
        bool: True if still in cooldown (should skip).
    """
    from models import RiskEvent

    last_event = (
        RiskEvent.query
        .filter_by(policy_id=policy.id)
        .filter(RiskEvent.status.in_(['pending', 'executed']))
        .order_by(RiskEvent.evaluated_at.desc())
        .first()
    )
    if last_event is None:
        return False

    cooldown_end = last_event.evaluated_at + timedelta(minutes=policy.cooldown_minutes)
    return now < cooldown_end


def _has_existing_event(dedupe_key):
    """Check if a risk_event with this dedupe_key already exists.

    Returns:
        bool: True if duplicate exists.
    """
    if dedupe_key is None:
        return False

    from models import RiskEvent
    return RiskEvent.query.filter_by(dedupe_key=dedupe_key).first() is not None


def _build_dedupe_key(policy, now):
    """Build a deduplication key for daily policies.

    Format: "{policy_id}:{YYYY-MM-DD}"
    Ensures at most one event per policy per calendar day.
    """
    if policy.policy_type == 'daily_spend_cap':
        return f"{policy.id}:{now.date().isoformat()}"
    # Future policy types may use different dedupe strategies
    return f"{policy.id}:{now.date().isoformat()}"


def _create_risk_event(policy, breach_value, threshold_value, dedupe_key, now):
    """Create a pending risk_event and commit."""
    from models import db, RiskEvent

    event = RiskEvent(
        uid=str(uuid.uuid4()),
        policy_id=policy.id,
        workspace_id=policy.workspace_id,
        agent_id=policy.agent_id,
        policy_type=policy.policy_type,
        breach_value=breach_value,
        threshold_value=threshold_value,
        action_type=policy.action_type,
        status='pending',
        evaluated_at=now,
        dedupe_key=dedupe_key,
    )
    db.session.add(event)
    db.session.commit()
    return event
