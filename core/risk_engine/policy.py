"""
Policy layer — CRUD helpers and constants for risk policies.

Does NOT evaluate or enforce policies; that's evaluator.py / interventions.py.
"""
from datetime import datetime

VALID_POLICY_TYPES = frozenset({'daily_spend_cap', 'error_rate_cap', 'token_rate_cap'})
VALID_ACTION_TYPES = frozenset({'alert_only', 'throttle', 'model_downgrade', 'pause_agent'})


def get_active_policies(workspace_id=None):
    """Return all enabled risk policies, optionally filtered by workspace.

    Args:
        workspace_id: If provided, return policies for this workspace only.
                      If None, return all enabled policies across all workspaces.

    Returns:
        list[RiskPolicy]
    """
    from models import RiskPolicy

    q = RiskPolicy.query.filter_by(is_enabled=True)
    if workspace_id is not None:
        q = q.filter_by(workspace_id=workspace_id)
    return q.all()


def get_policy(policy_id, workspace_id=None):
    """Return a single policy by ID, optionally scoped to a workspace.

    Args:
        policy_id: The policy ID.
        workspace_id: If provided, verify the policy belongs to this workspace.

    Returns:
        RiskPolicy or None
    """
    from models import RiskPolicy

    q = RiskPolicy.query.filter_by(id=policy_id)
    if workspace_id is not None:
        q = q.filter_by(workspace_id=workspace_id)
    return q.first()
