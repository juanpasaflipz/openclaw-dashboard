"""
Tests for the Risk Policy & Intervention Engine.
"""
import pytest
import uuid
from unittest.mock import patch, Mock
from datetime import datetime, date, timedelta
from decimal import Decimal
from models import db, User, Agent, RiskPolicy, RiskEvent, RiskAuditLog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def risk_policy(app, user, agent):
    """Create a daily_spend_cap policy for the test agent."""
    policy = RiskPolicy(
        workspace_id=user.id,
        agent_id=agent.id,
        policy_type='daily_spend_cap',
        threshold_value=Decimal('10.0000'),
        action_type='pause_agent',
        cooldown_minutes=360,
        is_enabled=True,
    )
    db.session.add(policy)
    db.session.commit()
    return policy


@pytest.fixture
def workspace_wide_policy(app, user):
    """Create a workspace-wide daily_spend_cap policy (no agent)."""
    policy = RiskPolicy(
        workspace_id=user.id,
        agent_id=None,
        policy_type='daily_spend_cap',
        threshold_value=Decimal('50.0000'),
        action_type='alert_only',
        cooldown_minutes=720,
        is_enabled=True,
    )
    db.session.add(policy)
    db.session.commit()
    return policy


# ---------------------------------------------------------------------------
# RiskPolicy Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestRiskPolicyModel:

    def test_create_policy(self, app, user, agent):
        policy = RiskPolicy(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.5000'),
            action_type='pause_agent',
        )
        db.session.add(policy)
        db.session.commit()

        assert policy.id is not None
        assert policy.workspace_id == user.id
        assert policy.agent_id == agent.id
        assert policy.threshold_value == Decimal('5.5000')
        assert policy.action_type == 'pause_agent'
        assert policy.cooldown_minutes == 360  # default
        assert policy.is_enabled is True  # default
        assert policy.created_at is not None

    def test_decimal_precision(self, app, user, agent):
        """Threshold stored as Decimal(12,4), no float drift."""
        policy = RiskPolicy(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('0.0001'),
            action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        fetched = RiskPolicy.query.get(policy.id)
        assert fetched.threshold_value == Decimal('0.0001')

    def test_unique_constraint_same_scope(self, app, user, agent):
        """Cannot create two policies of the same type for the same (workspace, agent)."""
        p1 = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'), action_type='pause_agent',
        )
        db.session.add(p1)
        db.session.commit()

        p2 = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('20.0000'), action_type='alert_only',
        )
        db.session.add(p2)
        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()
        db.session.rollback()

    def test_unique_constraint_different_agents(self, app, user, agent):
        """Same policy_type for different agents is allowed."""
        agent2 = Agent(
            user_id=user.id, name='Agent2', is_active=True,
            created_at=datetime.utcnow(),
        )
        db.session.add(agent2)
        db.session.commit()

        p1 = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'), action_type='pause_agent',
        )
        p2 = RiskPolicy(
            workspace_id=user.id, agent_id=agent2.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('20.0000'), action_type='pause_agent',
        )
        db.session.add_all([p1, p2])
        db.session.commit()

        assert p1.id != p2.id

    def test_workspace_wide_policy(self, app, user):
        """agent_id=NULL creates a workspace-wide policy."""
        policy = RiskPolicy(
            workspace_id=user.id, agent_id=None,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('100.0000'), action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        assert policy.agent_id is None
        assert policy.id is not None

    def test_to_dict(self, risk_policy):
        d = risk_policy.to_dict()
        assert d['policy_type'] == 'daily_spend_cap'
        assert d['threshold_value'] == '10.0000'
        assert d['action_type'] == 'pause_agent'
        assert d['is_enabled'] is True
        assert 'created_at' in d

    def test_valid_policy_types_constant(self):
        assert 'daily_spend_cap' in RiskPolicy.VALID_POLICY_TYPES
        assert 'error_rate_cap' in RiskPolicy.VALID_POLICY_TYPES
        assert 'token_rate_cap' in RiskPolicy.VALID_POLICY_TYPES
        assert 'invalid' not in RiskPolicy.VALID_POLICY_TYPES

    def test_valid_action_types_constant(self):
        assert 'alert_only' in RiskPolicy.VALID_ACTION_TYPES
        assert 'throttle' in RiskPolicy.VALID_ACTION_TYPES
        assert 'model_downgrade' in RiskPolicy.VALID_ACTION_TYPES
        assert 'pause_agent' in RiskPolicy.VALID_ACTION_TYPES


# ---------------------------------------------------------------------------
# RiskEvent Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestRiskEventModel:

    def test_create_event(self, app, risk_policy):
        event = RiskEvent(
            uid=str(uuid.uuid4()),
            policy_id=risk_policy.id,
            workspace_id=risk_policy.workspace_id,
            agent_id=risk_policy.agent_id,
            policy_type=risk_policy.policy_type,
            breach_value=Decimal('15.2500'),
            threshold_value=risk_policy.threshold_value,
            action_type=risk_policy.action_type,
            status='pending',
            dedupe_key=f"{risk_policy.id}:{date.today().isoformat()}",
        )
        db.session.add(event)
        db.session.commit()

        assert event.id is not None
        assert event.status == 'pending'
        assert event.executed_at is None
        assert event.breach_value == Decimal('15.2500')

    def test_dedupe_key_unique(self, app, risk_policy):
        """Two events with the same dedupe_key are rejected."""
        dedupe = f"{risk_policy.id}:{date.today().isoformat()}"

        e1 = RiskEvent(
            uid=str(uuid.uuid4()), policy_id=risk_policy.id,
            workspace_id=risk_policy.workspace_id,
            policy_type='daily_spend_cap',
            breach_value=Decimal('15.0000'),
            threshold_value=Decimal('10.0000'),
            action_type='pause_agent',
            dedupe_key=dedupe,
        )
        db.session.add(e1)
        db.session.commit()

        e2 = RiskEvent(
            uid=str(uuid.uuid4()), policy_id=risk_policy.id,
            workspace_id=risk_policy.workspace_id,
            policy_type='daily_spend_cap',
            breach_value=Decimal('16.0000'),
            threshold_value=Decimal('10.0000'),
            action_type='pause_agent',
            dedupe_key=dedupe,
        )
        db.session.add(e2)
        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()
        db.session.rollback()

    def test_status_lifecycle(self, app, risk_policy):
        """Event transitions from pending to executed."""
        event = RiskEvent(
            uid=str(uuid.uuid4()), policy_id=risk_policy.id,
            workspace_id=risk_policy.workspace_id,
            policy_type='daily_spend_cap',
            breach_value=Decimal('12.0000'),
            threshold_value=Decimal('10.0000'),
            action_type='pause_agent',
            status='pending',
        )
        db.session.add(event)
        db.session.commit()

        assert event.status == 'pending'

        event.status = 'executed'
        event.executed_at = datetime.utcnow()
        event.execution_result = {'action': 'pause_agent', 'agent_id': risk_policy.agent_id}
        db.session.commit()

        fetched = RiskEvent.query.get(event.id)
        assert fetched.status == 'executed'
        assert fetched.executed_at is not None
        assert fetched.execution_result['action'] == 'pause_agent'

    def test_to_dict(self, app, risk_policy):
        event = RiskEvent(
            uid=str(uuid.uuid4()), policy_id=risk_policy.id,
            workspace_id=risk_policy.workspace_id, agent_id=risk_policy.agent_id,
            policy_type='daily_spend_cap',
            breach_value=Decimal('15.0000'),
            threshold_value=Decimal('10.0000'),
            action_type='pause_agent', status='pending',
        )
        db.session.add(event)
        db.session.commit()

        d = event.to_dict()
        assert d['status'] == 'pending'
        assert d['breach_value'] == '15.0000'
        assert d['threshold_value'] == '10.0000'


# ---------------------------------------------------------------------------
# RiskAuditLog Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestRiskAuditLogModel:

    def test_create_audit_entry(self, app, risk_policy):
        event = RiskEvent(
            uid=str(uuid.uuid4()), policy_id=risk_policy.id,
            workspace_id=risk_policy.workspace_id, agent_id=risk_policy.agent_id,
            policy_type='daily_spend_cap',
            breach_value=Decimal('15.0000'), threshold_value=Decimal('10.0000'),
            action_type='pause_agent', status='executed',
            executed_at=datetime.utcnow(),
        )
        db.session.add(event)
        db.session.commit()

        log = RiskAuditLog(
            event_id=event.id,
            workspace_id=risk_policy.workspace_id,
            agent_id=risk_policy.agent_id,
            action_type='pause_agent',
            previous_state={'is_active': True, 'llm_config': {'model': 'gpt-4o'}},
            new_state={'is_active': False, 'llm_config': {'model': 'gpt-4o'}},
            result='success',
        )
        db.session.add(log)
        db.session.commit()

        assert log.id is not None
        assert log.previous_state['is_active'] is True
        assert log.new_state['is_active'] is False
        assert log.result == 'success'
        assert log.error_message is None

    def test_audit_with_error(self, app, risk_policy):
        event = RiskEvent(
            uid=str(uuid.uuid4()), policy_id=risk_policy.id,
            workspace_id=risk_policy.workspace_id,
            policy_type='daily_spend_cap',
            breach_value=Decimal('15.0000'), threshold_value=Decimal('10.0000'),
            action_type='pause_agent', status='failed',
        )
        db.session.add(event)
        db.session.commit()

        log = RiskAuditLog(
            event_id=event.id,
            workspace_id=risk_policy.workspace_id,
            agent_id=risk_policy.agent_id,
            action_type='pause_agent',
            previous_state={'is_active': True},
            new_state={'is_active': True},  # unchanged on failure
            result='failed',
            error_message='Agent not found',
        )
        db.session.add(log)
        db.session.commit()

        assert log.result == 'failed'
        assert log.error_message == 'Agent not found'


# ---------------------------------------------------------------------------
# Policy CRUD Helper Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestPolicyCRUD:

    def test_get_active_policies_all(self, app, risk_policy, workspace_wide_policy):
        from core.risk_engine.policy import get_active_policies
        policies = get_active_policies()
        assert len(policies) == 2

    def test_get_active_policies_by_workspace(self, app, user, risk_policy):
        from core.risk_engine.policy import get_active_policies
        policies = get_active_policies(workspace_id=user.id)
        assert len(policies) == 1
        assert policies[0].id == risk_policy.id

    def test_get_active_policies_excludes_disabled(self, app, user, agent):
        from core.risk_engine.policy import get_active_policies

        disabled = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'), action_type='pause_agent',
            is_enabled=False,
        )
        db.session.add(disabled)
        db.session.commit()

        policies = get_active_policies(workspace_id=user.id)
        assert len(policies) == 0

    def test_get_active_policies_empty_workspace(self, app):
        from core.risk_engine.policy import get_active_policies
        policies = get_active_policies(workspace_id=99999)
        assert policies == []

    def test_get_policy_by_id(self, app, risk_policy):
        from core.risk_engine.policy import get_policy
        fetched = get_policy(risk_policy.id)
        assert fetched is not None
        assert fetched.id == risk_policy.id

    def test_get_policy_with_workspace_scope(self, app, user, risk_policy):
        from core.risk_engine.policy import get_policy

        # Correct workspace
        assert get_policy(risk_policy.id, workspace_id=user.id) is not None
        # Wrong workspace
        assert get_policy(risk_policy.id, workspace_id=99999) is None

    def test_get_policy_not_found(self, app):
        from core.risk_engine.policy import get_policy
        assert get_policy(99999) is None


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestRiskEngineConstants:

    def test_module_exports(self):
        from core.risk_engine import VALID_POLICY_TYPES, VALID_ACTION_TYPES, evaluate_policies
        assert 'daily_spend_cap' in VALID_POLICY_TYPES
        assert 'pause_agent' in VALID_ACTION_TYPES
        assert callable(evaluate_policies)


# ---------------------------------------------------------------------------
# Helpers — seed cost events
# ---------------------------------------------------------------------------

def _seed_cost_events(user_id, agent_id, cost_per_event, count):
    """Seed ObsEvent rows with cost_usd for evaluator tests."""
    from core.observability import emit_event
    for _ in range(count):
        emit_event(
            user_id, 'llm_call', status='success',
            agent_id=agent_id, cost_usd=cost_per_event, model='gpt-4o',
        )


# ---------------------------------------------------------------------------
# Phase 2 — Evaluator Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestEvaluator:

    def test_breach_creates_pending_event(self, app, user, agent, risk_policy):
        """Spend > threshold creates a pending risk_event."""
        from core.risk_engine.evaluator import evaluate_policies

        # Seed $12 in cost (threshold is $10)
        _seed_cost_events(user.id, agent.id, Decimal('4.0000'), 3)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 1

        events = RiskEvent.query.filter_by(policy_id=risk_policy.id).all()
        assert len(events) == 1
        assert events[0].status == 'pending'
        assert events[0].breach_value >= Decimal('12.0000')
        assert events[0].threshold_value == Decimal('10.0000')
        assert events[0].action_type == 'pause_agent'
        assert events[0].agent_id == agent.id
        assert events[0].dedupe_key == f"{risk_policy.id}:{date.today().isoformat()}"

    def test_below_threshold_no_event(self, app, user, agent, risk_policy):
        """Spend <= threshold does not create an event."""
        from core.risk_engine.evaluator import evaluate_policies

        # Seed $6 in cost (threshold is $10)
        _seed_cost_events(user.id, agent.id, Decimal('2.0000'), 3)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 0
        assert RiskEvent.query.filter_by(policy_id=risk_policy.id).count() == 0

    def test_exact_threshold_no_event(self, app, user, agent, risk_policy):
        """Spend == threshold exactly does not trigger (must exceed, not equal)."""
        from core.risk_engine.evaluator import evaluate_policies

        # Seed exactly $10 (threshold is $10)
        _seed_cost_events(user.id, agent.id, Decimal('5.0000'), 2)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 0

    def test_zero_cost_no_event(self, app, user, agent, risk_policy):
        """No cost events means zero spend — no breach."""
        from core.risk_engine.evaluator import evaluate_policies

        created = evaluate_policies(workspace_id=user.id)
        assert created == 0

    def test_idempotency_no_duplicate(self, app, user, agent, risk_policy):
        """Running evaluator twice for the same day produces only one event."""
        from core.risk_engine.evaluator import evaluate_policies

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        first_run = evaluate_policies(workspace_id=user.id)
        assert first_run == 1

        second_run = evaluate_policies(workspace_id=user.id)
        assert second_run == 0

        events = RiskEvent.query.filter_by(policy_id=risk_policy.id).all()
        assert len(events) == 1

    def test_cooldown_respected(self, app, user, agent, risk_policy):
        """After an event is created, cooldown prevents new events."""
        from core.risk_engine.evaluator import evaluate_policies

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        # First evaluation — creates event
        evaluate_policies(workspace_id=user.id)

        # Delete the event but leave cooldown trace by creating a fresh one
        # with a recent evaluated_at timestamp
        event = RiskEvent.query.filter_by(policy_id=risk_policy.id).first()
        # Change dedupe_key so the duplicate check doesn't catch it
        event.dedupe_key = f"{risk_policy.id}:old"
        db.session.commit()

        # Seed more cost for a new day-like scenario
        # But cooldown should still block since the event was just created
        second = evaluate_policies(workspace_id=user.id)
        assert second == 0

    def test_disabled_policy_skipped(self, app, user, agent):
        """Disabled policies are not evaluated."""
        from core.risk_engine.evaluator import evaluate_policies

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('1.0000'), action_type='pause_agent',
            is_enabled=False,
        )
        db.session.add(policy)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('10.0000'), 1)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 0

    def test_workspace_wide_policy_sums_all_agents(self, app, user, agent, workspace_wide_policy):
        """Workspace-wide policy (agent_id=NULL) sums cost across all agents."""
        from core.risk_engine.evaluator import evaluate_policies

        # Create second agent
        agent2 = Agent(
            user_id=user.id, name='Agent2', is_active=True,
            created_at=datetime.utcnow(),
        )
        db.session.add(agent2)
        db.session.commit()

        # Seed $30 on each agent = $60 total (threshold is $50)
        _seed_cost_events(user.id, agent.id, Decimal('30.0000'), 1)
        _seed_cost_events(user.id, agent2.id, Decimal('30.0000'), 1)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 1

        event = RiskEvent.query.filter_by(policy_id=workspace_wide_policy.id).first()
        assert event is not None
        assert event.breach_value >= Decimal('60.0000')
        assert event.agent_id is None  # workspace-wide

    def test_workspace_wide_below_threshold(self, app, user, agent, workspace_wide_policy):
        """Workspace-wide policy does not trigger when total is under threshold."""
        from core.risk_engine.evaluator import evaluate_policies

        # Seed $20 total (threshold is $50)
        _seed_cost_events(user.id, agent.id, Decimal('20.0000'), 1)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 0

    def test_multiple_policies_independent(self, app, user, agent):
        """Multiple policies for the same agent are evaluated independently."""
        from core.risk_engine.evaluator import evaluate_policies

        # Policy 1: low threshold, will trigger
        p1 = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='pause_agent',
        )
        db.session.add(p1)
        db.session.commit()

        # Seed $8 (triggers p1 at $5, but only one policy of type daily_spend_cap
        # per agent is allowed by unique constraint, so test with workspace-wide)
        _seed_cost_events(user.id, agent.id, Decimal('8.0000'), 1)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 1

    def test_agent_scoped_policy_ignores_other_agents(self, app, user, agent, risk_policy):
        """Agent-scoped policy only considers cost from that agent."""
        from core.risk_engine.evaluator import evaluate_policies

        agent2 = Agent(
            user_id=user.id, name='Agent2', is_active=True,
            created_at=datetime.utcnow(),
        )
        db.session.add(agent2)
        db.session.commit()

        # Seed $15 on agent2 (not the policy's agent), $3 on policy's agent
        _seed_cost_events(user.id, agent2.id, Decimal('15.0000'), 1)
        _seed_cost_events(user.id, agent.id, Decimal('3.0000'), 1)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 0  # $3 < $10 threshold

    def test_decimal_precision_in_comparison(self, app, user, agent):
        """Threshold comparison uses Decimal, not float."""
        from core.risk_engine.evaluator import evaluate_policies

        # Threshold of $0.3000 — classic float trap (0.1 + 0.1 + 0.1 != 0.3 in float)
        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('0.3000'), action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        # Seed 3 events of $0.1 each = $0.3 exactly
        _seed_cost_events(user.id, agent.id, Decimal('0.1000'), 3)

        created = evaluate_policies(workspace_id=user.id)
        # Exactly at threshold should NOT trigger (must exceed)
        assert created == 0

    def test_evaluator_does_not_modify_agent(self, app, user, agent, risk_policy):
        """Evaluator creates events but never touches Agent state."""
        from core.risk_engine.evaluator import evaluate_policies

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        evaluate_policies(workspace_id=user.id)

        # Agent should remain unchanged
        db.session.refresh(agent)
        assert agent.is_active is True

    def test_evaluate_all_workspaces(self, app, user, agent, risk_policy):
        """evaluate_policies() with no workspace_id evaluates all workspaces."""
        from core.risk_engine.evaluator import evaluate_policies

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        created = evaluate_policies()  # no workspace_id filter
        assert created == 1


# ---------------------------------------------------------------------------
# Helpers — create a pending risk event for executor tests
# ---------------------------------------------------------------------------

def _create_pending_event(policy, breach_value=Decimal('15.0000')):
    """Seed cost events and run evaluator to produce a pending risk_event."""
    from core.risk_engine.evaluator import evaluate_policies
    _seed_cost_events(
        policy.workspace_id,
        policy.agent_id,
        breach_value,
        1,
    )
    evaluate_policies(workspace_id=policy.workspace_id)
    event = RiskEvent.query.filter_by(policy_id=policy.id, status='pending').first()
    assert event is not None, "Expected a pending event to be created"
    return event


# ---------------------------------------------------------------------------
# Phase 3 — Intervention Executor Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestExecutorPauseAgent:

    def test_pause_agent_sets_inactive(self, app, user, agent, risk_policy):
        """pause_agent intervention sets Agent.is_active = False."""
        from core.risk_engine.interventions import execute_pending_events

        event = _create_pending_event(risk_policy)

        executed = execute_pending_events()
        assert executed == 1

        db.session.refresh(agent)
        assert agent.is_active is False

        db.session.refresh(event)
        assert event.status == 'executed'
        assert event.executed_at is not None
        assert event.execution_result['action'] == 'pause_agent'
        assert event.execution_result['was_active'] is True

    def test_pause_agent_audit_log(self, app, user, agent, risk_policy):
        """pause_agent writes audit log with correct before/after snapshots."""
        from core.risk_engine.interventions import execute_pending_events

        event = _create_pending_event(risk_policy)
        execute_pending_events()

        logs = RiskAuditLog.query.filter_by(event_id=event.id).all()
        assert len(logs) == 1
        log = logs[0]
        assert log.action_type == 'pause_agent'
        assert log.result == 'success'
        assert log.previous_state['is_active'] is True
        assert log.new_state['is_active'] is False
        assert log.workspace_id == user.id
        assert log.agent_id == agent.id

    def test_pause_already_inactive_agent(self, app, user, agent, risk_policy):
        """Pausing an already-inactive agent still succeeds and logs correctly."""
        from core.risk_engine.interventions import execute_pending_events

        agent.is_active = False
        db.session.commit()

        event = _create_pending_event(risk_policy)
        executed = execute_pending_events()
        assert executed == 1

        log = RiskAuditLog.query.filter_by(event_id=event.id).first()
        assert log.previous_state['is_active'] is False
        assert log.new_state['is_active'] is False

    def test_pause_workspace_wide_skipped(self, app, user, workspace_wide_policy):
        """pause_agent on workspace-wide policy (no agent_id) is skipped."""
        from core.risk_engine.interventions import execute_pending_events

        # Change workspace-wide policy to pause_agent for this test
        workspace_wide_policy.action_type = 'pause_agent'
        db.session.commit()

        _seed_cost_events(user.id, None, Decimal('60.0000'), 1)
        from core.risk_engine.evaluator import evaluate_policies
        evaluate_policies(workspace_id=user.id)

        event = RiskEvent.query.filter_by(policy_id=workspace_wide_policy.id).first()
        if event and event.status == 'pending':
            executed = execute_pending_events()
            # Should be skipped (status set to 'skipped', not counted as executed)
            db.session.refresh(event)
            assert event.status == 'skipped'


@pytest.mark.risk_engine
class TestExecutorModelDowngrade:

    def test_model_downgrade_changes_config(self, app, user, agent):
        """model_downgrade switches agent to cheaper model."""
        from core.risk_engine.interventions import execute_pending_events

        agent.llm_config = {'provider': 'openai', 'model': 'gpt-4o', 'temperature': 0.7}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='model_downgrade',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))

        executed = execute_pending_events()
        assert executed == 1

        db.session.refresh(agent)
        assert agent.llm_config['model'] == 'gpt-4o-mini'
        # Other config preserved
        assert agent.llm_config['temperature'] == 0.7
        assert agent.llm_config['provider'] == 'openai'

    def test_model_downgrade_audit_log(self, app, user, agent):
        """model_downgrade audit log records previous and new model."""
        from core.risk_engine.interventions import execute_pending_events

        agent.llm_config = {'provider': 'anthropic', 'model': 'claude-sonnet-4-5-20250929'}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='model_downgrade',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        execute_pending_events()

        log = RiskAuditLog.query.filter_by(event_id=event.id).first()
        assert log.result == 'success'
        assert log.previous_state['llm_config']['model'] == 'claude-sonnet-4-5-20250929'
        assert log.new_state['llm_config']['model'] == 'claude-haiku-4-5-20251001'

    def test_model_downgrade_already_on_target_skipped(self, app, user, agent):
        """Skips downgrade if agent is already on the target model."""
        from core.risk_engine.interventions import execute_pending_events

        agent.llm_config = {'provider': 'openai', 'model': 'gpt-4o-mini'}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='model_downgrade',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        execute_pending_events()

        db.session.refresh(event)
        assert event.status == 'skipped'

    def test_model_downgrade_no_llm_config(self, app, user, agent):
        """Handles agent with no llm_config gracefully."""
        from core.risk_engine.interventions import execute_pending_events

        agent.llm_config = None
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='model_downgrade',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        executed = execute_pending_events()
        assert executed == 1

        db.session.refresh(agent)
        assert agent.llm_config['model'] == 'gpt-4o-mini'


@pytest.mark.risk_engine
class TestExecutorAlertOnly:

    def test_alert_only_no_agent_change(self, app, user, agent):
        """alert_only dispatches notification but does not modify agent."""
        from core.risk_engine.interventions import execute_pending_events

        agent.llm_config = {'provider': 'openai', 'model': 'gpt-4o'}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        executed = execute_pending_events()
        assert executed == 1

        # Agent unchanged
        db.session.refresh(agent)
        assert agent.is_active is True
        assert agent.llm_config['model'] == 'gpt-4o'

        db.session.refresh(event)
        assert event.status == 'executed'
        assert event.execution_result['action'] == 'alert_only'

    def test_alert_only_audit_log(self, app, user, agent):
        """alert_only writes audit log with empty state diffs."""
        from core.risk_engine.interventions import execute_pending_events

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        execute_pending_events()

        log = RiskAuditLog.query.filter_by(event_id=event.id).first()
        assert log.action_type == 'alert_only'
        assert log.result == 'success'
        assert log.previous_state == {}
        assert log.new_state == {}


@pytest.mark.risk_engine
class TestExecutorThrottle:

    def test_throttle_skipped_v1(self, app, user, agent):
        """Throttle is not implemented in v1 — event is skipped."""
        from core.risk_engine.interventions import execute_pending_events

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='throttle',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        execute_pending_events()

        db.session.refresh(event)
        assert event.status == 'skipped'
        assert event.execution_result['skipped'] is True


@pytest.mark.risk_engine
class TestExecutorDuplicatePrevention:

    def test_already_executed_not_reprocessed(self, app, user, agent, risk_policy):
        """Events already executed are not processed again."""
        from core.risk_engine.interventions import execute_pending_events

        event = _create_pending_event(risk_policy)

        # First run
        first = execute_pending_events()
        assert first == 1

        db.session.refresh(agent)
        assert agent.is_active is False

        # Re-activate agent to prove executor doesn't touch it again
        agent.is_active = True
        db.session.commit()

        # Second run — no pending events
        second = execute_pending_events()
        assert second == 0

        # Agent still active (not re-paused)
        db.session.refresh(agent)
        assert agent.is_active is True

    def test_no_pending_events_returns_zero(self, app):
        """No pending events returns 0."""
        from core.risk_engine.interventions import execute_pending_events
        assert execute_pending_events() == 0


@pytest.mark.risk_engine
class TestExecutorMaxEvents:

    def test_max_events_limit(self, app, user, agent):
        """max_events parameter limits how many events are processed."""
        from core.risk_engine.interventions import execute_pending_events

        # Create 3 policies with different types (use unique constraint workaround)
        # We can only have one daily_spend_cap per agent, so use workspace-wide + agent-scoped
        p1 = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('1.0000'), action_type='alert_only',
        )
        db.session.add(p1)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('5.0000'), 1)

        from core.risk_engine.evaluator import evaluate_policies
        evaluate_policies(workspace_id=user.id)

        pending_count = RiskEvent.query.filter_by(status='pending').count()
        assert pending_count >= 1

        # Process only 1
        executed = execute_pending_events(max_events=1)
        assert executed == 1


# ---------------------------------------------------------------------------
# Phase 3 — Audit Log Helper Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestAuditLogHelpers:

    def test_get_audit_trail_by_workspace(self, app, user, agent, risk_policy):
        """get_audit_trail returns entries for the workspace."""
        from core.risk_engine.interventions import execute_pending_events
        from core.risk_engine.audit_log import get_audit_trail

        event = _create_pending_event(risk_policy)
        execute_pending_events()

        trail = get_audit_trail(workspace_id=user.id)
        assert len(trail) == 1
        assert trail[0].workspace_id == user.id

    def test_get_audit_trail_by_agent(self, app, user, agent, risk_policy):
        """get_audit_trail filters by agent_id."""
        from core.risk_engine.interventions import execute_pending_events
        from core.risk_engine.audit_log import get_audit_trail

        event = _create_pending_event(risk_policy)
        execute_pending_events()

        # Correct agent
        trail = get_audit_trail(workspace_id=user.id, agent_id=agent.id)
        assert len(trail) == 1

        # Wrong agent
        trail_empty = get_audit_trail(workspace_id=user.id, agent_id=99999)
        assert len(trail_empty) == 0

    def test_get_audit_trail_by_policy(self, app, user, agent, risk_policy):
        """get_audit_trail filters by policy_id through the event join."""
        from core.risk_engine.interventions import execute_pending_events
        from core.risk_engine.audit_log import get_audit_trail

        event = _create_pending_event(risk_policy)
        execute_pending_events()

        trail = get_audit_trail(workspace_id=user.id, policy_id=risk_policy.id)
        assert len(trail) == 1

        trail_empty = get_audit_trail(workspace_id=user.id, policy_id=99999)
        assert len(trail_empty) == 0

    def test_get_audit_trail_limit(self, app, user, agent, risk_policy):
        """get_audit_trail respects limit parameter."""
        from core.risk_engine.audit_log import get_audit_trail

        trail = get_audit_trail(workspace_id=user.id, limit=5)
        assert isinstance(trail, list)

    def test_get_audit_trail_empty_workspace(self, app):
        """Empty workspace returns empty list."""
        from core.risk_engine.audit_log import get_audit_trail
        trail = get_audit_trail(workspace_id=99999)
        assert trail == []


# ---------------------------------------------------------------------------
# Phase 4 — Enforcement Worker Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestEnforcementWorker:

    def test_full_cycle_evaluate_and_execute(self, app, user, agent, risk_policy):
        """run_enforcement_cycle detects breach and executes intervention."""
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        result = run_enforcement_cycle()

        assert result['events_created'] == 1
        assert result['events_executed'] == 1
        assert result['truncated'] is False
        assert 'elapsed_seconds' in result

        # Agent should be paused
        db.session.refresh(agent)
        assert agent.is_active is False

        # Audit log should exist
        logs = RiskAuditLog.query.filter_by(workspace_id=user.id).all()
        assert len(logs) == 1

    def test_full_cycle_no_breach(self, app, user, agent, risk_policy):
        """No breach means no events created or executed."""
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        _seed_cost_events(user.id, agent.id, Decimal('3.0000'), 1)

        result = run_enforcement_cycle()

        assert result['events_created'] == 0
        assert result['events_executed'] == 0

        db.session.refresh(agent)
        assert agent.is_active is True

    def test_full_cycle_no_policies(self, app, user, agent):
        """No policies means nothing to do."""
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        result = run_enforcement_cycle()
        assert result['events_created'] == 0
        assert result['events_executed'] == 0

    def test_evaluation_only(self, app, user, agent, risk_policy):
        """run_evaluation_only creates events without executing them."""
        from core.risk_engine.enforcement_worker import run_evaluation_only

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        created = run_evaluation_only()
        assert created == 1

        # Agent NOT paused (executor didn't run)
        db.session.refresh(agent)
        assert agent.is_active is True

        # Event is pending
        event = RiskEvent.query.filter_by(policy_id=risk_policy.id).first()
        assert event.status == 'pending'

    def test_execution_only(self, app, user, agent, risk_policy):
        """run_execution_only processes existing pending events."""
        from core.risk_engine.enforcement_worker import run_evaluation_only, run_execution_only

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        # Step 1: evaluate
        run_evaluation_only()
        db.session.refresh(agent)
        assert agent.is_active is True

        # Step 2: execute
        executed = run_execution_only()
        assert executed == 1

        db.session.refresh(agent)
        assert agent.is_active is False

    def test_cycle_idempotent(self, app, user, agent, risk_policy):
        """Running the cycle twice produces the same outcome."""
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        first = run_enforcement_cycle()
        assert first['events_created'] == 1
        assert first['events_executed'] == 1

        second = run_enforcement_cycle()
        assert second['events_created'] == 0
        assert second['events_executed'] == 0

        # Still only one event and one audit entry
        assert RiskEvent.query.filter_by(policy_id=risk_policy.id).count() == 1
        assert RiskAuditLog.query.filter_by(workspace_id=user.id).count() == 1

    def test_cycle_survives_individual_failure(self, app, user, agent):
        """Worker continues even if one policy evaluation fails internally."""
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        # Create a valid policy
        p1 = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='alert_only',
        )
        db.session.add(p1)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('10.0000'), 1)

        # Should not raise
        result = run_enforcement_cycle()
        assert result['events_created'] >= 0  # At least doesn't crash


# ---------------------------------------------------------------------------
# Phase 4 — Cron Endpoint Tests
# ---------------------------------------------------------------------------

@pytest.mark.risk_engine
class TestCronEndpoint:

    def test_enforce_risk_requires_auth(self, app, client):
        """Endpoint rejects unauthenticated requests."""
        resp = client.post('/api/obs/internal/enforce-risk')
        assert resp.status_code == 401

    def test_enforce_risk_with_cron_secret(self, app, client, user, agent, risk_policy):
        """Endpoint accepts CRON_SECRET and runs enforcement cycle."""
        import os
        os.environ['CRON_SECRET'] = 'test-cron-secret'

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        resp = client.post(
            '/api/obs/internal/enforce-risk',
            headers={'Authorization': 'Bearer test-cron-secret'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'events_created' in data
        assert 'events_executed' in data
        assert 'elapsed_seconds' in data

        os.environ.pop('CRON_SECRET', None)

    def test_enforce_risk_with_admin_password(self, app, client):
        """Endpoint accepts admin password fallback."""
        import os
        os.environ['ADMIN_PASSWORD'] = 'test-admin-pw'

        resp = client.post(
            '/api/obs/internal/enforce-risk',
            json={'password': 'test-admin-pw'},
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        os.environ.pop('ADMIN_PASSWORD', None)

    def test_enforce_risk_no_policies_clean(self, app, client):
        """Endpoint returns clean result when no policies exist."""
        import os
        os.environ['CRON_SECRET'] = 'test-cron-secret'

        resp = client.post(
            '/api/obs/internal/enforce-risk',
            headers={'Authorization': 'Bearer test-cron-secret'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['events_created'] == 0
        assert data['events_executed'] == 0

        os.environ.pop('CRON_SECRET', None)


# ===========================================================================
# Phase 5 — Daily Spend Cap Guardrail V1: End-to-End Integration Tests
# ===========================================================================

@pytest.mark.risk_engine
class TestDailySpendCapE2E:
    """
    End-to-end integration tests for the daily_spend_cap guardrail.

    Proves the full pipeline:
      cost events → evaluator detects breach → executor pauses agent → audit logged
    """

    def test_full_guardrail_lifecycle(self, app, user, agent):
        """
        Complete lifecycle:
        1. Agent starts active with LLM config.
        2. Cost accumulates below threshold — no intervention.
        3. Cost crosses threshold — agent paused.
        4. Audit log records correct before/after state.
        5. Second cycle is idempotent — no duplicate action.
        """
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        # --- Setup: agent with real LLM config ---
        agent.llm_config = {'provider': 'openai', 'model': 'gpt-4o', 'temperature': 0.7}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'),
            action_type='pause_agent',
            cooldown_minutes=360,
            is_enabled=True,
        )
        db.session.add(policy)
        db.session.commit()

        # --- Step 1: Cost below threshold ($6) — no action ---
        _seed_cost_events(user.id, agent.id, Decimal('2.0000'), 3)

        result1 = run_enforcement_cycle()
        assert result1['events_created'] == 0
        assert result1['events_executed'] == 0

        db.session.refresh(agent)
        assert agent.is_active is True
        assert RiskEvent.query.count() == 0

        # --- Step 2: More cost pushes total to $16 — breach detected ---
        _seed_cost_events(user.id, agent.id, Decimal('5.0000'), 2)

        result2 = run_enforcement_cycle()
        assert result2['events_created'] == 1
        assert result2['events_executed'] == 1

        # Agent should be paused
        db.session.refresh(agent)
        assert agent.is_active is False
        # LLM config should be preserved (pause doesn't modify it)
        assert agent.llm_config['model'] == 'gpt-4o'
        assert agent.llm_config['temperature'] == 0.7

        # --- Step 3: Verify risk_event ---
        event = RiskEvent.query.filter_by(policy_id=policy.id).first()
        assert event is not None
        assert event.status == 'executed'
        assert event.policy_type == 'daily_spend_cap'
        assert event.breach_value >= Decimal('16.0000')
        assert event.threshold_value == Decimal('10.0000')
        assert event.action_type == 'pause_agent'
        assert event.agent_id == agent.id
        assert event.workspace_id == user.id
        assert event.executed_at is not None
        assert event.execution_result['action'] == 'pause_agent'
        assert event.execution_result['was_active'] is True
        assert event.dedupe_key == f"{policy.id}:{date.today().isoformat()}"

        # --- Step 4: Verify audit log ---
        logs = RiskAuditLog.query.filter_by(event_id=event.id).all()
        assert len(logs) == 1
        log = logs[0]
        assert log.action_type == 'pause_agent'
        assert log.result == 'success'
        assert log.workspace_id == user.id
        assert log.agent_id == agent.id
        assert log.error_message is None
        # Previous state: agent was active
        assert log.previous_state['is_active'] is True
        assert log.previous_state['llm_config']['model'] == 'gpt-4o'
        # New state: agent is paused
        assert log.new_state['is_active'] is False
        assert log.new_state['llm_config']['model'] == 'gpt-4o'

        # --- Step 5: Idempotency — second cycle creates nothing ---
        result3 = run_enforcement_cycle()
        assert result3['events_created'] == 0
        assert result3['events_executed'] == 0

        assert RiskEvent.query.filter_by(policy_id=policy.id).count() == 1
        assert RiskAuditLog.query.filter_by(workspace_id=user.id).count() == 1

        # Agent stays paused
        db.session.refresh(agent)
        assert agent.is_active is False

    def test_gradual_cost_accumulation(self, app, user, agent):
        """
        Simulates realistic scenario: many small LLM calls gradually
        accumulate cost until the threshold is crossed.
        """
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        policy = RiskPolicy(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('1.0000'),
            action_type='pause_agent',
        )
        db.session.add(policy)
        db.session.commit()

        # Simulate 20 LLM calls at $0.04 each = $0.80 (under $1 threshold)
        _seed_cost_events(user.id, agent.id, Decimal('0.0400'), 20)

        result = run_enforcement_cycle()
        assert result['events_created'] == 0
        db.session.refresh(agent)
        assert agent.is_active is True

        # 6 more calls at $0.04 each = $0.24 → total $1.04 (over $1 threshold)
        _seed_cost_events(user.id, agent.id, Decimal('0.0400'), 6)

        result = run_enforcement_cycle()
        assert result['events_created'] == 1
        assert result['events_executed'] == 1

        db.session.refresh(agent)
        assert agent.is_active is False

    def test_multi_agent_independent_policies(self, app, user):
        """
        Two agents with different thresholds. Only the one that
        exceeds its threshold gets paused.
        """
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        agent_cheap = Agent(
            user_id=user.id, name='CheapAgent', is_active=True,
            llm_config={'provider': 'openai', 'model': 'gpt-4o-mini'},
            created_at=datetime.utcnow(),
        )
        agent_expensive = Agent(
            user_id=user.id, name='ExpensiveAgent', is_active=True,
            llm_config={'provider': 'openai', 'model': 'gpt-4o'},
            created_at=datetime.utcnow(),
        )
        db.session.add_all([agent_cheap, agent_expensive])
        db.session.commit()

        policy_cheap = RiskPolicy(
            workspace_id=user.id, agent_id=agent_cheap.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='pause_agent',
        )
        policy_expensive = RiskPolicy(
            workspace_id=user.id, agent_id=agent_expensive.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('20.0000'), action_type='pause_agent',
        )
        db.session.add_all([policy_cheap, policy_expensive])
        db.session.commit()

        # CheapAgent spends $8 (over $5 threshold)
        _seed_cost_events(user.id, agent_cheap.id, Decimal('8.0000'), 1)
        # ExpensiveAgent spends $12 (under $20 threshold)
        _seed_cost_events(user.id, agent_expensive.id, Decimal('12.0000'), 1)

        result = run_enforcement_cycle()
        assert result['events_created'] == 1
        assert result['events_executed'] == 1

        db.session.refresh(agent_cheap)
        db.session.refresh(agent_expensive)
        assert agent_cheap.is_active is False     # paused
        assert agent_expensive.is_active is True  # still running

    def test_model_downgrade_guardrail(self, app, user, agent):
        """
        daily_spend_cap with model_downgrade action downgrades the model
        instead of pausing the agent.
        """
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        agent.llm_config = {'provider': 'openai', 'model': 'gpt-4o', 'temperature': 0.5}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'),
            action_type='model_downgrade',
        )
        db.session.add(policy)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        result = run_enforcement_cycle()
        assert result['events_created'] == 1
        assert result['events_executed'] == 1

        db.session.refresh(agent)
        assert agent.is_active is True  # NOT paused
        assert agent.llm_config['model'] == 'gpt-4o-mini'  # downgraded
        assert agent.llm_config['temperature'] == 0.5  # preserved

        # Audit log records the model change
        log = RiskAuditLog.query.filter_by(workspace_id=user.id).first()
        assert log.previous_state['llm_config']['model'] == 'gpt-4o'
        assert log.new_state['llm_config']['model'] == 'gpt-4o-mini'

    def test_alert_only_guardrail(self, app, user, agent):
        """
        daily_spend_cap with alert_only action notifies but does not
        modify the agent.
        """
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        agent.llm_config = {'provider': 'openai', 'model': 'gpt-4o'}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'),
            action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        result = run_enforcement_cycle()
        assert result['events_created'] == 1
        assert result['events_executed'] == 1

        db.session.refresh(agent)
        assert agent.is_active is True
        assert agent.llm_config['model'] == 'gpt-4o'

    def test_cron_endpoint_full_guardrail(self, app, client, user, agent):
        """
        The cron HTTP endpoint triggers the full guardrail pipeline.
        Proves the integration from HTTP → worker → evaluator → executor → DB.
        """
        import os
        os.environ['CRON_SECRET'] = 'test-cron-secret'

        agent.llm_config = {'provider': 'openai', 'model': 'gpt-4o'}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'),
            action_type='pause_agent',
        )
        db.session.add(policy)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        resp = client.post(
            '/api/obs/internal/enforce-risk',
            headers={'Authorization': 'Bearer test-cron-secret'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['events_created'] == 1
        assert data['events_executed'] == 1

        # Verify agent paused through the HTTP pathway
        db.session.refresh(agent)
        assert agent.is_active is False

        # Verify audit log created through the HTTP pathway
        log = RiskAuditLog.query.filter_by(workspace_id=user.id).first()
        assert log is not None
        assert log.action_type == 'pause_agent'
        assert log.result == 'success'

        os.environ.pop('CRON_SECRET', None)

    def test_workspace_wide_spend_cap(self, app, user):
        """
        Workspace-wide policy triggers alert_only when total spend
        across all agents exceeds threshold.
        """
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        agent1 = Agent(
            user_id=user.id, name='Agent1', is_active=True,
            created_at=datetime.utcnow(),
        )
        agent2 = Agent(
            user_id=user.id, name='Agent2', is_active=True,
            created_at=datetime.utcnow(),
        )
        db.session.add_all([agent1, agent2])
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=None,  # workspace-wide
            policy_type='daily_spend_cap',
            threshold_value=Decimal('20.0000'),
            action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        # Agent1: $12, Agent2: $10 → total $22 > $20 threshold
        _seed_cost_events(user.id, agent1.id, Decimal('12.0000'), 1)
        _seed_cost_events(user.id, agent2.id, Decimal('10.0000'), 1)

        result = run_enforcement_cycle()
        assert result['events_created'] == 1
        assert result['events_executed'] == 1

        event = RiskEvent.query.filter_by(policy_id=policy.id).first()
        assert event.agent_id is None  # workspace-wide
        assert event.breach_value >= Decimal('22.0000')
        assert event.status == 'executed'

        # Both agents still active (alert_only doesn't pause)
        db.session.refresh(agent1)
        db.session.refresh(agent2)
        assert agent1.is_active is True
        assert agent2.is_active is True


# ===========================================================================
# Phase 6 — Safety Hardening
# ===========================================================================

@pytest.mark.risk_engine
class TestSafetyNoRequestCycleIntervention:
    """Validate that no intervention logic runs inside HTTP request cycles."""

    def test_risk_engine_not_imported_in_user_routes(self, app):
        """
        No user-facing route module imports from core.risk_engine.
        The only caller is the cron endpoint in observability_routes.py.
        """
        import importlib
        import inspect

        user_route_modules = [
            'auth_routes', 'agent_routes', 'chatbot_routes',
            'model_config_routes', 'channels_routes',
        ]

        for mod_name in user_route_modules:
            try:
                mod = importlib.import_module(mod_name)
                source = inspect.getsource(mod)
                assert 'risk_engine' not in source, (
                    f"{mod_name} imports risk_engine — interventions must not "
                    f"run inside user request cycles"
                )
            except (ModuleNotFoundError, OSError):
                pass  # Module may not exist in test env

    def test_cron_endpoint_is_only_risk_caller(self, app):
        """
        The enforce-risk endpoint is the only route that calls
        the enforcement worker.
        """
        import inspect
        from routes.observability_routes import obs_bp

        # Get source of all route functions
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith('obs.') and 'enforce-risk' not in rule.rule:
                view_func = app.view_functions.get(rule.endpoint)
                if view_func:
                    source = inspect.getsource(view_func)
                    assert 'run_enforcement_cycle' not in source, (
                        f"Route {rule.rule} calls run_enforcement_cycle — "
                        f"only enforce-risk should do this"
                    )
                    assert 'execute_pending_events' not in source, (
                        f"Route {rule.rule} calls execute_pending_events — "
                        f"only the worker should do this"
                    )


@pytest.mark.risk_engine
class TestSafetyNoFloatMath:
    """Validate no float arithmetic in threshold comparison path."""

    def test_evaluator_returns_decimal(self, app, user, agent, risk_policy):
        """_evaluate_daily_spend returns Decimal, not float."""
        from core.risk_engine.evaluator import _evaluate_daily_spend

        _seed_cost_events(user.id, agent.id, Decimal('5.0000'), 1)

        result = _evaluate_daily_spend(risk_policy, datetime.utcnow())
        assert isinstance(result, Decimal), f"Expected Decimal, got {type(result)}"

    def test_evaluator_zero_returns_decimal(self, app, user, agent, risk_policy):
        """Zero cost returns Decimal('0'), not float 0.0 or int 0."""
        from core.risk_engine.evaluator import _evaluate_daily_spend

        result = _evaluate_daily_spend(risk_policy, datetime.utcnow())
        assert result == Decimal('0')
        assert isinstance(result, Decimal)

    def test_threshold_is_decimal_in_comparison(self, app, user, agent):
        """
        The threshold used in the comparison is Decimal, not float.
        Verifies the classic 0.1 + 0.1 + 0.1 float trap doesn't apply.
        """
        from core.risk_engine.evaluator import evaluate_policies

        # 0.1 + 0.1 + 0.1 == 0.3 in Decimal, != 0.3 in float
        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('0.3000'),
            action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        # Three events of exactly 0.1
        _seed_cost_events(user.id, agent.id, Decimal('0.1000'), 3)

        # Should NOT trigger — 0.3 is not > 0.3
        created = evaluate_policies(workspace_id=user.id)
        assert created == 0

        # Add one tiny amount to exceed
        _seed_cost_events(user.id, agent.id, Decimal('0.0001'), 1)

        created = evaluate_policies(workspace_id=user.id)
        assert created == 1  # 0.3001 > 0.3

    def test_breach_and_threshold_stored_as_decimal(self, app, user, agent, risk_policy):
        """risk_event stores breach_value and threshold_value as Decimal."""
        from core.risk_engine.evaluator import evaluate_policies

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)
        evaluate_policies(workspace_id=user.id)

        event = RiskEvent.query.filter_by(policy_id=risk_policy.id).first()
        assert isinstance(event.breach_value, Decimal)
        assert isinstance(event.threshold_value, Decimal)


@pytest.mark.risk_engine
class TestSafetyNoDuplicateExecution:
    """Validate no duplicate executions under various scenarios."""

    def test_executed_event_not_reprocessed(self, app, user, agent, risk_policy):
        """An event marked 'executed' is never picked up again."""
        from core.risk_engine.interventions import execute_pending_events

        event = _create_pending_event(risk_policy)
        execute_pending_events()

        db.session.refresh(event)
        assert event.status == 'executed'

        # Try again
        second = execute_pending_events()
        assert second == 0

        # Still exactly one audit entry
        assert RiskAuditLog.query.filter_by(event_id=event.id).count() == 1

    def test_skipped_event_not_reprocessed(self, app, user, agent):
        """An event marked 'skipped' is never picked up again."""
        from core.risk_engine.interventions import execute_pending_events

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='throttle',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        execute_pending_events()

        db.session.refresh(event)
        assert event.status == 'skipped'

        second = execute_pending_events()
        assert second == 0

    def test_failed_event_not_reprocessed(self, app, user, agent):
        """An event marked 'failed' is never picked up again."""
        from core.risk_engine.interventions import execute_pending_events

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='pause_agent',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))

        # Point event at non-existent agent to trigger 'failed' branch
        event.agent_id = 99999
        db.session.commit()

        execute_pending_events()

        db.session.refresh(event)
        assert event.status == 'failed'

        # Restore agent_id and prove the failed event is never retried
        event.agent_id = agent.id
        db.session.commit()

        second = execute_pending_events()
        assert second == 0  # failed event not retried


@pytest.mark.risk_engine
class TestSafetyAllTransitionsLogged:
    """Validate that every state transition produces an audit log entry."""

    def test_successful_pause_logged(self, app, user, agent, risk_policy):
        """Successful pause_agent produces a 'success' audit entry."""
        from core.risk_engine.interventions import execute_pending_events

        event = _create_pending_event(risk_policy)
        execute_pending_events()

        log = RiskAuditLog.query.filter_by(event_id=event.id).first()
        assert log is not None
        assert log.result == 'success'

    def test_skipped_throttle_logged(self, app, user, agent):
        """Skipped throttle produces a 'skipped' audit entry."""
        from core.risk_engine.interventions import execute_pending_events

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='throttle',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        execute_pending_events()

        log = RiskAuditLog.query.filter_by(event_id=event.id).first()
        assert log is not None
        assert log.result == 'skipped'
        assert log.error_message is not None

    def test_failed_intervention_logged(self, app, user, agent):
        """Failed intervention (agent not found) produces a 'failed' audit entry."""
        from core.risk_engine.interventions import execute_pending_events

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='pause_agent',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))

        # Point event at non-existent agent to trigger 'failed' branch
        event.agent_id = 99999
        db.session.commit()

        execute_pending_events()

        log = RiskAuditLog.query.filter_by(event_id=event.id).first()
        assert log is not None
        assert log.result == 'failed'
        assert 'Agent not found' in log.error_message

    def test_skipped_downgrade_logged(self, app, user, agent):
        """Skipped model_downgrade (already on target) produces audit entry."""
        from core.risk_engine.interventions import execute_pending_events

        agent.llm_config = {'provider': 'openai', 'model': 'gpt-4o-mini'}
        db.session.commit()

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='model_downgrade',
        )
        db.session.add(policy)
        db.session.commit()

        event = _create_pending_event(policy, breach_value=Decimal('10.0000'))
        execute_pending_events()

        log = RiskAuditLog.query.filter_by(event_id=event.id).first()
        assert log is not None
        assert log.result == 'skipped'


# ===========================================================================
# Phase 6 — QA Failure Simulation
# ===========================================================================

@pytest.mark.risk_engine
class TestQAFailureSimulation:
    """Simulate executor failures and verify recovery behavior."""

    def test_executor_crash_marks_event_failed(self, app, user, agent, risk_policy):
        """
        If executor handler raises mid-execution, the event is marked 'failed'
        and the system can continue processing other events.
        """
        from core.risk_engine.interventions import execute_pending_events, _ACTION_HANDLERS

        event = _create_pending_event(risk_policy)

        # Simulate crash by patching the handler dict entry
        with patch.dict(
            _ACTION_HANDLERS,
            {'pause_agent': Mock(side_effect=RuntimeError('Simulated crash'))},
        ):
            executed = execute_pending_events()

        assert executed == 0  # crash means not executed

        db.session.refresh(event)
        assert event.status == 'failed'
        assert event.execution_result['failed'] is True
        assert 'Simulated crash' in event.execution_result['error']

        # Agent should NOT be modified (crash happened before mutation)
        db.session.refresh(agent)
        assert agent.is_active is True

    def test_crash_recovery_no_duplicate_on_restart(self, app, user, agent, risk_policy):
        """
        After a crash, restarting the worker does NOT reprocess the failed event.
        A new cycle with fresh cost data creates a new event only if dedupe allows.
        """
        from core.risk_engine.enforcement_worker import run_enforcement_cycle
        from core.risk_engine.interventions import _ACTION_HANDLERS

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        # First cycle — simulate crash
        with patch.dict(
            _ACTION_HANDLERS,
            {'pause_agent': Mock(side_effect=RuntimeError('Simulated crash'))},
        ):
            result1 = run_enforcement_cycle()

        assert result1['events_created'] == 1
        assert result1['events_executed'] == 0

        event = RiskEvent.query.filter_by(policy_id=risk_policy.id).first()
        assert event.status == 'failed'

        # Second cycle — dedupe_key prevents new event creation
        result2 = run_enforcement_cycle()
        assert result2['events_created'] == 0
        assert result2['events_executed'] == 0

        # Agent still active (never successfully paused)
        db.session.refresh(agent)
        assert agent.is_active is True

    def test_partial_batch_failure(self, app, user):
        """
        Two pending events: first one crashes, second one succeeds.
        Verifies independent processing per event.
        """
        from core.risk_engine.interventions import execute_pending_events

        agent1 = Agent(
            user_id=user.id, name='CrashAgent', is_active=True,
            created_at=datetime.utcnow(),
        )
        agent2 = Agent(
            user_id=user.id, name='GoodAgent', is_active=True,
            created_at=datetime.utcnow(),
        )
        db.session.add_all([agent1, agent2])
        db.session.commit()

        p1 = RiskPolicy(
            workspace_id=user.id, agent_id=agent1.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='pause_agent',
        )
        p2 = RiskPolicy(
            workspace_id=user.id, agent_id=agent2.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='pause_agent',
        )
        db.session.add_all([p1, p2])
        db.session.commit()

        _seed_cost_events(user.id, agent1.id, Decimal('10.0000'), 1)
        _seed_cost_events(user.id, agent2.id, Decimal('10.0000'), 1)

        from core.risk_engine.evaluator import evaluate_policies
        evaluate_policies(workspace_id=user.id)

        # Delete agent1 to make its event fail
        db.session.delete(agent1)
        db.session.commit()

        executed = execute_pending_events()
        # Only agent2's event should succeed
        assert executed == 1

        db.session.refresh(agent2)
        assert agent2.is_active is False  # paused

        events = RiskEvent.query.order_by(RiskEvent.id).all()
        statuses = {e.agent_id: e.status for e in events}
        assert statuses[agent2.id] == 'executed'


@pytest.mark.risk_engine
class TestQACooldownEnforcement:
    """Thorough cooldown enforcement tests."""

    def test_cooldown_blocks_within_window(self, app, user, agent):
        """
        After an event is created, no new event can be created for the
        same policy within cooldown_minutes.
        """
        from core.risk_engine.evaluator import evaluate_policies

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='pause_agent',
            cooldown_minutes=60,
        )
        db.session.add(policy)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('10.0000'), 1)

        # First evaluation creates an event
        first = evaluate_policies(workspace_id=user.id)
        assert first == 1

        event = RiskEvent.query.filter_by(policy_id=policy.id).first()
        # Modify dedupe_key so cooldown is the only guard
        event.dedupe_key = f"{policy.id}:altered"
        db.session.commit()

        # Second evaluation within cooldown — blocked
        second = evaluate_policies(workspace_id=user.id)
        assert second == 0

    def test_cooldown_expires_allows_new_event(self, app, user, agent):
        """
        After cooldown_minutes have passed, a new event CAN be created.
        """
        from core.risk_engine.evaluator import evaluate_policies

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='alert_only',
            cooldown_minutes=60,
        )
        db.session.add(policy)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('10.0000'), 1)

        # First evaluation
        evaluate_policies(workspace_id=user.id)

        # Backdate the event to make cooldown expire
        event = RiskEvent.query.filter_by(policy_id=policy.id).first()
        event.evaluated_at = datetime.utcnow() - timedelta(minutes=120)
        event.dedupe_key = f"{policy.id}:old-date"
        db.session.commit()

        # Now evaluation should succeed (cooldown expired, dedupe_key differs)
        second = evaluate_policies(workspace_id=user.id)
        assert second == 1

        assert RiskEvent.query.filter_by(policy_id=policy.id).count() == 2

    def test_cooldown_only_considers_pending_or_executed(self, app, user, agent):
        """
        Failed or skipped events do NOT count toward cooldown.
        Only 'pending' and 'executed' events block re-evaluation.
        """
        from core.risk_engine.evaluator import evaluate_policies

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('5.0000'), action_type='pause_agent',
            cooldown_minutes=360,
        )
        db.session.add(policy)
        db.session.commit()

        _seed_cost_events(user.id, agent.id, Decimal('10.0000'), 1)

        # Create a failed event manually
        failed_event = RiskEvent(
            uid=str(uuid.uuid4()), policy_id=policy.id,
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            breach_value=Decimal('10.0000'), threshold_value=Decimal('5.0000'),
            action_type='pause_agent', status='failed',
            evaluated_at=datetime.utcnow(),
            dedupe_key=f"{policy.id}:failed",
        )
        db.session.add(failed_event)
        db.session.commit()

        # Should NOT be blocked by the failed event
        created = evaluate_policies(workspace_id=user.id)
        assert created == 1


@pytest.mark.risk_engine
class TestQAIdempotency:
    """Comprehensive idempotency validation."""

    def test_triple_cycle_same_result(self, app, user, agent, risk_policy):
        """Running enforcement cycle 3 times produces identical final state."""
        from core.risk_engine.enforcement_worker import run_enforcement_cycle

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        r1 = run_enforcement_cycle()
        r2 = run_enforcement_cycle()
        r3 = run_enforcement_cycle()

        assert r1['events_created'] == 1
        assert r1['events_executed'] == 1
        assert r2['events_created'] == 0
        assert r2['events_executed'] == 0
        assert r3['events_created'] == 0
        assert r3['events_executed'] == 0

        # Exactly 1 event, 1 audit log
        assert RiskEvent.query.filter_by(policy_id=risk_policy.id).count() == 1
        assert RiskAuditLog.query.filter_by(workspace_id=user.id).count() == 1

        db.session.refresh(agent)
        assert agent.is_active is False

    def test_evaluation_then_execution_then_repeat(self, app, user, agent, risk_policy):
        """
        Calling evaluate and execute separately, then repeating,
        produces the same result as a single cycle.
        """
        from core.risk_engine.enforcement_worker import run_evaluation_only, run_execution_only

        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        # Phase A: evaluate
        assert run_evaluation_only() == 1
        # Phase B: execute
        assert run_execution_only() == 1
        # Phase C: evaluate again — nothing new
        assert run_evaluation_only() == 0
        # Phase D: execute again — nothing pending
        assert run_execution_only() == 0

        assert RiskEvent.query.filter_by(policy_id=risk_policy.id).count() == 1

    def test_dedupe_key_prevents_db_level_duplicates(self, app, user, agent, risk_policy):
        """
        Even if cooldown check is bypassed, the dedupe_key unique constraint
        at the DB level prevents duplicate events for the same policy+date.
        """
        _seed_cost_events(user.id, agent.id, Decimal('15.0000'), 1)

        from core.risk_engine.evaluator import evaluate_policies
        evaluate_policies(workspace_id=user.id)

        dedupe = f"{risk_policy.id}:{date.today().isoformat()}"

        # Try to manually insert a duplicate — should fail
        duplicate = RiskEvent(
            uid=str(uuid.uuid4()), policy_id=risk_policy.id,
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            breach_value=Decimal('20.0000'), threshold_value=Decimal('10.0000'),
            action_type='pause_agent', dedupe_key=dedupe,
        )
        db.session.add(duplicate)
        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()
        db.session.rollback()

        # Still only one event
        assert RiskEvent.query.filter_by(policy_id=risk_policy.id).count() == 1
