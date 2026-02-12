"""
Tests for the Collaboration Messaging System — Phase 2.

Covers: message send/receive, task-linked threads, free threads,
role validation, workspace isolation, and filtering.
"""
import pytest
import uuid
from datetime import datetime
from models import db, User, Agent, CollaborationTask, AgentMessage


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
    """A collaboration task for message threading."""
    t = CollaborationTask(
        id=str(uuid.uuid4()),
        workspace_id=user.id,
        created_by_user_id=user.id,
        assigned_to_agent_id=agent.id,
        title='Message test task',
        status='running',
    )
    db.session.add(t)
    db.session.commit()
    return t


@pytest.fixture
def other_user(app):
    u = User(
        email='other@example.com', created_at=datetime.utcnow(),
        credit_balance=10, subscription_tier='free',
        subscription_status='inactive',
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def other_agent(app, other_user):
    a = Agent(
        user_id=other_user.id, name='OtherAgent', is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


# ---------------------------------------------------------------------------
# Send Message Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestSendMessage:

    def test_send_agent_message(self, authenticated_client, agent, agent_b):
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Hello from Agent A',
            'from_agent_id': agent.id,
            'to_agent_id': agent_b.id,
            'role': 'agent',
            'thread_id': str(uuid.uuid4()),
        })
        assert resp.status_code == 201
        msg = resp.get_json()['message']
        assert msg['content'] == 'Hello from Agent A'
        assert msg['from_agent_id'] == agent.id
        assert msg['to_agent_id'] == agent_b.id
        assert msg['role'] == 'agent'

    def test_send_user_message(self, authenticated_client, user, agent):
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Instructions from the user',
            'to_agent_id': agent.id,
            'role': 'user',
            'thread_id': str(uuid.uuid4()),
        })
        assert resp.status_code == 201
        msg = resp.get_json()['message']
        assert msg['role'] == 'user'
        assert msg['from_user_id'] == user.id

    def test_send_system_message(self, authenticated_client, agent, task):
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Task deadline approaching',
            'task_id': task.id,
            'role': 'system',
        })
        assert resp.status_code == 201
        assert resp.get_json()['message']['role'] == 'system'

    def test_send_task_linked_message(self, authenticated_client, agent, agent_b, task):
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Here are the results',
            'from_agent_id': agent.id,
            'to_agent_id': agent_b.id,
            'task_id': task.id,
            'role': 'agent',
        })
        assert resp.status_code == 201
        msg = resp.get_json()['message']
        assert msg['task_id'] == task.id

    def test_send_message_missing_content(self, authenticated_client):
        resp = authenticated_client.post('/api/messages', json={
            'role': 'agent',
            'thread_id': str(uuid.uuid4()),
        })
        assert resp.status_code == 400
        assert 'content' in resp.get_json()['error'].lower()

    def test_send_message_invalid_role(self, authenticated_client):
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Bad role',
            'role': 'superadmin',
            'thread_id': str(uuid.uuid4()),
        })
        assert resp.status_code == 400
        assert 'role' in resp.get_json()['error'].lower()

    def test_send_message_invalid_task(self, authenticated_client):
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Ghost task',
            'task_id': str(uuid.uuid4()),
            'role': 'agent',
        })
        assert resp.status_code == 404

    def test_send_message_requires_auth(self, client):
        resp = client.post('/api/messages', json={
            'content': 'No auth',
            'role': 'agent',
            'thread_id': str(uuid.uuid4()),
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# List Messages Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestListMessages:

    def test_list_by_task_id(self, authenticated_client, agent, agent_b, task):
        # Send 3 messages on this task
        for i in range(3):
            authenticated_client.post('/api/messages', json={
                'content': f'Msg {i}',
                'from_agent_id': agent.id,
                'task_id': task.id,
                'role': 'agent',
            })
        resp = authenticated_client.get(f'/api/messages?task_id={task.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 3

    def test_list_by_thread_id(self, authenticated_client, agent, agent_b):
        thread = str(uuid.uuid4())
        for i in range(2):
            authenticated_client.post('/api/messages', json={
                'content': f'Thread msg {i}',
                'from_agent_id': agent.id,
                'thread_id': thread,
                'role': 'agent',
            })
        # Unrelated message with different thread
        authenticated_client.post('/api/messages', json={
            'content': 'Other thread',
            'from_agent_id': agent.id,
            'thread_id': str(uuid.uuid4()),
            'role': 'agent',
        })

        resp = authenticated_client.get(f'/api/messages?thread_id={thread}')
        assert resp.get_json()['count'] == 2

    def test_list_requires_task_or_thread(self, authenticated_client):
        resp = authenticated_client.get('/api/messages')
        assert resp.status_code == 400

    def test_list_filter_by_role(self, authenticated_client, agent, task):
        authenticated_client.post('/api/messages', json={
            'content': 'Agent says', 'task_id': task.id,
            'from_agent_id': agent.id, 'role': 'agent',
        })
        authenticated_client.post('/api/messages', json={
            'content': 'System says', 'task_id': task.id,
            'role': 'system',
        })
        resp = authenticated_client.get(
            f'/api/messages?task_id={task.id}&role=system'
        )
        data = resp.get_json()
        assert data['count'] == 1
        assert data['messages'][0]['role'] == 'system'

    def test_list_filter_by_agent(self, authenticated_client, agent, agent_b, task):
        authenticated_client.post('/api/messages', json={
            'content': 'From A', 'task_id': task.id,
            'from_agent_id': agent.id, 'role': 'agent',
        })
        authenticated_client.post('/api/messages', json={
            'content': 'From B', 'task_id': task.id,
            'from_agent_id': agent_b.id, 'role': 'agent',
        })
        resp = authenticated_client.get(
            f'/api/messages?task_id={task.id}&agent_id={agent_b.id}'
        )
        data = resp.get_json()
        assert data['count'] == 1
        assert data['messages'][0]['from_agent_id'] == agent_b.id

    def test_messages_ordered_chronologically(self, authenticated_client, agent, task):
        for i in range(5):
            authenticated_client.post('/api/messages', json={
                'content': f'Msg {i}', 'task_id': task.id,
                'from_agent_id': agent.id, 'role': 'agent',
            })
        resp = authenticated_client.get(f'/api/messages?task_id={task.id}')
        messages = resp.get_json()['messages']
        contents = [m['content'] for m in messages]
        assert contents == ['Msg 0', 'Msg 1', 'Msg 2', 'Msg 3', 'Msg 4']


# ---------------------------------------------------------------------------
# Workspace Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestMessageIsolation:

    def test_cannot_see_other_workspace_messages(
        self, app, authenticated_client, user, agent,
        other_user, other_agent,
    ):
        """Messages from another workspace are invisible."""
        thread = str(uuid.uuid4())
        msg = AgentMessage(
            workspace_id=other_user.id,
            from_agent_id=other_agent.id,
            thread_id=thread,
            role='agent',
            content='Secret message',
        )
        db.session.add(msg)
        db.session.commit()

        resp = authenticated_client.get(f'/api/messages?thread_id={thread}')
        assert resp.get_json()['count'] == 0

    def test_cannot_send_to_other_workspace_agent(
        self, authenticated_client, other_agent,
    ):
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Cross workspace',
            'to_agent_id': other_agent.id,
            'role': 'agent',
            'thread_id': str(uuid.uuid4()),
        })
        assert resp.status_code == 404

    def test_cannot_send_from_other_workspace_agent(
        self, authenticated_client, other_agent,
    ):
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Impersonation',
            'from_agent_id': other_agent.id,
            'role': 'agent',
            'thread_id': str(uuid.uuid4()),
        })
        assert resp.status_code == 404

    def test_cannot_link_to_other_workspace_task(
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

        resp = authenticated_client.post('/api/messages', json={
            'content': 'Link to foreign task',
            'task_id': task.id,
            'role': 'agent',
        })
        assert resp.status_code == 404
