"""
Governance audit log — append-only trail for all governance events.

Every governance state transition (request, approval, denial, application,
expiration, rollback, boundary violation) is logged here. Separate from
risk_audit_log which tracks automated interventions.
"""


def log_governance_event(workspace_id, event_type, details,
                         agent_id=None, actor_id=None):
    """Write a governance audit log entry.

    Args:
        workspace_id: Workspace scope.
        event_type: One of: request_submitted, request_expired,
                    request_approved, request_denied, change_applied,
                    change_rolled_back, grant_created, grant_expired,
                    grant_revoked, grant_used, boundary_violation.
        details: dict with event-specific data. Should include
                 policy_before/policy_after for mutation events.
        agent_id: The agent involved (may be None for system events).
        actor_id: The human who acted (may be None for agent/system events).

    Returns:
        GovernanceAuditLog instance.
    """
    from models import db, GovernanceAuditLog

    entry = GovernanceAuditLog(
        workspace_id=workspace_id,
        agent_id=agent_id,
        actor_id=actor_id,
        event_type=event_type,
        details=details,
    )
    db.session.add(entry)
    # Caller is responsible for commit (batched with request status update).
    return entry


def get_governance_trail(workspace_id, event_type=None, agent_id=None,
                         limit=100):
    """Query the governance audit trail for a workspace.

    Args:
        workspace_id: Required workspace scope.
        event_type: Optional filter by event type.
        agent_id: Optional filter by agent.
        limit: Max entries to return (default 100).

    Returns:
        list[GovernanceAuditLog] ordered by created_at descending.
    """
    from models import GovernanceAuditLog

    q = GovernanceAuditLog.query.filter_by(workspace_id=workspace_id)

    if event_type is not None:
        q = q.filter_by(event_type=event_type)

    if agent_id is not None:
        q = q.filter_by(agent_id=agent_id)

    return q.order_by(GovernanceAuditLog.created_at.desc()).limit(limit).all()
