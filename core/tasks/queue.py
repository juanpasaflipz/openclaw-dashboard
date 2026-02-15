"""
core.tasks.queue — Approval queue state transitions for AgentActions.

All DB writes happen here so routes stay thin.
"""
from __future__ import annotations

import json
from datetime import datetime

from models import db, AgentAction, Superpower
from core.tasks.executor import execute_action


def get_pending_actions(user_id: int) -> list[dict]:
    """Return all pending actions for a user, newest first."""
    actions = AgentAction.query.filter_by(
        user_id=user_id,
        status='pending',
    ).order_by(AgentAction.created_at.desc()).all()
    return [a.to_dict() for a in actions]


def approve_and_execute(action_id: int, user_id: int) -> tuple[dict | None, str | None, int]:
    """Approve a pending action, execute it, and persist the result.

    Returns:
        (action_dict, None, 200) on success
        (None, error_message, status_code) on failure
    """
    action = AgentAction.query.filter_by(
        id=action_id,
        user_id=user_id,
        status='pending',
    ).first()

    if not action:
        return None, 'Action not found or already processed', 404

    action.status = 'approved'
    action.approved_at = datetime.utcnow()

    try:
        result, error = execute_action(
            user_id=user_id,
            action_type=action.action_type,
            service_type=action.service_type,
            action_data_json=action.action_data,
        )
    except Exception as exc:
        action.status = 'failed'
        action.error_message = str(exc)
        db.session.commit()
        return None, 'An internal error occurred', 500

    if error:
        action.status = 'failed'
        action.error_message = error
        db.session.commit()
        return None, error, 400

    action.status = 'executed'
    action.executed_at = datetime.utcnow()
    action.result_data = json.dumps(result)

    _update_superpower_usage(user_id, action.service_type)

    db.session.commit()
    return action.to_dict(), None, 200


def reject_action(action_id: int, user_id: int) -> tuple[dict | None, str | None]:
    """Reject a pending action.

    Returns:
        (success_dict, None) on success or (None, error_message) on failure.
    """
    action = AgentAction.query.filter_by(
        id=action_id,
        user_id=user_id,
        status='pending',
    ).first()

    if not action:
        return None, 'Action not found or already processed'

    action.status = 'rejected'
    action.approved_at = datetime.utcnow()
    db.session.commit()

    return {'message': 'Action rejected'}, None


def create_action(user_id: int, agent_id: int | None, action_type: str,
                  service_type: str, action_data: dict,
                  ai_reasoning: str = '', ai_confidence: float = 0.0) -> AgentAction:
    """Create a new pending action in the approval queue."""
    action = AgentAction(
        user_id=user_id,
        agent_id=agent_id,
        action_type=action_type,
        service_type=service_type,
        status='pending',
        action_data=json.dumps(action_data),
        ai_reasoning=ai_reasoning,
        ai_confidence=ai_confidence,
    )
    db.session.add(action)
    db.session.commit()
    return action


# ---- internal helpers ----

def _update_superpower_usage(user_id: int, service_type: str) -> None:
    """Bump usage counter for the superpower after successful execution."""
    superpower = Superpower.query.filter_by(
        user_id=user_id,
        service_type=service_type,
    ).first()
    if superpower:
        superpower.usage_count = (superpower.usage_count or 0) + 1
        superpower.last_used = datetime.utcnow()
