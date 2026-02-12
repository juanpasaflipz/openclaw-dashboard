"""
Tests for the Collaboration Team Hierarchy — Phase 3.

Covers: agent roles CRUD, team rules CRUD, role-based assignment enforcement
on task creation/reassignment, workspace isolation, and team summary.
"""
import pytest
import uuid
from datetime import datetime
from models import db, User, Agent, AgentRole, TeamRule, CollaborationTask


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
def agent_c(app, user):
    """Third agent in same workspace."""
    a = Agent(
        user_id=user.id, name='AgentC', is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


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
# Agent Role CRUD Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestAgentRoles:

    def test_set_role(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id,
            'role': 'supervisor',
        })
        assert resp.status_code == 201
        data = resp.get_json()['role']
        assert data['agent_id'] == agent.id
        assert data['role'] == 'supervisor'

    def test_set_role_worker(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id,
            'role': 'worker',
            'can_assign_to_peers': True,
        })
        assert resp.status_code == 201
        data = resp.get_json()['role']
        assert data['role'] == 'worker'
        assert data['can_assign_to_peers'] is True

    def test_set_role_specialist(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id,
            'role': 'specialist',
            'can_escalate_to_supervisor': False,
        })
        assert resp.status_code == 201
        data = resp.get_json()['role']
        assert data['role'] == 'specialist'
        assert data['can_escalate_to_supervisor'] is False

    def test_update_existing_role(self, authenticated_client, agent):
        # Create as worker
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'worker',
        })
        # Update to supervisor
        resp = authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'supervisor',
        })
        assert resp.status_code == 201
        assert resp.get_json()['role']['role'] == 'supervisor'

    def test_invalid_role(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'admin',
        })
        assert resp.status_code == 400
        assert 'role' in resp.get_json()['error'].lower()

    def test_missing_agent_id(self, authenticated_client):
        resp = authenticated_client.post('/api/team/roles', json={
            'role': 'worker',
        })
        assert resp.status_code == 400

    def test_invalid_agent(self, authenticated_client):
        resp = authenticated_client.post('/api/team/roles', json={
            'agent_id': 99999, 'role': 'worker',
        })
        assert resp.status_code == 404

    def test_get_role(self, authenticated_client, agent):
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'worker',
        })
        resp = authenticated_client.get(f'/api/team/roles/{agent.id}')
        assert resp.status_code == 200
        assert resp.get_json()['role']['role'] == 'worker'

    def test_get_role_not_found(self, authenticated_client, agent):
        resp = authenticated_client.get(f'/api/team/roles/{agent.id}')
        assert resp.status_code == 404

    def test_list_roles(self, authenticated_client, agent, agent_b):
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'supervisor',
        })
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent_b.id, 'role': 'worker',
        })
        resp = authenticated_client.get('/api/team/roles')
        assert resp.status_code == 200
        assert resp.get_json()['count'] == 2

    def test_delete_role(self, authenticated_client, agent):
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'worker',
        })
        resp = authenticated_client.post(f'/api/team/roles/{agent.id}/delete')
        assert resp.status_code == 200
        # Verify it's gone
        resp = authenticated_client.get(f'/api/team/roles/{agent.id}')
        assert resp.status_code == 404

    def test_delete_role_not_found(self, authenticated_client, agent):
        resp = authenticated_client.post(f'/api/team/roles/{agent.id}/delete')
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.post('/api/team/roles', json={
            'agent_id': 1, 'role': 'worker',
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Team Rules Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestTeamRules:

    def test_get_default_rules(self, authenticated_client):
        resp = authenticated_client.get('/api/team/rules')
        assert resp.status_code == 200
        rules = resp.get_json()['rules']
        assert rules['allow_peer_assignment'] is False
        assert rules['require_supervisor_for_tasks'] is False
        assert rules['default_supervisor_agent_id'] is None

    def test_set_rules(self, authenticated_client):
        resp = authenticated_client.post('/api/team/rules', json={
            'allow_peer_assignment': True,
        })
        assert resp.status_code == 201
        rules = resp.get_json()['rules']
        assert rules['allow_peer_assignment'] is True

    def test_update_rules(self, authenticated_client):
        authenticated_client.post('/api/team/rules', json={
            'allow_peer_assignment': False,
        })
        resp = authenticated_client.post('/api/team/rules', json={
            'allow_peer_assignment': True,
            'require_supervisor_for_tasks': True,
        })
        assert resp.status_code == 201
        rules = resp.get_json()['rules']
        assert rules['allow_peer_assignment'] is True
        assert rules['require_supervisor_for_tasks'] is True

    def test_set_default_supervisor(self, authenticated_client, agent):
        # Agent must have supervisor role first
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'supervisor',
        })
        resp = authenticated_client.post('/api/team/rules', json={
            'default_supervisor_agent_id': agent.id,
        })
        assert resp.status_code == 201
        assert resp.get_json()['rules']['default_supervisor_agent_id'] == agent.id

    def test_cannot_set_worker_as_default_supervisor(self, authenticated_client, agent):
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'worker',
        })
        resp = authenticated_client.post('/api/team/rules', json={
            'default_supervisor_agent_id': agent.id,
        })
        assert resp.status_code == 400
        assert 'supervisor role' in resp.get_json()['error'].lower()

    def test_cannot_set_invalid_agent_as_supervisor(self, authenticated_client):
        resp = authenticated_client.post('/api/team/rules', json={
            'default_supervisor_agent_id': 99999,
        })
        assert resp.status_code == 404

    def test_rules_require_auth(self, client):
        resp = client.get('/api/team/rules')
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Role-Based Assignment Enforcement Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestRoleEnforcement:

    def _enable_enforcement(self, client, allow_peer=False):
        """Helper to set up enforcement rules."""
        client.post('/api/team/rules', json={
            'require_supervisor_for_tasks': True,
            'allow_peer_assignment': allow_peer,
        })

    def _set_role(self, client, agent_id, role, **kwargs):
        client.post('/api/team/roles', json={
            'agent_id': agent_id, 'role': role, **kwargs,
        })

    def test_no_enforcement_by_default(self, authenticated_client, agent, agent_b):
        """Without team rules, any agent can assign to any other."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Free assignment',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 201

    def test_supervisor_can_assign_to_anyone(self, authenticated_client, agent, agent_b):
        self._enable_enforcement(authenticated_client)
        self._set_role(authenticated_client, agent.id, 'supervisor')
        self._set_role(authenticated_client, agent_b.id, 'worker')

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Supervisor assigns',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 201

    def test_worker_cannot_assign_to_peer_without_permission(
        self, authenticated_client, agent, agent_b,
    ):
        self._enable_enforcement(authenticated_client, allow_peer=False)
        self._set_role(authenticated_client, agent.id, 'worker')
        self._set_role(authenticated_client, agent_b.id, 'worker')

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Worker to peer',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 403

    def test_worker_can_assign_to_peer_with_permission(
        self, authenticated_client, agent, agent_b,
    ):
        self._enable_enforcement(authenticated_client, allow_peer=True)
        self._set_role(authenticated_client, agent.id, 'worker',
                       can_assign_to_peers=True)
        self._set_role(authenticated_client, agent_b.id, 'worker')

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Worker to peer allowed',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 201

    def test_worker_can_escalate_to_supervisor(
        self, authenticated_client, agent, agent_b,
    ):
        self._enable_enforcement(authenticated_client)
        self._set_role(authenticated_client, agent.id, 'worker')
        self._set_role(authenticated_client, agent_b.id, 'supervisor')

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Escalation',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 201

    def test_worker_cannot_escalate_when_disabled(
        self, authenticated_client, agent, agent_b,
    ):
        self._enable_enforcement(authenticated_client)
        self._set_role(authenticated_client, agent.id, 'worker',
                       can_escalate_to_supervisor=False)
        self._set_role(authenticated_client, agent_b.id, 'supervisor')

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Blocked escalation',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 403
        assert 'escalation' in resp.get_json()['error'].lower()

    def test_worker_can_assign_to_self(self, authenticated_client, agent):
        self._enable_enforcement(authenticated_client)
        self._set_role(authenticated_client, agent.id, 'worker')

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Self-assign',
            'assigned_to_agent_id': agent.id,
            'created_by_agent_id': agent.id,
        })
        assert resp.status_code == 201

    def test_human_created_task_bypasses_enforcement(
        self, authenticated_client, agent, agent_b,
    ):
        """Tasks created by the user (no created_by_agent_id) skip role checks."""
        self._enable_enforcement(authenticated_client)
        self._set_role(authenticated_client, agent.id, 'worker')
        self._set_role(authenticated_client, agent_b.id, 'worker')

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Human created',
            'assigned_to_agent_id': agent_b.id,
            # No created_by_agent_id → user-created
        })
        assert resp.status_code == 201

    def test_enforcement_on_reassign(
        self, authenticated_client, agent, agent_b, agent_c,
    ):
        self._enable_enforcement(authenticated_client, allow_peer=False)
        self._set_role(authenticated_client, agent.id, 'supervisor')
        self._set_role(authenticated_client, agent_b.id, 'worker')
        self._set_role(authenticated_client, agent_c.id, 'worker')

        # Create task assigned to agent_b
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'To reassign',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        # Worker tries to reassign to peer — blocked
        resp = authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_c.id,
            'agent_id': agent_b.id,  # requesting agent
        })
        assert resp.status_code == 403

    def test_reassign_without_agent_bypasses_enforcement(
        self, authenticated_client, agent, agent_b, agent_c,
    ):
        """Reassignment without agent_id (human-initiated) skips role checks."""
        self._enable_enforcement(authenticated_client, allow_peer=False)
        self._set_role(authenticated_client, agent.id, 'supervisor')
        self._set_role(authenticated_client, agent_b.id, 'worker')
        self._set_role(authenticated_client, agent_c.id, 'worker')

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'To reassign',
            'assigned_to_agent_id': agent_b.id,
            'created_by_agent_id': agent.id,
        })
        task_id = resp.get_json()['task']['id']

        # Human-initiated reassignment — no agent_id in payload
        resp = authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': agent_c.id,
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Team Summary Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestTeamSummary:

    def test_summary_empty(self, authenticated_client, agent):
        resp = authenticated_client.get('/api/team/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['supervisors'] == []
        assert data['workers'] == []
        assert data['specialists'] == []
        # Agent without role should appear in unassigned
        unassigned_ids = [a['id'] for a in data['unassigned_agents']]
        assert agent.id in unassigned_ids

    def test_summary_with_roles(self, authenticated_client, agent, agent_b, agent_c):
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent.id, 'role': 'supervisor',
        })
        authenticated_client.post('/api/team/roles', json={
            'agent_id': agent_b.id, 'role': 'worker',
        })
        resp = authenticated_client.get('/api/team/summary')
        data = resp.get_json()
        assert len(data['supervisors']) == 1
        assert len(data['workers']) == 1
        assert len(data['specialists']) == 0
        # agent_c has no role
        unassigned_ids = [a['id'] for a in data['unassigned_agents']]
        assert agent_c.id in unassigned_ids

    def test_summary_requires_auth(self, client):
        resp = client.get('/api/team/summary')
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Workspace Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestTeamIsolation:

    def test_cannot_set_role_for_other_workspace_agent(
        self, authenticated_client, other_agent,
    ):
        resp = authenticated_client.post('/api/team/roles', json={
            'agent_id': other_agent.id, 'role': 'worker',
        })
        assert resp.status_code == 404

    def test_cannot_see_other_workspace_roles(
        self, app, authenticated_client, other_user, other_agent,
    ):
        # Create role in other workspace directly
        role = AgentRole(
            workspace_id=other_user.id,
            agent_id=other_agent.id,
            role='supervisor',
        )
        db.session.add(role)
        db.session.commit()

        resp = authenticated_client.get('/api/team/roles')
        assert resp.get_json()['count'] == 0

    def test_cannot_get_other_workspace_agent_role(
        self, app, authenticated_client, other_user, other_agent,
    ):
        role = AgentRole(
            workspace_id=other_user.id,
            agent_id=other_agent.id,
            role='worker',
        )
        db.session.add(role)
        db.session.commit()

        resp = authenticated_client.get(f'/api/team/roles/{other_agent.id}')
        assert resp.status_code == 404

    def test_cannot_set_other_workspace_agent_as_default_supervisor(
        self, authenticated_client, other_agent,
    ):
        resp = authenticated_client.post('/api/team/rules', json={
            'default_supervisor_agent_id': other_agent.id,
        })
        assert resp.status_code == 404
