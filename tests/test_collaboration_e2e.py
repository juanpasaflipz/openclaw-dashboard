"""
End-to-End Tests for the Multi-Agent Collaboration Framework — Phase 6.

Tests full lifecycle scenarios using 3 agents:
  - Supervisor (Alpha): oversees work, can assign to anyone
  - Worker (Beta): executes tasks, can escalate to supervisor
  - Specialist (Gamma): handles specialist work, limited assignment

Covers cross-phase integration:
  Phase 1: Task creation, transitions, delegation chains
  Phase 2: Messaging within task threads and free threads
  Phase 3: Role-based hierarchy enforcement
  Phase 4: Risk/governance hooks (blocking, observability, audit trail)
  Phase 5: (UI — not testable server-side)
"""
import pytest
import uuid
from datetime import datetime
from unittest.mock import patch
from models import (
    db, User, Agent, RiskPolicy, RiskEvent, AgentRole, TeamRule,
    CollaborationTask, TaskEvent, AgentMessage, GovernanceAuditLog,
)


# ---------------------------------------------------------------------------
# Fixtures — 3-agent team in a single workspace
# ---------------------------------------------------------------------------

@pytest.fixture
def supervisor(app, user):
    """Agent Alpha — supervisor role."""
    a = Agent(
        user_id=user.id, name='Alpha', is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def worker(app, user):
    """Agent Beta — worker role."""
    a = Agent(
        user_id=user.id, name='Beta', is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def specialist(app, user):
    """Agent Gamma — specialist role."""
    a = Agent(
        user_id=user.id, name='Gamma', is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def team_setup(app, authenticated_client, user, supervisor, worker, specialist):
    """Set up roles and team rules for the 3-agent team."""
    # Assign roles
    authenticated_client.post('/api/team/roles', json={
        'agent_id': supervisor.id, 'role': 'supervisor',
    })
    authenticated_client.post('/api/team/roles', json={
        'agent_id': worker.id, 'role': 'worker',
    })
    authenticated_client.post('/api/team/roles', json={
        'agent_id': specialist.id, 'role': 'specialist',
    })

    # Configure team rules: require supervisor, allow peer assignment
    authenticated_client.post('/api/team/rules', json={
        'require_supervisor_for_tasks': True,
        'allow_peer_assignment': True,
        'default_supervisor_agent_id': supervisor.id,
    })

    return {'supervisor': supervisor, 'worker': worker, 'specialist': specialist}


@pytest.fixture
def other_workspace(app):
    """A completely separate workspace (user + agent) for isolation tests."""
    u = User(
        email='outsider@example.com', created_at=datetime.utcnow(),
        credit_balance=10, subscription_tier='free',
        subscription_status='inactive',
    )
    db.session.add(u)
    db.session.commit()

    a = Agent(
        user_id=u.id, name='Outsider', is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return {'user': u, 'agent': a}


# ---------------------------------------------------------------------------
# E2E Scenario 1: Full Task Lifecycle (create → start → complete)
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2ETaskLifecycle:
    """Complete task lifecycle: supervisor creates, worker executes, messages flow."""

    @patch('core.observability.ingestion.emit_event')
    def test_full_task_lifecycle(
        self, mock_emit, authenticated_client, user,
        supervisor, worker, team_setup,
    ):
        """Supervisor creates task → worker starts → sends messages → completes."""
        # 1. Supervisor creates a task for worker
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Analyze Q4 report',
            'assigned_to_agent_id': worker.id,
            'created_by_agent_id': supervisor.id,
            'input': {'report_url': 'https://example.com/q4.pdf'},
            'priority': 8,
        })
        assert resp.status_code == 201
        task_id = resp.get_json()['task']['id']

        # 2. Worker starts the task
        resp = authenticated_client.post(f'/api/tasks/{task_id}/start')
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'running'

        # 3. Worker sends a progress message on the task thread
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Starting analysis of Q4 data...',
            'from_agent_id': worker.id,
            'to_agent_id': supervisor.id,
            'task_id': task_id,
            'role': 'agent',
        })
        assert resp.status_code == 201

        # 4. Supervisor replies with guidance
        resp = authenticated_client.post('/api/messages', json={
            'content': 'Focus on revenue trends',
            'from_agent_id': supervisor.id,
            'to_agent_id': worker.id,
            'task_id': task_id,
            'role': 'agent',
        })
        assert resp.status_code == 201

        # 5. Worker completes the task with output
        resp = authenticated_client.post(f'/api/tasks/{task_id}/complete', json={
            'output': {'summary': 'Revenue up 15% QoQ', 'charts': 3},
        })
        assert resp.status_code == 200
        completed = resp.get_json()['task']
        assert completed['status'] == 'completed'
        assert completed['output']['summary'] == 'Revenue up 15% QoQ'

        # 6. Verify full event trail
        resp = authenticated_client.get(f'/api/tasks/{task_id}')
        events = resp.get_json()['task']['events']
        event_types = [e['event_type'] for e in events]
        assert event_types == ['created', 'started', 'completed']

        # 7. Verify messages on the task thread
        resp = authenticated_client.get(f'/api/messages?task_id={task_id}')
        assert resp.get_json()['count'] == 2

        # 8. Verify observability events were emitted
        assert mock_emit.call_count == 2  # started + completed
        call_types = [c[1]['event_type'] for c in mock_emit.call_args_list]
        assert 'action_started' in call_types
        assert 'action_finished' in call_types


# ---------------------------------------------------------------------------
# E2E Scenario 2: Delegation Chain with Escalation
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2EDelegationChain:
    """Task delegation from supervisor → worker → specialist, then escalation back."""

    def test_delegation_and_escalation(
        self, authenticated_client, user,
        supervisor, worker, specialist, team_setup,
    ):
        """Supervisor delegates → worker sub-delegates → specialist escalates back."""
        # 1. Supervisor creates a parent task for worker
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Build dashboard widget',
            'assigned_to_agent_id': worker.id,
            'created_by_agent_id': supervisor.id,
        })
        assert resp.status_code == 201
        parent_id = resp.get_json()['task']['id']

        # 2. Worker creates a subtask for specialist (peer assignment is enabled)
        worker_role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=worker.id,
        ).first()
        worker_role.can_assign_to_peers = True
        db.session.commit()

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Design chart component',
            'assigned_to_agent_id': specialist.id,
            'created_by_agent_id': worker.id,
            'parent_task_id': parent_id,
        })
        assert resp.status_code == 201
        sub_id = resp.get_json()['task']['id']

        # 3. Verify delegation chain via parent_task_id filter
        resp = authenticated_client.get(f'/api/tasks?parent_task_id={parent_id}')
        assert resp.get_json()['count'] == 1
        assert resp.get_json()['tasks'][0]['id'] == sub_id

        # 4. Specialist starts subtask, then escalates to supervisor
        authenticated_client.post(f'/api/tasks/{sub_id}/start')
        resp = authenticated_client.post(f'/api/tasks/{sub_id}/assign', json={
            'assigned_to_agent_id': supervisor.id,
        })
        assert resp.status_code == 200
        assert resp.get_json()['task']['assigned_to_agent_id'] == supervisor.id
        # Running task resets to queued on reassignment
        assert resp.get_json()['task']['status'] == 'queued'

        # 5. Verify escalation was logged in governance audit
        audits = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_escalated',
        ).all()
        assert len(audits) == 1
        assert audits[0].details['to_agent_id'] == supervisor.id

        # 6. Verify reassignment was also logged
        reassign_audits = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_reassigned',
        ).all()
        assert len(reassign_audits) == 1


# ---------------------------------------------------------------------------
# E2E Scenario 3: Risk-Blocked Task with Recovery
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2ERiskBlocking:
    """Task gets blocked by risk policy, then recovered after resolution."""

    @patch('core.observability.ingestion.emit_event')
    def test_risk_block_and_recovery(
        self, mock_emit, app, authenticated_client, user, worker, team_setup,
    ):
        """Task blocked by risk → risk resolved → task starts successfully."""
        # 1. Create a risk policy and pending event for the worker
        policy = RiskPolicy(
            workspace_id=user.id,
            agent_id=worker.id,
            policy_type='daily_spend_cap',
            threshold_value=100.0,
            action_type='pause_agent',
            cooldown_minutes=60,
            is_enabled=True,
        )
        db.session.add(policy)
        db.session.commit()

        risk_event = RiskEvent(
            uid=str(uuid.uuid4()),
            policy_id=policy.id,
            workspace_id=user.id,
            agent_id=worker.id,
            policy_type='daily_spend_cap',
            breach_value=150.0,
            threshold_value=100.0,
            action_type='pause_agent',
            status='pending',
            evaluated_at=datetime.utcnow(),
        )
        db.session.add(risk_event)
        db.session.commit()

        # 2. Create a task for the at-risk worker
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Process payments',
            'assigned_to_agent_id': worker.id,
        })
        task_id = resp.get_json()['task']['id']

        # 3. Try to start — should be blocked
        resp = authenticated_client.post(f'/api/tasks/{task_id}/start')
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['blocked'] is True
        assert data['task']['status'] == 'blocked'

        # 4. Verify blocked event in task events
        events = TaskEvent.query.filter_by(task_id=task_id, event_type='blocked').all()
        assert len(events) == 1

        # 5. Verify governance audit logged the block
        audit = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_blocked',
        ).first()
        assert audit is not None
        assert audit.details['task_id'] == task_id

        # 6. Resolve the risk event
        risk_event.status = 'executed'
        db.session.commit()

        # 7. Retry start — should succeed now (blocked → running)
        resp = authenticated_client.post(f'/api/tasks/{task_id}/start')
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'running'

        # 8. Complete the task
        resp = authenticated_client.post(f'/api/tasks/{task_id}/complete', json={
            'output': {'payments_processed': 42},
        })
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'completed'

        # 9. Verify observability: started + completed (not the blocked attempt)
        obs_calls = [c[1]['event_type'] for c in mock_emit.call_args_list]
        assert 'action_started' in obs_calls
        assert 'action_finished' in obs_calls


# ---------------------------------------------------------------------------
# E2E Scenario 4: Hierarchy Enforcement
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2EHierarchyEnforcement:
    """Team hierarchy rules are enforced across task creation and reassignment."""

    def test_worker_cannot_assign_to_peers_without_permission(
        self, authenticated_client, user, worker, specialist, team_setup,
    ):
        """Worker without can_assign_to_peers cannot delegate to specialist."""
        # Worker's default can_assign_to_peers = False
        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=worker.id,
        ).first()
        role.can_assign_to_peers = False
        db.session.commit()

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Peer task',
            'assigned_to_agent_id': specialist.id,
            'created_by_agent_id': worker.id,
        })
        assert resp.status_code == 403

    def test_worker_can_escalate_to_supervisor(
        self, authenticated_client, user, worker, supervisor, team_setup,
    ):
        """Worker can escalate (create task for) supervisor."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Need supervisor review',
            'assigned_to_agent_id': supervisor.id,
            'created_by_agent_id': worker.id,
        })
        assert resp.status_code == 201
        assert resp.get_json()['task']['assigned_to_agent_id'] == supervisor.id

    def test_supervisor_can_assign_to_anyone(
        self, authenticated_client, supervisor, worker, specialist, team_setup,
    ):
        """Supervisor can assign tasks to both worker and specialist."""
        for target in [worker, specialist]:
            resp = authenticated_client.post('/api/tasks', json={
                'title': f'Task for {target.name}',
                'assigned_to_agent_id': target.id,
                'created_by_agent_id': supervisor.id,
            })
            assert resp.status_code == 201

    def test_human_created_tasks_bypass_role_checks(
        self, authenticated_client, worker, specialist, team_setup,
    ):
        """Tasks created by users (no created_by_agent_id) always succeed."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Human override',
            'assigned_to_agent_id': specialist.id,
        })
        assert resp.status_code == 201

    def test_team_summary_shows_all_roles(
        self, authenticated_client, user, team_setup,
    ):
        """Team summary endpoint correctly groups agents by role."""
        resp = authenticated_client.get('/api/team/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['supervisors']) == 1
        assert len(data['workers']) == 1
        assert len(data['specialists']) == 1


# ---------------------------------------------------------------------------
# E2E Scenario 5: Messaging Across Contexts
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2EMessaging:
    """Messages flow within task threads, free threads, and across agents."""

    def test_task_thread_and_free_thread_isolation(
        self, authenticated_client, user, supervisor, worker, team_setup,
    ):
        """Task-linked messages and free-thread messages don't mix."""
        # Create a task
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Thread isolation test',
            'assigned_to_agent_id': worker.id,
        })
        task_id = resp.get_json()['task']['id']

        # Send 2 messages on the task thread
        for i in range(2):
            authenticated_client.post('/api/messages', json={
                'content': f'Task msg {i}',
                'from_agent_id': worker.id,
                'task_id': task_id,
                'role': 'agent',
            })

        # Send 3 messages on a free thread
        free_thread = str(uuid.uuid4())
        for i in range(3):
            authenticated_client.post('/api/messages', json={
                'content': f'Free msg {i}',
                'from_agent_id': supervisor.id,
                'to_agent_id': worker.id,
                'thread_id': free_thread,
                'role': 'agent',
            })

        # Verify isolation
        resp = authenticated_client.get(f'/api/messages?task_id={task_id}')
        assert resp.get_json()['count'] == 2

        resp = authenticated_client.get(f'/api/messages?thread_id={free_thread}')
        assert resp.get_json()['count'] == 3

    def test_multi_agent_task_conversation(
        self, authenticated_client, user, supervisor, worker, specialist, team_setup,
    ):
        """Three agents can all post messages on the same task thread."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Team discussion task',
            'assigned_to_agent_id': worker.id,
        })
        task_id = resp.get_json()['task']['id']

        for agent_fixture in [supervisor, worker, specialist]:
            authenticated_client.post('/api/messages', json={
                'content': f'{agent_fixture.name} checking in',
                'from_agent_id': agent_fixture.id,
                'task_id': task_id,
                'role': 'agent',
            })

        resp = authenticated_client.get(f'/api/messages?task_id={task_id}')
        messages = resp.get_json()['messages']
        assert len(messages) == 3
        senders = {m['from_agent_id'] for m in messages}
        assert senders == {supervisor.id, worker.id, specialist.id}

    def test_user_can_participate_in_task_thread(
        self, authenticated_client, user, worker, team_setup,
    ):
        """User can send messages on a task thread alongside agents."""
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'User participation task',
            'assigned_to_agent_id': worker.id,
        })
        task_id = resp.get_json()['task']['id']

        # Agent message
        authenticated_client.post('/api/messages', json={
            'content': 'Agent update',
            'from_agent_id': worker.id,
            'task_id': task_id,
            'role': 'agent',
        })

        # User message
        authenticated_client.post('/api/messages', json={
            'content': 'Human feedback',
            'to_agent_id': worker.id,
            'task_id': task_id,
            'role': 'user',
        })

        resp = authenticated_client.get(f'/api/messages?task_id={task_id}')
        messages = resp.get_json()['messages']
        assert len(messages) == 2
        roles = {m['role'] for m in messages}
        assert roles == {'agent', 'user'}


# ---------------------------------------------------------------------------
# E2E Scenario 6: Workspace Isolation
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2EWorkspaceIsolation:
    """Tasks, messages, and team config from one workspace are invisible to another."""

    def test_cross_workspace_task_invisible(
        self, app, authenticated_client, user, worker,
        team_setup, other_workspace,
    ):
        """Tasks, messages, and roles from another workspace are completely isolated."""
        # Create task in our workspace
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Our task',
            'assigned_to_agent_id': worker.id,
        })
        assert resp.status_code == 201
        our_task_id = resp.get_json()['task']['id']

        # Create task directly in other workspace via DB
        foreign_task = CollaborationTask(
            id=str(uuid.uuid4()),
            workspace_id=other_workspace['user'].id,
            created_by_user_id=other_workspace['user'].id,
            assigned_to_agent_id=other_workspace['agent'].id,
            title='Foreign task',
            status='queued',
        )
        db.session.add(foreign_task)
        db.session.commit()

        # Our listing should only show our task
        resp = authenticated_client.get('/api/tasks')
        task_ids = [t['id'] for t in resp.get_json()['tasks']]
        assert our_task_id in task_ids
        assert foreign_task.id not in task_ids

        # Cannot access foreign task directly
        resp = authenticated_client.get(f'/api/tasks/{foreign_task.id}')
        assert resp.status_code == 404

        # Cannot start foreign task
        resp = authenticated_client.post(f'/api/tasks/{foreign_task.id}/start')
        assert resp.status_code == 404

    def test_cross_workspace_message_invisible(
        self, app, authenticated_client, user, worker,
        team_setup, other_workspace,
    ):
        """Messages from another workspace are not accessible."""
        thread = str(uuid.uuid4())

        # Foreign message in DB
        msg = AgentMessage(
            workspace_id=other_workspace['user'].id,
            from_agent_id=other_workspace['agent'].id,
            thread_id=thread,
            role='agent',
            content='Secret foreign msg',
        )
        db.session.add(msg)
        db.session.commit()

        # Our user cannot see it
        resp = authenticated_client.get(f'/api/messages?thread_id={thread}')
        assert resp.get_json()['count'] == 0

    def test_cross_workspace_team_isolated(
        self, authenticated_client, team_setup, other_workspace,
    ):
        """Team roles and rules are scoped to workspace."""
        # Our workspace has 3 roles
        resp = authenticated_client.get('/api/team/summary')
        data = resp.get_json()
        total = (
            len(data['supervisors'])
            + len(data['workers'])
            + len(data['specialists'])
        )
        assert total == 3

        # Cannot assign role to foreign agent
        resp = authenticated_client.post('/api/team/roles', json={
            'agent_id': other_workspace['agent'].id,
            'role': 'worker',
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# E2E Scenario 7: Failure Path with Governance Trail
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2EFailurePath:
    """Task failure with complete governance and observability trail."""

    @patch('core.observability.ingestion.emit_event')
    def test_task_failure_full_trail(
        self, mock_emit, authenticated_client, user, worker, team_setup,
    ):
        """Task starts → fails → full event + observability + audit trail."""
        # Create and start task
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Risky operation',
            'assigned_to_agent_id': worker.id,
            'priority': 10,
        })
        task_id = resp.get_json()['task']['id']
        authenticated_client.post(f'/api/tasks/{task_id}/start')

        # Fail the task with a reason
        resp = authenticated_client.post(f'/api/tasks/{task_id}/fail', json={
            'reason': 'API rate limit exceeded',
            'output': {'error_code': 429},
        })
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'failed'

        # Verify task events: created → started → failed
        resp = authenticated_client.get(f'/api/tasks/{task_id}')
        event_types = [e['event_type'] for e in resp.get_json()['task']['events']]
        assert event_types == ['created', 'started', 'failed']

        # Verify failure event payload has reason
        fail_event = TaskEvent.query.filter_by(
            task_id=task_id, event_type='failed',
        ).first()
        assert 'rate limit' in fail_event.payload.get('reason', '').lower()

        # Verify observability emitted started + error
        obs_types = [c[1]['event_type'] for c in mock_emit.call_args_list]
        assert 'action_started' in obs_types
        assert 'error' in obs_types


# ---------------------------------------------------------------------------
# E2E Scenario 8: Cancel and Re-create Pattern
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2ECancelAndRecreate:
    """Cancel a task and re-create it for a different agent."""

    def test_cancel_and_reassign_pattern(
        self, authenticated_client, user, supervisor, worker, specialist, team_setup,
    ):
        """Task assigned to worker → canceled → new task for specialist."""
        # Create for worker
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Data extraction',
            'assigned_to_agent_id': worker.id,
        })
        task_id = resp.get_json()['task']['id']

        # Cancel it
        resp = authenticated_client.post(f'/api/tasks/{task_id}/cancel')
        assert resp.status_code == 200
        assert resp.get_json()['task']['status'] == 'canceled'

        # Cannot start a canceled task
        resp = authenticated_client.post(f'/api/tasks/{task_id}/start')
        assert resp.status_code == 409

        # Create a replacement task for specialist
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Data extraction (retry)',
            'assigned_to_agent_id': specialist.id,
            'input': {'attempt': 2},
        })
        assert resp.status_code == 201
        new_id = resp.get_json()['task']['id']
        assert new_id != task_id

        # New task can proceed normally
        resp = authenticated_client.post(f'/api/tasks/{new_id}/start')
        assert resp.status_code == 200
        resp = authenticated_client.post(f'/api/tasks/{new_id}/complete')
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# E2E Scenario 9: Concurrent Tasks Across Agents
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2EConcurrentTasks:
    """Multiple tasks running in parallel across agents."""

    def test_parallel_task_execution(
        self, authenticated_client, user, supervisor, worker, specialist, team_setup,
    ):
        """Three agents each have a running task simultaneously."""
        task_ids = {}
        for name, agent_fixture in [
            ('supervisor', supervisor),
            ('worker', worker),
            ('specialist', specialist),
        ]:
            resp = authenticated_client.post('/api/tasks', json={
                'title': f'{name} parallel task',
                'assigned_to_agent_id': agent_fixture.id,
            })
            task_ids[name] = resp.get_json()['task']['id']
            authenticated_client.post(f'/api/tasks/{task_ids[name]}/start')

        # Verify all 3 are running
        resp = authenticated_client.get('/api/tasks?status=running')
        assert resp.get_json()['count'] == 3

        # Complete them in reverse order
        for name in ['specialist', 'worker', 'supervisor']:
            resp = authenticated_client.post(
                f'/api/tasks/{task_ids[name]}/complete',
            )
            assert resp.status_code == 200

        # All completed
        resp = authenticated_client.get('/api/tasks?status=completed')
        assert resp.get_json()['count'] == 3

        resp = authenticated_client.get('/api/tasks?status=running')
        assert resp.get_json()['count'] == 0

    def test_filter_tasks_by_agent(
        self, authenticated_client, user, supervisor, worker, specialist, team_setup,
    ):
        """Tasks can be filtered by assigned agent."""
        for agent_fixture in [worker, worker, specialist]:
            authenticated_client.post('/api/tasks', json={
                'title': f'Task for {agent_fixture.name}',
                'assigned_to_agent_id': agent_fixture.id,
            })

        resp = authenticated_client.get(f'/api/tasks?assigned_to={worker.id}')
        assert resp.get_json()['count'] == 2

        resp = authenticated_client.get(f'/api/tasks?assigned_to={specialist.id}')
        assert resp.get_json()['count'] == 1


# ---------------------------------------------------------------------------
# E2E Scenario 10: Team Configuration Changes
# ---------------------------------------------------------------------------

@pytest.mark.collaboration
class TestE2ETeamConfiguration:
    """Team rules and role changes affect subsequent task operations."""

    def test_enable_then_disable_hierarchy(
        self, authenticated_client, user, worker, specialist, team_setup,
    ):
        """Disabling hierarchy enforcement allows previously blocked assignments."""
        # With hierarchy on: worker can't assign to specialist (no peer permission)
        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=worker.id,
        ).first()
        role.can_assign_to_peers = False
        db.session.commit()

        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Blocked by hierarchy',
            'assigned_to_agent_id': specialist.id,
            'created_by_agent_id': worker.id,
        })
        assert resp.status_code == 403

        # Disable hierarchy enforcement
        authenticated_client.post('/api/team/rules', json={
            'require_supervisor_for_tasks': False,
        })

        # Now the same assignment succeeds
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Allowed without hierarchy',
            'assigned_to_agent_id': specialist.id,
            'created_by_agent_id': worker.id,
        })
        assert resp.status_code == 201

    def test_role_removal_affects_escalation_audit(
        self, authenticated_client, user, supervisor, worker, team_setup,
    ):
        """Removing supervisor role stops escalation audit entries."""
        # Create task assigned to worker
        resp = authenticated_client.post('/api/tasks', json={
            'title': 'Escalation audit test',
            'assigned_to_agent_id': worker.id,
        })
        task_id = resp.get_json()['task']['id']

        # Remove supervisor role
        sup_role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=supervisor.id,
        ).first()
        authenticated_client.post(f'/api/team/roles/{sup_role.id}/delete')

        # Reassign to former supervisor — should NOT log escalation
        authenticated_client.post(f'/api/tasks/{task_id}/assign', json={
            'assigned_to_agent_id': supervisor.id,
        })

        escalations = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_escalated',
        ).count()
        assert escalations == 0

        # But reassignment audit should still exist
        reassignments = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='task_reassigned',
        ).count()
        assert reassignments == 1
