"""
Audit log — append-only trail for all risk interventions.

Every intervention writes a RiskAuditLog entry with before/after state snapshots.
This module provides write and query helpers.
"""


def log_intervention(event_id, workspace_id, agent_id, action_type,
                     previous_state, new_state, result, error_message=None):
    """Write an audit log entry for an intervention.

    Args:
        event_id: The RiskEvent that triggered this intervention.
        workspace_id: Workspace scope.
        agent_id: Target agent (may be None for workspace-wide).
        action_type: The action performed.
        previous_state: dict snapshot of state before intervention.
        new_state: dict snapshot of state after intervention.
        result: 'success', 'failed', or 'skipped'.
        error_message: Optional error detail on failure.

    Returns:
        RiskAuditLog instance.
    """
    from models import db, RiskAuditLog

    entry = RiskAuditLog(
        event_id=event_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        action_type=action_type,
        previous_state=previous_state,
        new_state=new_state,
        result=result,
        error_message=error_message,
    )
    db.session.add(entry)
    # Caller is responsible for commit (batched with event status update).
    return entry


def get_audit_trail(workspace_id, policy_id=None, agent_id=None, limit=100):
    """Query the audit trail for a workspace.

    Args:
        workspace_id: Required workspace scope.
        policy_id: Optional filter by originating policy.
        agent_id: Optional filter by target agent.
        limit: Max entries to return (default 100).

    Returns:
        list[RiskAuditLog] ordered by created_at descending.
    """
    from models import RiskAuditLog, RiskEvent

    q = RiskAuditLog.query.filter_by(workspace_id=workspace_id)

    if agent_id is not None:
        q = q.filter_by(agent_id=agent_id)

    if policy_id is not None:
        # Join through event to filter by policy
        q = q.join(RiskEvent, RiskAuditLog.event_id == RiskEvent.id)
        q = q.filter(RiskEvent.policy_id == policy_id)

    return q.order_by(RiskAuditLog.created_at.desc()).limit(limit).all()
