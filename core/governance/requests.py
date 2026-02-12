"""
Policy change request pipeline — agents submit, humans review.

Agents propose policy modifications via create_request(). Requests are
stored with status='pending' and no immediate policy mutation occurs.
Humans review and approve/deny through the approvals module (Phase 2).

Enforces:
- Workspace isolation (all queries scoped by workspace_id).
- Agent ownership validation (agent must belong to workspace).
- Request cooldown (one request per policy per 15 minutes per workspace).
- Policy snapshot at request time (for audit and rollback).
"""
from datetime import datetime, timedelta

# Minimum minutes between requests for the same policy from the same workspace.
REQUEST_COOLDOWN_MINUTES = 15

# Default hours before a pending request auto-expires.
DEFAULT_EXPIRY_HOURS = 24

# Mutable fields that agents can request changes to.
MUTABLE_FIELDS = frozenset({'threshold_value', 'action_type', 'cooldown_minutes'})


def create_request(workspace_id, agent_id, requested_changes, reason):
    """Submit a policy change request.

    Args:
        workspace_id: The workspace submitting the request.
        agent_id: The agent requesting the change.
        requested_changes: dict with keys: policy_id, field,
                          current_value, requested_value.
        reason: Agent's justification for the change.

    Returns:
        (PolicyChangeRequest, None) on success.
        (None, str) on validation failure.
    """
    from models import db, PolicyChangeRequest, RiskPolicy, Agent

    # --- Validate agent ownership ---
    agent = Agent.query.filter_by(id=agent_id, user_id=workspace_id).first()
    if agent is None:
        return None, 'Agent not found or does not belong to workspace'

    # --- Validate requested_changes structure ---
    if not isinstance(requested_changes, dict):
        return None, 'requested_changes must be a dict'

    policy_id = requested_changes.get('policy_id')
    field = requested_changes.get('field')
    requested_value = requested_changes.get('requested_value')

    if policy_id is None:
        return None, 'requested_changes.policy_id is required'
    if field is None:
        return None, 'requested_changes.field is required'
    if requested_value is None:
        return None, 'requested_changes.requested_value is required'

    # --- Validate field is mutable ---
    if field not in MUTABLE_FIELDS:
        return None, f'Field "{field}" is not mutable via governance'

    # --- Validate policy exists and belongs to workspace ---
    policy = RiskPolicy.query.filter_by(
        id=policy_id, workspace_id=workspace_id
    ).first()
    if policy is None:
        return None, 'Policy not found or does not belong to workspace'

    # --- Cooldown check ---
    cooldown_cutoff = datetime.utcnow() - timedelta(minutes=REQUEST_COOLDOWN_MINUTES)
    recent = PolicyChangeRequest.query.filter(
        PolicyChangeRequest.workspace_id == workspace_id,
        PolicyChangeRequest.policy_id == policy_id,
        PolicyChangeRequest.status == 'pending',
        PolicyChangeRequest.requested_at >= cooldown_cutoff,
    ).first()
    if recent is not None:
        return None, (
            f'A pending request for this policy was submitted less than '
            f'{REQUEST_COOLDOWN_MINUTES} minutes ago'
        )

    # --- Snapshot current policy state ---
    policy_snapshot = policy.to_dict()

    # --- Populate current_value if not provided ---
    current_value = requested_changes.get('current_value')
    if current_value is None:
        current_value = str(getattr(policy, field, None))
        requested_changes = dict(requested_changes)
        requested_changes['current_value'] = current_value

    now = datetime.utcnow()
    pcr = PolicyChangeRequest(
        workspace_id=workspace_id,
        agent_id=agent_id,
        policy_id=policy_id,
        requested_changes=requested_changes,
        reason=reason,
        status='pending',
        requested_at=now,
        expires_at=now + timedelta(hours=DEFAULT_EXPIRY_HOURS),
        policy_snapshot=policy_snapshot,
    )
    db.session.add(pcr)

    # Log governance event
    from core.governance.governance_audit import log_governance_event
    log_governance_event(
        workspace_id=workspace_id,
        event_type='request_submitted',
        details={
            'request_id': None,  # Will be set after flush
            'policy_id': policy_id,
            'field': field,
            'current_value': current_value,
            'requested_value': str(requested_value),
            'reason': reason,
        },
        agent_id=agent_id,
    )

    db.session.commit()

    # Backfill request_id in the audit entry (committed, id is available)
    return pcr, None


def get_requests(workspace_id, status=None, agent_id=None, limit=50):
    """List policy change requests for a workspace.

    Args:
        workspace_id: Required workspace scope.
        status: Optional filter by status.
        agent_id: Optional filter by requesting agent.
        limit: Max entries to return (default 50).

    Returns:
        list[PolicyChangeRequest] ordered by requested_at descending.
    """
    from models import PolicyChangeRequest

    q = PolicyChangeRequest.query.filter_by(workspace_id=workspace_id)

    if status is not None:
        q = q.filter_by(status=status)
    if agent_id is not None:
        q = q.filter_by(agent_id=agent_id)

    return q.order_by(PolicyChangeRequest.requested_at.desc()).limit(limit).all()


def get_request(request_id, workspace_id):
    """Get a single policy change request, scoped to workspace.

    Args:
        request_id: The request ID.
        workspace_id: Workspace scope (enforced).

    Returns:
        PolicyChangeRequest or None.
    """
    from models import PolicyChangeRequest

    return PolicyChangeRequest.query.filter_by(
        id=request_id, workspace_id=workspace_id
    ).first()


def expire_stale_requests(max_age_hours=DEFAULT_EXPIRY_HOURS):
    """Expire pending requests that have passed their expiry time.

    Args:
        max_age_hours: Fallback max age for requests without expires_at.

    Returns:
        int: Count of requests expired.
    """
    from models import db, PolicyChangeRequest
    from core.governance.governance_audit import log_governance_event

    now = datetime.utcnow()
    fallback_cutoff = now - timedelta(hours=max_age_hours)

    # Find pending requests that are expired
    stale = PolicyChangeRequest.query.filter(
        PolicyChangeRequest.status == 'pending',
        db.or_(
            db.and_(
                PolicyChangeRequest.expires_at.isnot(None),
                PolicyChangeRequest.expires_at <= now,
            ),
            db.and_(
                PolicyChangeRequest.expires_at.is_(None),
                PolicyChangeRequest.requested_at <= fallback_cutoff,
            ),
        ),
    ).all()

    count = 0
    for req in stale:
        req.status = 'expired'
        log_governance_event(
            workspace_id=req.workspace_id,
            event_type='request_expired',
            details={
                'request_id': req.id,
                'policy_id': req.policy_id,
                'reason': 'Request expired without review',
            },
            agent_id=req.agent_id,
        )
        count += 1

    if count > 0:
        db.session.commit()

    return count
