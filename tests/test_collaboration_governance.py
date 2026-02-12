"""
Tests for the Collaboration Governance Integration — Phase 4.

Covers: pre-start risk checks (agent paused, pending risk events),
observability event emission, governance audit trail logging (block,
escalation, reassignment), and best-effort resilience.
"""
import pytest
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock
from models import (
    db, User, Agent, RiskPolicy, RiskEvent, AgentRole,
    CollaborationTask, TaskEvent, GovernanceAuditLog,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent_b(app, user):
    """Second agent in same workspace."""
    a = Agent(
        user_id=user.id, name='AgentB', is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def task(app, user, agent):
    """A queued collaboration task."""
    t = CollaborationTask(
        id=str(uuid.uuid4()),
        workspace_id=user.id,
        created_by_user_id=user.id,
        assigned_to_agent_id=agent.id,
        title='Governance test task',
        status='queued',
    )
    db.session.add(t)
    db.session.commit()
    return t


@pytest.fixture
def running_task(app, user, agent):
    """A running collaboration task."""
    t = CollaborationTask(
        id=str(uuid.uuid4()),
        workspace_id=user.id,
        created_by_user_id=user.id,
        assigned_to_agent_id=agent.id,
        title='Running task',
        status='running',
    )
    db.session.add(t)
    db.session.commit()
    return t


@pytest.fixture
def paused_agent(app, user):
    """An agent that has been paused by a risk intervention."""
    a = Agent(
        user_id=user.id, name='PausedAgent', is_active=False,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def risk_policy(app, user, agent):
    """An active risk policy for the test agent."""
    p = RiskPolicy(
        workspace_id=user.id,
        agent_id=agent.id,
        policy_type='daily_spend_cap',
        threshold_value=50.00,
        action_type='pause_agent',
        cooldown_minutes=360,
        is_enabled=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def pending_risk_event(app, user, agent, risk_policy):
    """A pending risk event for the test agent."""
    e = RiskEvent(
        uid=str(uuid.uuid4()),
        policy_id=risk_policy.id,
        workspace_id=user.id,
        agent_id=agent.id,
        policy_type='daily_spend_cap',
        breach_value=75.00,
        threshold_value=50.00,
        action_type='pause_agent',
        status='pending',
        evaluated_at=datetime.utcnow(),
    )
    db.session.add(e)
    db.session.commit()
    return e


# ---------------------------------------------------------------------------
# Pre-Start Risk Check Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestPreStartRiskCheck:

    def test_start_allowed_when_agent_healthy(self, authenticated_client, task):
        """Healthy agent can start a task."""
        resp = authenticated_client.post(f'/api/tasks/{task.id}/start')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['task']['status'] == 'running'

    def test_start_blocked_when_agent_paused(
        self, app, authenticated_client, user, paused_agent,
    ):
        """Paused agent cannot start a task — task gets blocked."""
        t = CollaborationTask(
            id=str(uuid.uuid4()),
            workspace_id=user.id,
            created_by_user_id=user.id,
            assigned_to_agent_id=paused_agent.id,
            title='Task for paused agent',
            status='queued',
        )
        db.session.add(t)
        db.session.commit()

        resp = authenticated_client.post(f'/api/tasks/{t.id}/start')
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['blocked'] is True
        assert 'paused' in data['reason'].lower()
        assert data['task']['status'] == 'blocked'

    def test_start_blocked_when_pending_risk_event(
        self, authenticated_client, task, pending_risk_event,
    ):
        """Agent with pending risk events cannot start a task."""
        resp = authenticated_client.post(f'/api/tasks/{task.id}/start')
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['blocked'] is True
        assert 'risk event' in data['reason'].lower()

    def test_blocked_task_emits_event(
        self, app, authenticated_client, user, paused_agent,
    ):
        """Blocking a task creates a TaskEvent with type 'blocked'."""
        t = CollaborationTask(
            id=str(uuid.uuid4()),
            workspace_id=user.id,
            created_by_user_id=user.id,
            assigned_to_agent_id=paused_agent.id,
            title='Blocked task events',
            status='queued',
        )
        db.session.add(t)
        db.session.commit()

        authenticated_client.post(f'/api/tasks/{t.id}/start')

        events = TaskEvent.query.filter_by(task_id=t.id).all()
        blocked_events = [e for e in events if e.event_type == 'blocked']
        assert len(blocked_events) == 1
        assert 'paused' in blocked_events[0].payload.get('reason', '').lower()

    def test_blocked_task_logs_governance_audit(
        self, app, authenticated_client, user, paused_agent,
    ):
        """Blocking a task logs a governance audit entry."""
        t = CollaborationTask(
            id=str(uuid.uuid4()),
            workspace_id=user.id,
            created_by_user_id=user.id,
            assigned_to_agent_id=paused_agent.id,
            title='Audit trail task',
            status='queued',
        )
        db.session.add(t)
        db.session.commit()

        authenticated_client.post(f'/api/tasks/{t.id}/start')

        audits = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_blocked',
        ).all()
        assert len(audits) == 1
        assert audits[0].details['task_id'] == t.id

    def test_blocked_task_can_be_started_after_resolution(
        self, app, authenticated_client, user, agent, task, pending_risk_event,
    ):
        """After risk event is resolved, blocked task can be started."""
        # First attempt — blocked
        resp = authenticated_client.post(f'/api/tasks/{task.id}/start')
        assert resp.status_code == 409

        # Resolve the risk event
        pending_risk_event.status = 'executed'
        db.session.commit()

        # Second attempt — task is now 'blocked', transition to running
        resp = authenticated_client.post(f'/api/tasks/{task.id}/start')
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'running'


# ---------------------------------------------------------------------------
# Observability Event Emission Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestObservabilityEmission:

    @patch('core.observability.ingestion.emit_event')
    def test_start_emits_action_started(self, mock_emit, authenticated_client, task):
        resp = authenticated_client.post(f'/api/tasks/{task.id}/start')
        assert resp.status_code == 200

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs['event_type'] == 'action_started'
        assert call_kwargs['agent_id'] == task.assigned_to_agent_id
        assert call_kwargs['payload']['task_id'] == task.id

    @patch('core.observability.ingestion.emit_event')
    def test_complete_emits_action_finished(self, mock_emit, authenticated_client, running_task):
        resp = authenticated_client.post(f'/api/tasks/{running_task.id}/complete', json={
            'output': {'result': 'done'},
        })
        assert resp.status_code == 200

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs['event_type'] == 'action_finished'
        assert call_kwargs['status'] == 'success'

    @patch('core.observability.ingestion.emit_event')
    def test_fail_emits_error_event(self, mock_emit, authenticated_client, running_task):
        resp = authenticated_client.post(f'/api/tasks/{running_task.id}/fail', json={
            'reason': 'out of tokens',
        })
        assert resp.status_code == 200

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs['event_type'] == 'error'
        assert call_kwargs['status'] == 'error'
        assert 'out of tokens' in call_kwargs['payload']['reason']


# ---------------------------------------------------------------------------
# Governance Audit Trail Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestGovernanceAuditTrail:

    def test_escalation_logged(self, authenticated_client, agent, agent_b, user):
        """Reassigning to a supervisor logs a task_escalated audit entry."""
        # Make agent_b a supervisor
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent_b.id, 'role': 'supervisor',
        })

        # Create and assign task to agent
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Escalation test',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        # Reassign to supervisor (escalation)
        authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })

        audits = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_escalated',
        ).all()
        assert len(audits) == 1
        assert audits[0].details['from_agent_id'] == agent.id
        assert audits[0].details['to_agent_id'] == agent_b.id

    def test_reassignment_logged(self, authenticated_client, agent, agent_b, user):
        """Every reassignment logs a task_reassigned audit entry."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Reassign audit test',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })

        audits = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_reassigned',
        ).all()
        assert len(audits) == 1
        assert audits[0].details['task_id'] == task_id

    def test_escalation_also_has_reassignment_audit(
        self, authenticated_client, agent, agent_b, user,
    ):
        """Escalation creates both task_reassigned and task_escalated entries."""
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent_b.id, 'role': 'supervisor',
        })
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Both audits',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })

        reassigned = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_reassigned',
        ).count()
        escalated = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_escalated',
        ).count()
        assert reassigned == 1
        assert escalated == 1

    def test_no_escalation_for_non_supervisor(
        self, authenticated_client, agent, agent_b, user,
    ):
        """Reassigning to a non-supervisor does not log task_escalated."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'No escalation',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })

        escalated = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_escalated',
        ).count()
        assert escalated == 0

    def test_governance_audit_queryable_via_api(
        self, app, authenticated_client, user, paused_agent,
    ):
        """Governance audit events are queryable via existing /api/governance/audit."""
        t = CollaborationTask(
            id=str(uuid.uuid4()),
            workspace_id=user.id,
            created_by_user_id=user.id,
            assigned_to_agent_id=paused_agent.id,
            title='Audit query test',
            status='queued',
        )
        db.session.add(t)
        db.session.commit()

        authenticated_client.post(f'/api/tasks/{t.id}/start')

        resp = authenticated_client.get('/api/governance/audit?event_type=task_blocked')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] >= 1


# ---------------------------------------------------------------------------
# Best-Effort Resilience Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestBestEffortResilience:

    @patch('core.observability.ingestion.emit_event', side_effect=Exception('obs down'))
    def test_task_completes_even_if_observability_fails(
        self, mock_emit, authenticated_client, running_task,
    ):
        """Observability failure does not block task completion."""
        resp = authenticated_client.post(f'/api/tasks/{running_task.id}/complete')
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'completed'

    @patch('core.observability.ingestion.emit_event', side_effect=Exception('obs down'))
    def test_task_starts_even_if_observability_fails(
        self, mock_emit, authenticated_client, task,
    ):
        """Observability failure does not block task start."""
        resp = authenticated_client.post(f'/api/tasks/{task.id}/start')
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'running'

    @patch(
        'core.governance.governance_audit.log_governance_event',
        side_effect=Exception('audit down'),
    )
    def test_reassign_succeeds_even_if_audit_fails(
        self, mock_audit, authenticated_client, agent, agent_b,
    ):
        """Governance audit failure does not block reassignment."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Resilience test',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        resp = authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })
        assert resp.status_code == 200
