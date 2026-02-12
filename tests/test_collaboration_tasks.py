"""
Tests for the Collaboration Task System — Phase 1.

Covers: task CRUD, state transitions, delegation chains,
workspace isolation, and event logging.
"""
import pytest
import uuid
from datetime import datetime, timedelta
from models import db, User, Agent, CollaborationTask, TaskEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent_b(app, user):
    """Create a second agent in the same workspace."""
    a = Agent(
        user_id=user.id,
        name='AgentB',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def other_user(app):
    """Create a second user for workspace isolation tests."""
    u = User(
        email='other@example.com',
        created_at=datetime.utcnow(),
        credit_balance=10,
        subscription_tier='free',
        subscription_status='inactive',
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def other_agent(app, other_user):
    """Create an agent belonging to other_user."""
    a = Agent(
        user_id=other_user.id,
        name='OtherAgent',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


# ---------------------------------------------------------------------------
# Task Creation Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestTaskCreation:

    def test_create_task_by_user(self, authenticated_client, user, agent):
        """User can create a task assigned to their own agent."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Summarize the report',
            'assigned_to_agent_id': agent.id,
            'input': {'document_url': 'https://example.com/report.pdf'},
            'priority': 5,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        task = data['task']
        assert task['title'] == 'Summarize the report'
        assert task['status'] == 'queued'
        assert task['assigned_to_agent_id'] == agent.id
        assert task['created_by_user_id'] == user.id
        assert task['created_by_agent_id'] is None
        assert task['priority'] == 5
        assert task['input'] == {'document_url': 'https://example.com/report.pdf'}

    def test_create_task_by_agent(self, authenticated_client, user, agent, agent_b):
        """An agent can create a task assigned to another agent."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Research competitor pricing',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 201
        task = resp.get_json()['task']
        assert task['created_by_agent_id'] == agent.id
        assert task['assigned_to_agent_id'] == agent_b.id
        assert task['created_by_user_id'] is None

    def test_create_task_missing_title(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/tasks', json={
            'assigned_to_agent_id': agent.id,
        })
        assert resp.status_code == 400
        assert 'title' in resp.get_json()['error'].lower()

    def test_create_task_missing_assigned_to(self, authenticated_client):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Some task',
        })
        assert resp.status_code == 400
        assert 'assigned_to_agent_id' in resp.get_json()['error']

    def test_create_task_invalid_agent(self, authenticated_client):
        """Cannot assign a task to a non-existent agent."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Task for ghost',
            'assigned_to_agent_id': 99999,
        })
        assert resp.status_code == 404

    def test_create_task_emits_created_event(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Event test',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']
        events = TaskEvent.query.filter_by(task_id=task_id).all()
        assert len(events) == 1
        assert events[0].event_type == 'created'

    def test_create_task_requires_auth(self, client, agent):
        resp = client.post('/api/tasks', json={
            'title': 'No auth',
            'assigned_to_agent_id': agent.id,
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Task Listing / Retrieval Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestTaskRetrieval:

    def test_list_tasks(self, authenticated_client, user, agent):
        # Create two tasks
        for title in ['Task A', 'Task B']:
            authenticated_client.post('/api/tasks', json={
                'title': title,
                'assigned_to_agent_id': agent.id,
            })
        resp = authenticated_client.get('/api/tasks')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 2

    def test_list_tasks_filter_by_status(self, authenticated_client, user, agent):
        authenticated_client.post('/api/tasks', json={
            'title': 'Queued task',
            'assigned_to_agent_id': agent.id,
        })
        resp = authenticated_client.get('/api/tasks?status=running')
        assert resp.get_json()['count'] == 0

        resp = authenticated_client.get('/api/tasks?status=queued')
        assert resp.get_json()['count'] == 1

    def test_list_tasks_filter_by_assigned_to(self, authenticated_client, agent, agent_b):
        authenticated_client.post('/api/tasks', json={
            'title': 'For A', 'assigned_to_agent_id': agent.id,
        })
        authenticated_client.post('/api/tasks', json={
            'title': 'For B', 'assigned_to_agent_id': agent_b.id,
        })
        resp = authenticated_client.get(f'/api/tasks?assigned_to={agent_b.id}')
        data = resp.get_json()
        assert data['count'] == 1
        assert data['tasks'][0]['title'] == 'For B'

    def test_get_task_with_events(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Detail test',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        resp = authenticated_client.get(f'/api/tasks/{task_id}')
        assert resp.status_code == 200
        data = resp.get_json()['task']
        assert data['id'] == task_id
        assert len(data['events']) >= 1

    def test_get_task_not_found(self, authenticated_client):
        resp = authenticated_client.get(f'/api/tasks/{uuid.uuid4()}')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# State Transition Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestTaskTransitions:

    def _create_task(self, client, agent_id):
        resp = client.post('/api/tasks', json={
            'title': 'Transition test',
            'assigned_to_agent_id': agent_id,
        })
        return resp.get_json()['task']['id']

    def test_start_task(self, authenticated_client, agent):
        task_id = self._create_task(authenticated_client, agent.id)
        resp = authenticated_client.post(f'/api/tasks/{task_id}/start')
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'running'

    def test_complete_task(self, authenticated_client, agent):
        task_id = self._create_task(authenticated_client, agent.id)
        authenticated_client.post(f'/api/tasks/{task_id}/start')
        resp = authenticated_client.post(f'/api/tasks/{task_id}/complete', json={
            'output': {'summary': 'Done!'},
        })
        assert resp.status_code == 200
        task = resp.get_json()['task']
        assert task['status'] == 'completed'
        assert task['output'] == {'summary': 'Done!'}

    def test_fail_task(self, authenticated_client, agent):
        task_id = self._create_task(authenticated_client, agent.id)
        authenticated_client.post(f'/api/tasks/{task_id}/start')
        resp = authenticated_client.post(f'/api/tasks/{task_id}/fail', json={
            'output': {'error': 'Model timeout'},
            'reason': 'LLM provider unreachable',
        })
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'failed'

    def test_cancel_queued_task(self, authenticated_client, agent):
        task_id = self._create_task(authenticated_client, agent.id)
        resp = authenticated_client.post(f'/api/tasks/{task_id}/cancel')
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'canceled'

    def test_invalid_transition_queued_to_completed(self, authenticated_client, agent):
        task_id = self._create_task(authenticated_client, agent.id)
        resp = authenticated_client.post(f'/api/tasks/{task_id}/complete')
        assert resp.status_code == 409

    def test_invalid_transition_completed_to_running(self, authenticated_client, agent):
        task_id = self._create_task(authenticated_client, agent.id)
        authenticated_client.post(f'/api/tasks/{task_id}/start')
        authenticated_client.post(f'/api/tasks/{task_id}/complete')
        resp = authenticated_client.post(f'/api/tasks/{task_id}/start')
        assert resp.status_code == 409

    def test_transitions_emit_events(self, authenticated_client, agent):
        task_id = self._create_task(authenticated_client, agent.id)
        authenticated_client.post(f'/api/tasks/{task_id}/start')
        authenticated_client.post(f'/api/tasks/{task_id}/complete')

        events = TaskEvent.query.filter_by(task_id=task_id).order_by(
            TaskEvent.created_at.asc()
        ).all()
        types = [e.event_type for e in events]
        assert types == ['created', 'started', 'completed']


# ---------------------------------------------------------------------------
# Delegation Chain Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestDelegationChain:

    def test_parent_task_id(self, authenticated_client, agent, agent_b):
        # Create parent
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Parent task',
            'assigned_to_agent_id': agent.id,
        })
        parent_id = resp.get_json()['task']['id']

        # Create subtask
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Sub task',
            'assigned_to_agent_id': agent_b.id,
            'parent_task_id': parent_id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 201
        sub = resp.get_json()['task']
        assert sub['parent_task_id'] == parent_id

    def test_filter_subtasks(self, authenticated_client, agent, agent_b):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Root',
            'assigned_to_agent_id': agent.id,
        })
        root_id = resp.get_json()['task']['id']

        for i in range(3):
            authenticated_client.post('/api/tasks', json={
                'title': f'Child {i}',
                'assigned_to_agent_id': agent_b.id,
                'parent_task_id': root_id,
            })

        resp = authenticated_client.get(f'/api/tasks?parent_task_id={root_id}')
        assert resp.get_json()['count'] == 3

    def test_invalid_parent_task(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Orphan',
            'assigned_to_agent_id': agent.id,
            'parent_task_id': str(uuid.uuid4()),
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task Reassignment Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestTaskReassignment:

    def test_reassign_task(self, authenticated_client, agent, agent_b):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Reassign me',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        resp = authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })
        assert resp.status_code == 200
        assert resp.get_json()['task']['assigned_to_agent_id'] == agent_b.id

    def test_reassign_running_resets_to_queued(self, authenticated_client, agent, agent_b):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Running reassign',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']
        authenticated_client.post(f'/api/tasks/{task_id}/start')

        resp = authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })
        task = resp.get_json()['task']
        assert task['status'] == 'queued'
        assert task['assigned_to_agent_id'] == agent_b.id

    def test_reassign_completed_fails(self, authenticated_client, agent, agent_b):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Done task',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']
        authenticated_client.post(f'/api/tasks/{task_id}/start')
        authenticated_client.post(f'/api/tasks/{task_id}/complete')

        resp = authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })
        assert resp.status_code == 409

    def test_reassign_emits_event(self, authenticated_client, agent, agent_b):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Event check',
            'assigned_to_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']
        authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_b.id,
        })

        events = TaskEvent.query.filter_by(
            task_id=task_id, event_type='assigned',
        ).all()
        assert len(events) == 1
        assert events[0].payload['to_agent_id'] == agent_b.id


# ---------------------------------------------------------------------------
# Workspace Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestWorkspaceIsolation:

    def test_cannot_see_other_workspace_tasks(
        self, app, authenticated_client, user, agent, other_user, other_agent,
    ):
        """Tasks from another workspace are invisible."""
        # Create task in other workspace directly
        task = CollaborationTask(
            id=str(uuid.uuid4()),
            workspace_id=other_user.id,
            created_by_user_id=other_user.id,
            assigned_to_agent_id=other_agent.id,
            title='Secret task',
            status='queued',
        )
        db.session.add(task)
        db.session.commit()

        resp = authenticated_client.get('/api/tasks')
        assert resp.get_json()['count'] == 0

    def test_cannot_get_other_workspace_task(
        self, app, authenticated_client, other_user, other_agent,
    ):
        task = CollaborationTask(
            id=str(uuid.uuid4()),
            workspace_id=other_user.id,
            created_by_user_id=other_user.id,
            assigned_to_agent_id=other_agent.id,
            title='Secret',
            status='queued',
        )
        db.session.add(task)
        db.session.commit()

        resp = authenticated_client.get(f'/api/tasks/{task.id}')
        assert resp.status_code == 404

    def test_cannot_assign_to_other_workspace_agent(
        self, authenticated_client, other_agent,
    ):
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Cross-workspace',
            'assigned_to_agent_id': other_agent.id,
        })
        assert resp.status_code == 404

    def test_cannot_start_other_workspace_task(
        self, app, authenticated_client, other_user, other_agent,
    ):
        task = CollaborationTask(
            id=str(uuid.uuid4()),
            workspace_id=other_user.id,
            created_by_user_id=other_user.id,
            assigned_to_agent_id=other_agent.id,
            title='Foreign task',
            status='queued',
        )
        db.session.add(task)
        db.session.commit()

        resp = authenticated_client.post(f'/api/tasks/{task.id}/start')
        assert resp.status_code == 404
