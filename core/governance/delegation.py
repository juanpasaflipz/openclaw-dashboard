"""
Delegation grant management — time-bound, bounded agent autonomy.

Agents use active grants to self-apply policy changes within the
pre-approved envelope. Every operation is validated against:
  1. Grant validity (active, within time window).
  2. Grant envelope (allowed_changes constraints).
  3. Workspace immutable boundaries.

Grants do NOT stack — each apply is validated against the specific grant's
envelope independently. The resulting policy value must satisfy both the
grant and workspace boundaries.
"""
from datetime import datetime
from decimal import Decimal


def get_active_grants(workspace_id, agent_id=None):
    """Return active, non-expired delegation grants.

    Args:
        workspace_id: Required workspace scope.
        agent_id: Optional filter by agent.

    Returns:
        list[DelegationGrant] ordered by valid_to ascending.
    """
    from models import DelegationGrant

    now = datetime.utcnow()
    q = DelegationGrant.query.filter(
        DelegationGrant.workspace_id == workspace_id,
        DelegationGrant.active == True,  # noqa: E712
        DelegationGrant.valid_from <= now,
        DelegationGrant.valid_to >= now,
    )
    if agent_id is not None:
        q = q.filter_by(agent_id=agent_id)

    return q.order_by(DelegationGrant.valid_to.asc()).all()


def apply_delegated_change(grant_id, workspace_id, agent_id, requested_change):
    """Agent applies a policy change using a delegation grant.

    Args:
        grant_id: The grant to use.
        workspace_id: Workspace scope (enforced).
        agent_id: The agent applying (must match grant).
        requested_change: dict with: policy_id, field, new_value.

    Returns:
        (dict, None) on success.
        (None, str) on failure.
    """
    from models import db, DelegationGrant, RiskPolicy, Agent
    from core.governance.boundaries import validate_against_boundaries
    from core.governance.governance_audit import log_governance_event

    # --- Validate agent ownership ---
    agent = Agent.query.filter_by(id=agent_id, user_id=workspace_id).first()
    if agent is None:
        return None, 'Agent not found or does not belong to workspace'

    # --- Load grant ---
    grant = DelegationGrant.query.filter_by(
        id=grant_id, workspace_id=workspace_id,
    ).first()
    if grant is None:
        return None, 'Grant not found'

    # --- Grant belongs to this agent ---
    if grant.agent_id != agent_id:
        return None, 'Grant does not belong to this agent'

    # --- Grant is active ---
    if not grant.active:
        return None, 'Grant is no longer active'

    # --- Grant is within time window ---
    now = datetime.utcnow()
    if now < grant.valid_from:
        return None, 'Grant is not yet valid'
    if now > grant.valid_to:
        # Auto-deactivate
        grant.active = False
        log_governance_event(
            workspace_id=workspace_id,
            event_type='grant_expired',
            details={'grant_id': grant.id, 'expired_at': now.isoformat()},
            agent_id=agent_id,
        )
        db.session.commit()
        return None, 'Grant has expired'

    # --- Validate requested_change structure ---
    if not isinstance(requested_change, dict):
        return None, 'requested_change must be a dict'

    policy_id = requested_change.get('policy_id')
    field = requested_change.get('field')
    new_value = requested_change.get('new_value')

    if policy_id is None or field is None or new_value is None:
        return None, 'requested_change must include policy_id, field, new_value'

    # --- Grant envelope: policy_id must match ---
    grant_policy_id = grant.allowed_changes.get('policy_id')
    if grant_policy_id is not None and int(grant_policy_id) != int(policy_id):
        return None, (
            f'Grant is for policy {grant_policy_id}, '
            f'not policy {policy_id}'
        )

    # --- Grant envelope: field must be in allowed fields ---
    grant_fields = grant.allowed_changes.get('fields', {})
    if field not in grant_fields:
        return None, f'Field "{field}" is not covered by this grant'

    # --- Grant envelope: value within constraints ---
    field_constraints = grant_fields[field]
    envelope_error = _check_envelope(field, new_value, field_constraints)
    if envelope_error:
        log_governance_event(
            workspace_id=workspace_id,
            event_type='boundary_violation',
            details={
                'grant_id': grant.id,
                'policy_id': policy_id,
                'field': field,
                'new_value': str(new_value),
                'error': envelope_error,
                'source': 'grant_envelope',
            },
            agent_id=agent_id,
        )
        db.session.commit()
        return None, f'Grant envelope violation: {envelope_error}'

    # --- Workspace boundary check ---
    valid, boundary_error = validate_against_boundaries(
        workspace_id, policy_id, field, new_value,
    )
    if not valid:
        log_governance_event(
            workspace_id=workspace_id,
            event_type='boundary_violation',
            details={
                'grant_id': grant.id,
                'policy_id': policy_id,
                'field': field,
                'new_value': str(new_value),
                'error': boundary_error,
                'source': 'workspace_boundary',
            },
            agent_id=agent_id,
        )
        db.session.commit()
        return None, f'Workspace boundary violation: {boundary_error}'

    # --- Load and mutate policy ---
    policy = RiskPolicy.query.filter_by(
        id=policy_id, workspace_id=workspace_id,
    ).first()
    if policy is None:
        return None, 'Policy not found'

    policy_before = policy.to_dict()

    if field == 'threshold_value':
        policy.threshold_value = Decimal(str(new_value))
    elif field == 'cooldown_minutes':
        policy.cooldown_minutes = int(new_value)
    elif field == 'action_type':
        policy.action_type = str(new_value)

    policy.updated_at = now

    policy_after = policy.to_dict()

    # --- Audit: grant used ---
    log_governance_event(
        workspace_id=workspace_id,
        event_type='grant_used',
        details={
            'grant_id': grant.id,
            'policy_id': policy_id,
            'field': field,
            'old_value': str(policy_before.get(field)),
            'new_value': str(new_value),
            'policy_before': policy_before,
            'policy_after': policy_after,
        },
        agent_id=agent_id,
    )

    # --- Audit: change applied ---
    log_governance_event(
        workspace_id=workspace_id,
        event_type='change_applied',
        details={
            'grant_id': grant.id,
            'policy_id': policy_id,
            'field': field,
            'old_value': str(policy_before.get(field)),
            'new_value': str(new_value),
            'policy_before': policy_before,
            'policy_after': policy_after,
            'source': 'delegation',
        },
        agent_id=agent_id,
    )

    db.session.commit()

    return {
        'grant_id': grant.id,
        'policy_id': policy_id,
        'field': field,
        'old_value': str(policy_before.get(field)),
        'new_value': str(new_value),
    }, None


def expire_grants():
    """Deactivate expired delegation grants.

    Called by cron. Sets active=False on grants whose valid_to has passed.

    Returns:
        int: Count of grants expired.
    """
    from models import db, DelegationGrant
    from core.governance.governance_audit import log_governance_event

    now = datetime.utcnow()
    expired = DelegationGrant.query.filter(
        DelegationGrant.active == True,  # noqa: E712
        DelegationGrant.valid_to < now,
    ).all()

    count = 0
    for grant in expired:
        grant.active = False
        log_governance_event(
            workspace_id=grant.workspace_id,
            event_type='grant_expired',
            details={
                'grant_id': grant.id,
                'valid_to': grant.valid_to.isoformat(),
                'expired_at': now.isoformat(),
            },
            agent_id=grant.agent_id,
        )
        count += 1

    if count > 0:
        db.session.commit()

    return count


def revoke_grant(grant_id, workspace_id, revoker_id):
    """Human revokes an active delegation grant.

    Args:
        grant_id: The grant to revoke.
        workspace_id: Workspace scope (enforced).
        revoker_id: The human revoking.

    Returns:
        (dict, None) on success.
        (None, str) on failure.
    """
    from models import db, DelegationGrant, User
    from core.governance.governance_audit import log_governance_event

    # --- Validate revoker ---
    revoker = User.query.get(revoker_id)
    if revoker is None:
        return None, 'Revoker not found'
    if revoker_id != workspace_id and not revoker.is_admin:
        return None, 'Only the workspace owner or an admin can revoke grants'

    # --- Load grant ---
    grant = DelegationGrant.query.filter_by(
        id=grant_id, workspace_id=workspace_id,
    ).first()
    if grant is None:
        return None, 'Grant not found'

    if not grant.active:
        return None, 'Grant is already inactive'

    # --- Revoke ---
    now = datetime.utcnow()
    grant.active = False
    grant.revoked_at = now
    grant.revoked_by = revoker_id

    log_governance_event(
        workspace_id=workspace_id,
        event_type='grant_revoked',
        details={
            'grant_id': grant.id,
            'revoked_by': revoker_id,
            'revoked_at': now.isoformat(),
        },
        agent_id=grant.agent_id,
        actor_id=revoker_id,
    )

    db.session.commit()

    return {
        'grant_id': grant.id,
        'status': 'revoked',
        'revoked_by': revoker_id,
    }, None


# ---------------------------------------------------------------------------
# Internal: envelope validation
# ---------------------------------------------------------------------------

def _check_envelope(field, new_value, constraints):
    """Check if new_value falls within the grant's field constraints.

    Args:
        field: The policy field.
        new_value: The proposed value.
        constraints: dict with either:
            min_value/max_value (for numeric fields), or
            allowed_values (for enum fields).

    Returns:
        None if valid, str error message if violated.
    """
    if 'min_value' in constraints or 'max_value' in constraints:
        return _check_numeric_envelope(field, new_value, constraints)

    if 'allowed_values' in constraints:
        allowed = constraints['allowed_values']
        if str(new_value) not in [str(v) for v in allowed]:
            return (
                f'Value "{new_value}" not in allowed values: {allowed}'
            )
        return None

    # No constraints defined — permissive (should not happen with proper grants)
    return None


def _check_numeric_envelope(field, new_value, constraints):
    """Check numeric value against min/max envelope."""
    try:
        val = Decimal(str(new_value))
    except Exception:
        return f'Invalid numeric value: {new_value}'

    min_val = constraints.get('min_value')
    max_val = constraints.get('max_value')

    if min_val is not None:
        if val < Decimal(str(min_val)):
            return (
                f'Value {val} is below grant minimum {min_val}'
            )

    if max_val is not None:
        if val > Decimal(str(max_val)):
            return (
                f'Value {val} exceeds grant maximum {max_val}'
            )

    return None
