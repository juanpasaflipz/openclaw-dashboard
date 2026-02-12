"""
Policy rollback — restore a policy to its pre-change state.

Every policy mutation via the governance pipeline stores a `policy_before`
snapshot in the governance audit log. Rollback loads that snapshot and
restores the policy, subject to boundary re-validation (the workspace
tier may have changed since the original change).

Rollbacks are themselves audited and reversible: rolling back a rollback
restores the state that existed before the rollback was applied.
"""
from datetime import datetime
from decimal import Decimal


def rollback_change(audit_entry_id, workspace_id, actor_id):
    """Rollback a policy change to its pre-change state.

    Args:
        audit_entry_id: The governance_audit_log entry ID whose
                        ``policy_before`` snapshot will be restored.
        workspace_id: Workspace scope (enforced).
        actor_id: The human initiating the rollback.

    Returns:
        (dict, None) on success — rollback details.
        (None, str) on failure — error message.
    """
    from models import db, GovernanceAuditLog, RiskPolicy, User
    from core.governance.boundaries import validate_against_boundaries
    from core.governance.governance_audit import log_governance_event

    # --- Validate actor ---
    actor = User.query.get(actor_id)
    if actor is None:
        return None, 'Actor not found'
    if actor_id != workspace_id and not actor.is_admin:
        return None, 'Only the workspace owner or an admin can rollback changes'

    # --- Load audit entry ---
    entry = GovernanceAuditLog.query.filter_by(
        id=audit_entry_id, workspace_id=workspace_id,
    ).first()
    if entry is None:
        return None, 'Audit entry not found'

    # --- Must be a mutation event ---
    if entry.event_type not in ('change_applied', 'change_rolled_back'):
        return None, (
            f'Cannot rollback event type "{entry.event_type}". '
            f'Only change_applied and change_rolled_back events can be rolled back.'
        )

    details = entry.details or {}
    policy_before = details.get('policy_before')
    if policy_before is None:
        return None, 'Audit entry does not contain a policy_before snapshot'

    # --- Resolve policy ---
    policy_id = details.get('policy_id') or policy_before.get('id')
    if policy_id is None:
        return None, 'Cannot determine policy_id from audit entry'

    policy = RiskPolicy.query.filter_by(
        id=policy_id, workspace_id=workspace_id,
    ).first()
    if policy is None:
        return None, 'Policy not found or does not belong to workspace'

    # --- Snapshot current state (before rollback) ---
    policy_current = policy.to_dict()

    # --- Determine which fields to restore ---
    # We restore the three mutable fields from the snapshot.
    restorable_fields = {
        'threshold_value': policy_before.get('threshold_value'),
        'cooldown_minutes': policy_before.get('cooldown_minutes'),
        'action_type': policy_before.get('action_type'),
    }

    # --- Boundary re-validation for each field being changed ---
    for field, snapshot_value in restorable_fields.items():
        if snapshot_value is None:
            continue

        # Only validate if the value is actually changing
        current_val = str(getattr(policy, field, None))
        if current_val == str(snapshot_value):
            continue

        valid, boundary_error = validate_against_boundaries(
            workspace_id, policy_id, field, snapshot_value,
        )
        if not valid:
            log_governance_event(
                workspace_id=workspace_id,
                event_type='boundary_violation',
                details={
                    'audit_entry_id': audit_entry_id,
                    'policy_id': policy_id,
                    'field': field,
                    'attempted_value': str(snapshot_value),
                    'error': boundary_error,
                    'source': 'rollback',
                },
                actor_id=actor_id,
            )
            db.session.commit()
            return None, (
                f'Rollback blocked: restoring {field} to {snapshot_value} '
                f'would violate current boundaries: {boundary_error}'
            )

    # --- Apply rollback ---
    now = datetime.utcnow()

    if restorable_fields.get('threshold_value') is not None:
        policy.threshold_value = Decimal(str(restorable_fields['threshold_value']))
    if restorable_fields.get('cooldown_minutes') is not None:
        policy.cooldown_minutes = int(restorable_fields['cooldown_minutes'])
    if restorable_fields.get('action_type') is not None:
        policy.action_type = str(restorable_fields['action_type'])

    policy.updated_at = now

    # --- Snapshot after rollback ---
    policy_after = policy.to_dict()

    # --- Audit: rollback ---
    log_governance_event(
        workspace_id=workspace_id,
        event_type='change_rolled_back',
        details={
            'rolled_back_entry_id': audit_entry_id,
            'policy_id': policy_id,
            'policy_before': policy_current,   # state before rollback
            'policy_after': policy_after,       # state after rollback (restored)
            'restored_from': 'policy_before snapshot of entry '
                             f'{audit_entry_id}',
        },
        agent_id=entry.agent_id,
        actor_id=actor_id,
    )

    db.session.commit()

    return {
        'audit_entry_id': audit_entry_id,
        'policy_id': policy_id,
        'policy_before_rollback': policy_current,
        'policy_after_rollback': policy_after,
    }, None
