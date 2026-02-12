"""
Immutable workspace boundaries — hard limits that no delegation can exceed.

Boundaries are derived from workspace tier + system constants. They apply
to all mutation paths: one-time apply, delegation grant creation, and
agent self-apply via delegation.

No policy value can exceed these limits, regardless of who requests or
approves the change.
"""
from decimal import Decimal

# ---------------------------------------------------------------------------
# System constants (never changeable at runtime)
# ---------------------------------------------------------------------------

SYSTEM_BOUNDARIES = {
    'min_cooldown_minutes': 30,        # No policy can have < 30 min cooldown
    'max_policies_per_workspace': 50,  # Hard cap on policy count
}

# Action severity ordering (higher index = more severe).
# A governance change can only escalate or maintain severity, never de-escalate.
ACTION_SEVERITY = {
    'alert_only': 0,
    'throttle': 1,
    'model_downgrade': 2,
    'pause_agent': 3,
}

# ---------------------------------------------------------------------------
# Tier-derived boundaries
# ---------------------------------------------------------------------------

TIER_BOUNDARIES = {
    'free':       {'max_daily_spend_cap': Decimal('50.00')},
    'production': {'max_daily_spend_cap': Decimal('200.00')},
    'pro':        {'max_daily_spend_cap': Decimal('500.00')},
    'agency':     {'max_daily_spend_cap': Decimal('2000.00')},
}


def get_workspace_boundaries(workspace_id):
    """Return the full boundary set for a workspace.

    Combines system constants with tier-derived limits.

    Args:
        workspace_id: The workspace to check.

    Returns:
        dict with all boundary fields.
    """
    from core.observability.tier_enforcement import get_workspace_tier

    tier = get_workspace_tier(workspace_id)
    tier_name = tier.get('tier_name', 'free')

    tier_bounds = TIER_BOUNDARIES.get(tier_name, TIER_BOUNDARIES['free']).copy()
    tier_bounds.update(SYSTEM_BOUNDARIES)
    tier_bounds['tier_name'] = tier_name

    return tier_bounds


def validate_against_boundaries(workspace_id, policy_id, field, new_value):
    """Validate a proposed policy change against immutable boundaries.

    Args:
        workspace_id: The workspace scope.
        policy_id: The policy being changed.
        field: The field being changed.
        new_value: The proposed new value (as string for threshold, int for
                   cooldown, string for action_type).

    Returns:
        (True, None) if valid.
        (False, str) if boundary violated.
    """
    boundaries = get_workspace_boundaries(workspace_id)

    if field == 'threshold_value':
        return _validate_threshold(workspace_id, policy_id, new_value, boundaries)
    elif field == 'cooldown_minutes':
        return _validate_cooldown(new_value, boundaries)
    elif field == 'action_type':
        return _validate_action_type(policy_id, new_value)

    return True, None


def _validate_threshold(workspace_id, policy_id, new_value, boundaries):
    """Validate a threshold_value change against tier boundaries."""
    from models import RiskPolicy

    policy = RiskPolicy.query.filter_by(
        id=policy_id, workspace_id=workspace_id
    ).first()
    if policy is None:
        return False, 'Policy not found'

    try:
        new_threshold = Decimal(str(new_value))
    except Exception:
        return False, f'Invalid threshold value: {new_value}'

    if new_threshold < Decimal('0'):
        return False, 'Threshold value cannot be negative'

    # Check tier-specific cap based on policy type
    boundary_key = f'max_{policy.policy_type}'
    max_value = boundaries.get(boundary_key)
    if max_value is not None and new_threshold > max_value:
        return False, (
            f'Threshold {new_threshold} exceeds workspace boundary '
            f'{max_value} for {policy.policy_type} '
            f'(tier: {boundaries.get("tier_name", "unknown")})'
        )

    return True, None


def _validate_cooldown(new_value, boundaries):
    """Validate a cooldown_minutes change against minimum."""
    try:
        cooldown = int(new_value)
    except (ValueError, TypeError):
        return False, f'Invalid cooldown value: {new_value}'

    min_cooldown = boundaries.get('min_cooldown_minutes', 30)
    if cooldown < min_cooldown:
        return False, (
            f'Cooldown {cooldown} minutes is below minimum '
            f'{min_cooldown} minutes'
        )

    return True, None


def _validate_action_type(policy_id, new_value):
    """Validate an action_type change: can only escalate, never de-escalate."""
    from models import RiskPolicy

    if new_value not in ACTION_SEVERITY:
        return False, f'Unknown action_type: {new_value}'

    policy = RiskPolicy.query.get(policy_id)
    if policy is None:
        return False, 'Policy not found'

    current_severity = ACTION_SEVERITY.get(policy.action_type, 0)
    new_severity = ACTION_SEVERITY.get(new_value, 0)

    if new_severity < current_severity:
        return False, (
            f'Cannot de-escalate action from {policy.action_type} '
            f'to {new_value}. Actions can only escalate.'
        )

    return True, None
