"""
Governance hooks for the collaboration task system.

Called at task lifecycle transitions to integrate with the risk engine,
observability pipeline, and governance audit trail. All hooks are
best-effort — they never raise and never block the task operation.
"""
from datetime import datetime


# ---------------------------------------------------------------------------
# Pre-start check: validate agent health before allowing task execution
# ---------------------------------------------------------------------------

def pre_task_start(task):
    """Check the assigned agent's readiness before starting a task.

    Checks:
    1. Agent is_active (not paused by risk intervention)
    2. Active risk policies have not been breached (pending events)

    Returns:
        (ok: bool, reason: str | None)
        If ok is False, the caller should block the task with the reason.
    """
    try:
        from models import Agent, RiskEvent

        agent = Agent.query.get(task.assigned_to_agent_id)
        if not agent:
            return False, 'Assigned agent not found'

        if not agent.is_active:
            return False, 'Agent is paused by risk policy'

        # Check for pending (unresolved) risk events targeting this agent
        pending = RiskEvent.query.filter_by(
            agent_id=task.assigned_to_agent_id,
            workspace_id=task.workspace_id,
            status='pending',
        ).first()

        if pending:
            return False, f'Agent has pending risk event: {pending.policy_type}'

        return True, None

    except Exception as e:
        # Best-effort: if risk check fails, allow the task to proceed
        print(f"[collab] pre_task_start check failed: {e}")
        return True, None


# ---------------------------------------------------------------------------
# Post-start: emit observability event for task start
# ---------------------------------------------------------------------------

def on_task_started(task):
    """Emit an observability event when a task begins execution."""
    try:
        from core.observability.ingestion import emit_event

        emit_event(
            user_id=task.workspace_id,
            event_type='action_started',
            status='info',
            agent_id=task.assigned_to_agent_id,
            payload={
                'source': 'collaboration',
                'task_id': task.id,
                'task_title': task.title,
            },
            dedupe_key=f"collab:start:{task.id}",
        )
    except Exception as e:
        print(f"[collab] on_task_started emit failed: {e}")


# ---------------------------------------------------------------------------
# Post-complete: emit observability event and log governance audit
# ---------------------------------------------------------------------------

def on_task_completed(task, output=None):
    """Emit observability event when a task completes successfully."""
    try:
        from core.observability.ingestion import emit_event

        payload = {
            'source': 'collaboration',
            'task_id': task.id,
            'task_title': task.title,
        }
        if output:
            # Include a summary (truncated) for observability
            payload['output_summary'] = str(output)[:500]

        emit_event(
            user_id=task.workspace_id,
            event_type='action_finished',
            status='success',
            agent_id=task.assigned_to_agent_id,
            payload=payload,
            dedupe_key=f"collab:complete:{task.id}",
        )
    except Exception as e:
        print(f"[collab] on_task_completed emit failed: {e}")


# ---------------------------------------------------------------------------
# Post-fail: emit observability error event
# ---------------------------------------------------------------------------

def on_task_failed(task, reason=None):
    """Emit observability error event when a task fails."""
    try:
        from core.observability.ingestion import emit_event

        emit_event(
            user_id=task.workspace_id,
            event_type='error',
            status='error',
            agent_id=task.assigned_to_agent_id,
            payload={
                'source': 'collaboration',
                'task_id': task.id,
                'task_title': task.title,
                'reason': reason or 'unknown',
            },
            dedupe_key=f"collab:fail:{task.id}",
        )
    except Exception as e:
        print(f"[collab] on_task_failed emit failed: {e}")


# ---------------------------------------------------------------------------
# Task blocked: log governance event when risk check blocks a task
# ---------------------------------------------------------------------------

def on_task_blocked_by_risk(task, reason):
    """Log a governance audit event when a task is blocked by risk policy."""
    try:
        from core.governance.governance_audit import log_governance_event
        from models import db

        log_governance_event(
            workspace_id=task.workspace_id,
            event_type='task_blocked',
            details={
                'task_id': task.id,
                'task_title': task.title,
                'assigned_agent_id': task.assigned_to_agent_id,
                'reason': reason,
            },
            agent_id=task.assigned_to_agent_id,
        )
        db.session.commit()
    except Exception as e:
        print(f"[collab] on_task_blocked_by_risk audit failed: {e}")


# ---------------------------------------------------------------------------
# Escalation: log governance event when a task is escalated to supervisor
# ---------------------------------------------------------------------------

def on_task_escalated(task, from_agent_id, to_agent_id):
    """Log a governance audit event when a task escalates to a supervisor."""
    try:
        from core.governance.governance_audit import log_governance_event
        from models import db

        log_governance_event(
            workspace_id=task.workspace_id,
            event_type='task_escalated',
            details={
                'task_id': task.id,
                'task_title': task.title,
                'from_agent_id': from_agent_id,
                'to_agent_id': to_agent_id,
            },
            agent_id=to_agent_id,
        )
        db.session.commit()
    except Exception as e:
        print(f"[collab] on_task_escalated audit failed: {e}")


# ---------------------------------------------------------------------------
# Reassignment: log governance event on task reassignment
# ---------------------------------------------------------------------------

def on_task_reassigned(task, from_agent_id, to_agent_id):
    """Log a governance audit event when a task is reassigned."""
    try:
        from core.governance.governance_audit import log_governance_event
        from models import db

        log_governance_event(
            workspace_id=task.workspace_id,
            event_type='task_reassigned',
            details={
                'task_id': task.id,
                'task_title': task.title,
                'from_agent_id': from_agent_id,
                'to_agent_id': to_agent_id,
            },
            agent_id=to_agent_id,
        )
        db.session.commit()
    except Exception as e:
        print(f"[collab] on_task_reassigned audit failed: {e}")
