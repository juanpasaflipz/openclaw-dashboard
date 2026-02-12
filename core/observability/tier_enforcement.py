"""
Tier enforcement — workspace limit checks for the observability layer.

All limits are read from the WorkspaceTier DB row for the workspace.
If no row exists, FREE tier defaults are applied (from WorkspaceTier.TIER_DEFAULTS).

Tier config is cached in-memory per workspace with a 60-second TTL to avoid
hitting the DB on every request.
"""
import time
from datetime import datetime, timedelta

_tier_cache = {}       # {workspace_id: (WorkspaceTier-like dict, timestamp)}
_TIER_CACHE_TTL = 60   # seconds


def get_workspace_tier(workspace_id):
    """Return the tier config dict for a workspace. Cached with 60s TTL.

    Returns a dict with all tier fields (agent_limit, retention_days, etc.).
    Falls back to FREE defaults if no DB row exists.
    """
    now = time.time()
    cached = _tier_cache.get(workspace_id)
    if cached and (now - cached[1]) < _TIER_CACHE_TTL:
        return cached[0]

    from models import WorkspaceTier, db

    row = WorkspaceTier.query.filter_by(workspace_id=workspace_id).first()
    if row:
        tier_dict = row.to_dict()
    else:
        # No row → free tier defaults
        defaults = WorkspaceTier.TIER_DEFAULTS['free'].copy()
        defaults['workspace_id'] = workspace_id
        defaults['tier_name'] = 'free'
        defaults['updated_at'] = None
        tier_dict = defaults

    _tier_cache[workspace_id] = (tier_dict, now)
    return tier_dict


def invalidate_tier_cache(workspace_id=None):
    """Clear the tier cache. If workspace_id is given, clear only that entry."""
    if workspace_id is not None:
        _tier_cache.pop(workspace_id, None)
    else:
        _tier_cache.clear()


# ---------------------------------------------------------------------------
# Individual limit checks — return (allowed: bool, error_message: str | None)
# ---------------------------------------------------------------------------

def check_agent_limit(workspace_id):
    """Check if the workspace can monitor more agents.

    Returns (True, None) if under limit, (False, message) if at/over limit.
    """
    tier = get_workspace_tier(workspace_id)
    limit = tier['agent_limit']

    from models import ObsEvent, db
    from sqlalchemy import func

    count = (
        db.session.query(func.count(func.distinct(ObsEvent.agent_id)))
        .filter(ObsEvent.user_id == workspace_id, ObsEvent.agent_id.isnot(None))
        .scalar()
    ) or 0

    if count >= limit:
        return False, (
            f"Agent monitoring limit reached ({limit}). "
            f"Current tier: {tier['tier_name']}. Upgrade to monitor more agents."
        )
    return True, None


def check_agent_allowed(workspace_id, agent_id):
    """Check if a specific agent_id is within the monitored agent set.

    If the agent is already known (has prior events), it's always allowed.
    If it's new, check_agent_limit applies.
    """
    if agent_id is None:
        return True, None

    from models import ObsEvent
    existing = ObsEvent.query.filter_by(
        user_id=workspace_id, agent_id=agent_id
    ).first()
    if existing:
        return True, None

    # New agent — check limit
    return check_agent_limit(workspace_id)


def check_alert_rule_limit(workspace_id):
    """Check if the workspace can create more alert rules.

    Returns (True, None) if under limit, (False, message) if at/over limit.
    """
    tier = get_workspace_tier(workspace_id)
    limit = tier['alert_rule_limit']

    from models import ObsAlertRule
    count = ObsAlertRule.query.filter_by(user_id=workspace_id).count()

    if count >= limit:
        if limit == 0:
            msg = (
                f"Alert rules are not available on the {tier['tier_name']} tier. "
                f"Upgrade to create alert rules."
            )
        else:
            msg = (
                f"Alert rule limit reached ({limit}). "
                f"Current tier: {tier['tier_name']}. Upgrade for more alert rules."
            )
        return False, msg
    return True, None


def get_retention_cutoff(workspace_id):
    """Return the earliest allowed datetime for this workspace's retention window.

    Queries outside this window should be filtered.
    """
    tier = get_workspace_tier(workspace_id)
    days = tier['retention_days']
    return datetime.utcnow() - timedelta(days=days)


def clamp_date_range(workspace_id, from_date, to_date):
    """Clamp a (from_date, to_date) range to the workspace's retention window.

    Returns (clamped_from, clamped_to). Dates are date objects.
    If from_date is before the retention cutoff, it's moved forward.
    """
    tier = get_workspace_tier(workspace_id)
    cutoff = (datetime.utcnow() - timedelta(days=tier['retention_days'])).date()

    if from_date is None or from_date < cutoff:
        from_date = cutoff
    if to_date is None:
        to_date = datetime.utcnow().date()

    return from_date, to_date


def get_health_history_cutoff(workspace_id):
    """Return the earliest allowed date for health score history.

    Returns a date object. 0 days means today only.
    """
    tier = get_workspace_tier(workspace_id)
    days = tier['health_history_days']
    return (datetime.utcnow() - timedelta(days=days)).date()


def check_anomaly_detection(workspace_id):
    """Check if anomaly detection is enabled for this workspace."""
    tier = get_workspace_tier(workspace_id)
    return tier['anomaly_detection_enabled']


def check_slack_notifications(workspace_id):
    """Check if Slack notifications are enabled for this workspace."""
    tier = get_workspace_tier(workspace_id)
    return tier['slack_notifications_enabled']


def check_api_key_limit(workspace_id):
    """Check if the workspace can create more API keys.

    Returns (True, None) if under limit, (False, message) if at/over limit.
    """
    tier = get_workspace_tier(workspace_id)
    limit = tier['max_api_keys']

    from models import ObsApiKey
    count = ObsApiKey.query.filter_by(user_id=workspace_id, is_active=True).count()

    if count >= limit:
        return False, (
            f"API key limit reached ({limit}). "
            f"Current tier: {tier['tier_name']}. Upgrade for more API keys."
        )
    return True, None


def get_max_batch_size(workspace_id):
    """Return the max batch size for event ingestion."""
    tier = get_workspace_tier(workspace_id)
    return tier['max_batch_size']


def verify_workspace_limits(workspace_id, check='all'):
    """Verify workspace limits for a specific check or all checks.

    Args:
        workspace_id: The workspace (user) ID.
        check: One of 'agent', 'alert_rule', 'api_key', 'all', or a specific agent_id (int).

    Returns:
        (True, None) if all checks pass.
        (False, error_message) on first failure.
    """
    if isinstance(check, int):
        # check is an agent_id
        return check_agent_allowed(workspace_id, check)

    checks = {
        'agent': lambda: check_agent_limit(workspace_id),
        'alert_rule': lambda: check_alert_rule_limit(workspace_id),
        'api_key': lambda: check_api_key_limit(workspace_id),
    }

    if check == 'all':
        for name, fn in checks.items():
            ok, msg = fn()
            if not ok:
                return False, msg
        return True, None

    fn = checks.get(check)
    if fn is None:
        return True, None
    return fn()
