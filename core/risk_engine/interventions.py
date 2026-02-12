"""
Intervention executor — process pending risk events and apply actions.

Handles each action_type: alert_only, throttle, model_downgrade, pause_agent.
All actions are reversible: a before/after snapshot is written to the audit log.
Duplicate execution is prevented by checking event status before processing.
"""
from datetime import datetime

from core.risk_engine.audit_log import log_intervention

# Model to downgrade to when model_downgrade is triggered.
# Maps provider to a cheaper model. Extensible.
_DOWNGRADE_TARGETS = {
    'openai': 'gpt-4o-mini',
    'anthropic': 'claude-haiku-4-5-20251001',
    'google': 'gemini-2.0-flash',
}
_DEFAULT_DOWNGRADE_MODEL = 'gpt-4o-mini'


def execute_pending_events(max_events=50):
    """Process pending risk events and execute their interventions.

    Args:
        max_events: Maximum number of events to process in one call.

    Returns:
        int: Count of events successfully executed.
    """
    from models import db, RiskEvent

    pending = (
        RiskEvent.query
        .filter_by(status='pending')
        .order_by(RiskEvent.evaluated_at.asc())
        .limit(max_events)
        .all()
    )

    executed_count = 0
    for event in pending:
        try:
            _process_event(event)
            if event.status == 'executed':
                executed_count += 1
        except Exception as e:
            db.session.rollback()
            print(f"[risk] executor failed event={event.id}: {e}")
            _mark_failed(event, str(e))

    return executed_count


def _process_event(event):
    """Process a single pending risk event."""
    from models import db

    # Guard: re-check status to prevent duplicate execution
    if event.status != 'pending':
        return

    handler = _ACTION_HANDLERS.get(event.action_type)
    if handler is None:
        _mark_skipped(event, f"Unknown action_type: {event.action_type}")
        return

    result = handler(event)

    # Handler may have already set status to 'skipped' or 'failed'
    if event.status == 'pending':
        event.status = 'executed'
        event.executed_at = datetime.utcnow()
        event.execution_result = result
        db.session.commit()


def _execute_alert_only(event):
    """Dispatch a notification without modifying agent state."""
    from models import db
    from core.observability.notifications import dispatch_alert_notification

    message = (
        f"[Risk Policy] {event.policy_type}: "
        f"${event.breach_value:.4f} exceeds ${event.threshold_value:.4f} threshold"
    )
    if event.agent_id:
        message += f" (agent #{event.agent_id})"

    dispatch_result = dispatch_alert_notification(message)

    log_intervention(
        event_id=event.id,
        workspace_id=event.workspace_id,
        agent_id=event.agent_id,
        action_type='alert_only',
        previous_state={},
        new_state={},
        result='success',
    )

    return {'action': 'alert_only', 'notification': dispatch_result}


def _execute_pause_agent(event):
    """Pause an agent by setting is_active=False."""
    from models import db, Agent

    if event.agent_id is None:
        log_intervention(
            event_id=event.id,
            workspace_id=event.workspace_id,
            agent_id=None,
            action_type='pause_agent',
            previous_state={},
            new_state={},
            result='skipped',
            error_message='No agent_id on event; cannot pause workspace-wide',
        )
        _mark_skipped(event, 'No agent_id; cannot pause workspace-wide')
        return {'action': 'pause_agent', 'skipped': True, 'reason': 'no agent_id'}

    agent = Agent.query.filter_by(
        id=event.agent_id, user_id=event.workspace_id
    ).first()

    if agent is None:
        log_intervention(
            event_id=event.id,
            workspace_id=event.workspace_id,
            agent_id=event.agent_id,
            action_type='pause_agent',
            previous_state={},
            new_state={},
            result='failed',
            error_message='Agent not found',
        )
        _mark_failed(event, f'Agent {event.agent_id} not found for workspace {event.workspace_id}')
        return {'action': 'pause_agent', 'failed': True, 'reason': 'agent_not_found'}

    previous_state = _snapshot_agent(agent)

    agent.is_active = False

    new_state = _snapshot_agent(agent)

    log_intervention(
        event_id=event.id,
        workspace_id=event.workspace_id,
        agent_id=event.agent_id,
        action_type='pause_agent',
        previous_state=previous_state,
        new_state=new_state,
        result='success',
    )

    return {'action': 'pause_agent', 'agent_id': agent.id, 'was_active': previous_state['is_active']}


def _execute_model_downgrade(event):
    """Downgrade an agent's LLM model to a cheaper alternative."""
    from models import db, Agent

    if event.agent_id is None:
        log_intervention(
            event_id=event.id,
            workspace_id=event.workspace_id,
            agent_id=None,
            action_type='model_downgrade',
            previous_state={},
            new_state={},
            result='skipped',
            error_message='No agent_id on event; cannot downgrade workspace-wide',
        )
        _mark_skipped(event, 'No agent_id; cannot downgrade workspace-wide')
        return {'action': 'model_downgrade', 'skipped': True, 'reason': 'no agent_id'}

    agent = Agent.query.filter_by(
        id=event.agent_id, user_id=event.workspace_id
    ).first()

    if agent is None:
        log_intervention(
            event_id=event.id,
            workspace_id=event.workspace_id,
            agent_id=event.agent_id,
            action_type='model_downgrade',
            previous_state={},
            new_state={},
            result='failed',
            error_message='Agent not found',
        )
        _mark_failed(event, f'Agent {event.agent_id} not found for workspace {event.workspace_id}')
        return {'action': 'model_downgrade', 'failed': True, 'reason': 'agent_not_found'}

    previous_state = _snapshot_agent(agent)

    llm_config = dict(agent.llm_config) if agent.llm_config else {}
    current_provider = llm_config.get('provider', 'openai')
    current_model = llm_config.get('model', '')

    target_model = _DOWNGRADE_TARGETS.get(current_provider, _DEFAULT_DOWNGRADE_MODEL)

    # Only downgrade if not already on the target model
    if current_model == target_model:
        log_intervention(
            event_id=event.id,
            workspace_id=event.workspace_id,
            agent_id=event.agent_id,
            action_type='model_downgrade',
            previous_state=previous_state,
            new_state=previous_state,
            result='skipped',
            error_message=f'Already on target model: {target_model}',
        )
        _mark_skipped(event, f'Already on target model: {target_model}')
        return {'action': 'model_downgrade', 'skipped': True, 'reason': 'already_downgraded'}

    llm_config['model'] = target_model
    agent.llm_config = llm_config

    new_state = _snapshot_agent(agent)

    log_intervention(
        event_id=event.id,
        workspace_id=event.workspace_id,
        agent_id=event.agent_id,
        action_type='model_downgrade',
        previous_state=previous_state,
        new_state=new_state,
        result='success',
    )

    return {
        'action': 'model_downgrade',
        'agent_id': agent.id,
        'previous_model': current_model,
        'new_model': target_model,
    }


def _execute_throttle(event):
    """Throttle an agent. Future implementation — no-op in v1."""
    log_intervention(
        event_id=event.id,
        workspace_id=event.workspace_id,
        agent_id=event.agent_id,
        action_type='throttle',
        previous_state={},
        new_state={},
        result='skipped',
        error_message='Throttle not implemented in v1',
    )
    _mark_skipped(event, 'Throttle not implemented in v1')
    return {'action': 'throttle', 'skipped': True, 'reason': 'not_implemented'}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _snapshot_agent(agent):
    """Capture agent state relevant to risk interventions."""
    return {
        'is_active': agent.is_active,
        'llm_config': dict(agent.llm_config) if agent.llm_config else None,
    }


def _mark_skipped(event, reason):
    """Mark event as skipped with a reason."""
    from models import db
    event.status = 'skipped'
    event.executed_at = datetime.utcnow()
    event.execution_result = {'skipped': True, 'reason': reason}
    db.session.commit()


def _mark_failed(event, error_message):
    """Mark event as failed."""
    from models import db
    try:
        event.status = 'failed'
        event.executed_at = datetime.utcnow()
        event.execution_result = {'failed': True, 'error': error_message}
        db.session.commit()
    except Exception:
        db.session.rollback()


# Action type → handler mapping
_ACTION_HANDLERS = {
    'alert_only': _execute_alert_only,
    'pause_agent': _execute_pause_agent,
    'model_downgrade': _execute_model_downgrade,
    'throttle': _execute_throttle,
}
