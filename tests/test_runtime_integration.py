"""
Phase 3 integration tests — Blueprint → Runtime → Governance pipeline.

Covers:
    - Risk policy seeding from blueprint default_risk_profile.
    - AgentRole seeding from blueprint hierarchy_defaults / role_type.
    - Governance audit trail for blueprint events.
    - End-to-end: create blueprint → instantiate 3 agents → verify
      capability enforcement, risk envelope, and collaboration roles.
    - Policy refresh re-seeds risk policies and roles.
    - Instance removal logging.
"""
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from models import (
    db, User, Agent,
    AgentBlueprint, AgentBlueprintVersion, AgentInstance,
    CapabilityBundle, RiskPolicy, AgentRole,
    GovernanceAuditLog,
)
from core.identity.agent_blueprint import (
    create_blueprint, publish_blueprint,
)
from core.identity.agent_capabilities import (
    create_capability_bundle, resolve_capabilities,
)
from core.identity.agent_instance import (
    instantiate_agent, get_agent_instance,
    refresh_instance_policy, remove_agent_instance,
    _seed_risk_policies, _seed_agent_role,
    _ROLE_TYPE_TO_COLLAB_ROLE,
)
from core.runtime.execution_context import ExecutionContext
from core.runtime.tool_gateway import ToolGateway
from core.runtime.agent_runtime import AgentRuntime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(*args, **kwargs):
    pass


@pytest.fixture(autouse=True)
def _bypass_runtime_infra():
    """Bypass governance tier checks and obs run tracking for runtime tests."""
    with patch.object(AgentRuntime, '_pre_start_check', _noop), \
         patch.object(AgentRuntime, '_start_obs_run', _noop), \
         patch.object(AgentRuntime, '_finish_obs_run', _noop):
        yield


# ---------------------------------------------------------------------------
# Additional fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent2(app, user):
    """Second agent for multi-agent tests."""
    a = Agent(
        user_id=user.id,
        name='Agent-B',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def agent3(app, user):
    """Third agent for multi-agent tests."""
    a = Agent(
        user_id=user.id,
        name='Agent-C',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


# ---------------------------------------------------------------------------
# Risk policy seeding
# ---------------------------------------------------------------------------

class TestRiskPolicySeeding:
    """Verify that blueprint default_risk_profile seeds RiskPolicy rows."""

    def test_instantiation_seeds_daily_spend_cap(self, app, user, agent):
        bp = create_blueprint(user.id, 'Risk BP', user.id, role_type='worker')
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={
                'daily_spend_cap': 50.0,
                'action_type': 'throttle',
                'cooldown_minutes': 120,
            },
        )

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        policies = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).all()
        assert len(policies) == 1
        p = policies[0]
        assert p.policy_type == 'daily_spend_cap'
        assert p.threshold_value == Decimal('50.0')
        assert p.action_type == 'throttle'
        assert p.cooldown_minutes == 120
        assert p.is_enabled is True

    def test_seeds_multiple_policy_types(self, app, user, agent):
        bp = create_blueprint(user.id, 'Multi-Risk', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={
                'daily_spend_cap': 100,
                'error_rate_cap': 0.15,
                'token_rate_cap': 5000,
                'action_type': 'alert_only',
            },
        )

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        policies = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).order_by(RiskPolicy.policy_type).all()
        assert len(policies) == 3
        types = {p.policy_type for p in policies}
        assert types == {'daily_spend_cap', 'error_rate_cap', 'token_rate_cap'}

    def test_no_risk_profile_seeds_nothing(self, app, user, agent):
        bp = create_blueprint(user.id, 'No-Risk', user.id)
        publish_blueprint(bp.id, user.id, user.id)

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        policies = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).all()
        assert len(policies) == 0

    def test_invalid_action_type_defaults_to_alert(self, app, user, agent):
        bp = create_blueprint(user.id, 'Bad Action', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={
                'daily_spend_cap': 10,
                'action_type': 'invalid_action',
            },
        )

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        p = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert p.action_type == 'alert_only'

    def test_default_cooldown_is_360(self, app, user, agent):
        bp = create_blueprint(user.id, 'Default CD', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={'daily_spend_cap': 25},
        )

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        p = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert p.cooldown_minutes == 360

    def test_existing_policy_is_updated(self, app, user, agent):
        """If a risk policy already exists, seeding updates it."""
        existing = RiskPolicy(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10'),
            action_type='alert_only',
            cooldown_minutes=60,
            is_enabled=False,
        )
        db.session.add(existing)
        db.session.commit()

        bp = create_blueprint(user.id, 'Update Risk', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={
                'daily_spend_cap': 200,
                'action_type': 'pause_agent',
                'cooldown_minutes': 30,
            },
        )

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        policies = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).all()
        assert len(policies) == 1
        p = policies[0]
        assert p.threshold_value == Decimal('200')
        assert p.action_type == 'pause_agent'
        assert p.cooldown_minutes == 30
        assert p.is_enabled is True  # re-enabled


# ---------------------------------------------------------------------------
# AgentRole seeding
# ---------------------------------------------------------------------------

class TestAgentRoleSeeding:
    """Verify that blueprint hierarchy_defaults / role_type seeds AgentRole."""

    def test_hierarchy_defaults_sets_role(self, app, user, agent):
        bp = create_blueprint(user.id, 'Supervisor BP', user.id, role_type='supervisor')
        publish_blueprint(
            bp.id, user.id, user.id,
            hierarchy_defaults={
                'role': 'supervisor',
                'can_assign_to_peers': True,
                'can_escalate_to_supervisor': False,
            },
        )

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert role is not None
        assert role.role == 'supervisor'
        assert role.can_assign_to_peers is True
        assert role.can_escalate_to_supervisor is False

    def test_fallback_to_role_type_mapping(self, app, user, agent):
        """When hierarchy_defaults has no role, falls back to blueprint role_type."""
        bp = create_blueprint(user.id, 'Researcher BP', user.id, role_type='researcher')
        publish_blueprint(bp.id, user.id, user.id)

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert role is not None
        assert role.role == 'specialist'  # researcher -> specialist

    def test_executor_maps_to_worker(self, app, user, agent):
        bp = create_blueprint(user.id, 'Executor BP', user.id, role_type='executor')
        publish_blueprint(bp.id, user.id, user.id)

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert role.role == 'worker'

    def test_autonomous_maps_to_worker(self, app, user, agent):
        bp = create_blueprint(user.id, 'Auto BP', user.id, role_type='autonomous')
        publish_blueprint(bp.id, user.id, user.id)

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert role.role == 'worker'

    def test_existing_role_is_updated(self, app, user, agent):
        """If an AgentRole already exists, seeding updates it."""
        existing = AgentRole(
            workspace_id=user.id,
            agent_id=agent.id,
            role='worker',
            can_assign_to_peers=False,
            can_escalate_to_supervisor=True,
        )
        db.session.add(existing)
        db.session.commit()

        bp = create_blueprint(user.id, 'Upgrade Role', user.id, role_type='supervisor')
        publish_blueprint(
            bp.id, user.id, user.id,
            hierarchy_defaults={'role': 'supervisor', 'can_assign_to_peers': True},
        )

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        roles = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).all()
        assert len(roles) == 1
        assert roles[0].role == 'supervisor'
        assert roles[0].can_assign_to_peers is True

    def test_invalid_role_in_defaults_falls_back(self, app, user, agent):
        """An invalid role in hierarchy_defaults falls back to role_type mapping."""
        bp = create_blueprint(user.id, 'Bad Role', user.id, role_type='worker')
        publish_blueprint(
            bp.id, user.id, user.id,
            hierarchy_defaults={'role': 'invalid_role'},
        )

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert role.role == 'worker'

    def test_all_role_type_mappings(self, app):
        """Verify all _ROLE_TYPE_TO_COLLAB_ROLE entries map to valid roles."""
        from models import AgentRole as AR
        for bp_role, collab_role in _ROLE_TYPE_TO_COLLAB_ROLE.items():
            assert collab_role in AR.VALID_ROLES, (
                f'{bp_role} -> {collab_role} is not a valid AgentRole.role'
            )


# ---------------------------------------------------------------------------
# Governance audit logging
# ---------------------------------------------------------------------------

class TestGovernanceAuditTrail:
    """Verify governance events are logged for blueprint lifecycle."""

    def test_publish_logs_governance_event(self, app, user):
        bp = create_blueprint(user.id, 'Audited BP', user.id)
        publish_blueprint(bp.id, user.id, user.id, allowed_tools=['web_search'])

        logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='blueprint_published',
        ).all()
        assert len(logs) == 1
        assert logs[0].details['blueprint_id'] == bp.id
        assert logs[0].details['version'] == 1
        assert logs[0].actor_id == user.id

    def test_instantiation_logs_governance_event(self, app, user, agent):
        bp = create_blueprint(user.id, 'Inst Audit', user.id)
        publish_blueprint(bp.id, user.id, user.id)

        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='instance_created',
        ).all()
        assert len(logs) == 1
        assert logs[0].agent_id == agent.id
        assert logs[0].details['blueprint_id'] == bp.id
        assert logs[0].details['blueprint_version'] == 1
        assert logs[0].actor_id == user.id

    def test_removal_logs_governance_event(self, app, user, agent):
        bp = create_blueprint(user.id, 'Remove Audit', user.id)
        publish_blueprint(bp.id, user.id, user.id)
        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        remove_agent_instance(agent.id, user.id)

        logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='instance_removed',
        ).all()
        assert len(logs) == 1
        assert logs[0].agent_id == agent.id
        assert logs[0].details['blueprint_id'] == bp.id

    def test_refresh_logs_governance_event(self, app, user, agent):
        bp = create_blueprint(user.id, 'Refresh Audit', user.id)
        publish_blueprint(bp.id, user.id, user.id)
        publish_blueprint(bp.id, user.id, user.id, changelog='v2')
        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        refresh_instance_policy(agent.id, user.id, new_version=2)

        logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='instance_refreshed',
        ).all()
        assert len(logs) == 1
        assert logs[0].details['blueprint_version'] == 2
        assert logs[0].details['version_changed'] is True

    def test_multiple_publishes_log_separate_events(self, app, user):
        bp = create_blueprint(user.id, 'Multi Pub', user.id)
        publish_blueprint(bp.id, user.id, user.id, changelog='v1')
        publish_blueprint(bp.id, user.id, user.id, changelog='v2')
        publish_blueprint(bp.id, user.id, user.id, changelog='v3')

        logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='blueprint_published',
        ).all()
        assert len(logs) == 3
        versions = {log.details['version'] for log in logs}
        assert versions == {1, 2, 3}


# ---------------------------------------------------------------------------
# Policy refresh re-seeds risk + role
# ---------------------------------------------------------------------------

class TestRefreshReseeds:
    """Verify that refresh_instance_policy re-seeds artefacts from new version."""

    def test_refresh_updates_risk_policies(self, app, user, agent):
        bp = create_blueprint(user.id, 'Refresh Risk', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={'daily_spend_cap': 50, 'action_type': 'alert_only'},
        )
        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        # Publish v2 with a higher cap and different action
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={
                'daily_spend_cap': 200,
                'error_rate_cap': 0.25,
                'action_type': 'pause_agent',
            },
        )

        refresh_instance_policy(agent.id, user.id, new_version=2)

        policies = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).order_by(RiskPolicy.policy_type).all()
        assert len(policies) == 2
        by_type = {p.policy_type: p for p in policies}
        assert by_type['daily_spend_cap'].threshold_value == Decimal('200')
        assert by_type['daily_spend_cap'].action_type == 'pause_agent'
        assert by_type['error_rate_cap'].threshold_value == Decimal('0.25')

    def test_refresh_updates_role(self, app, user, agent):
        bp = create_blueprint(user.id, 'Refresh Role', user.id, role_type='worker')
        publish_blueprint(
            bp.id, user.id, user.id,
            hierarchy_defaults={'role': 'worker'},
        )
        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        # Publish v2 promoting to supervisor
        publish_blueprint(
            bp.id, user.id, user.id,
            hierarchy_defaults={
                'role': 'supervisor',
                'can_assign_to_peers': True,
            },
        )

        refresh_instance_policy(agent.id, user.id, new_version=2)

        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert role.role == 'supervisor'
        assert role.can_assign_to_peers is True


# ---------------------------------------------------------------------------
# End-to-end integration: 3 agents from same blueprint
# ---------------------------------------------------------------------------

class TestMultiAgentIntegration:
    """Full pipeline: blueprint → 3 agents → capabilities + risk + roles."""

    def test_three_agents_from_one_blueprint(self, app, user, agent, agent2, agent3):
        """Create a supervisor blueprint, instantiate 3 agents, verify everything."""

        # --- Step 1: Create blueprint with capabilities ---
        bp = create_blueprint(
            user.id, 'Team Blueprint', user.id, role_type='supervisor',
        )

        cap = create_capability_bundle(
            workspace_id=user.id,
            name='Core Tools',
            tool_set=['web_search', 'send_email', 'read_file'],
            model_constraints={'allowed_providers': ['openai', 'anthropic']},
        )

        ver = publish_blueprint(
            bp.id, user.id, user.id,
            allowed_tools=['web_search', 'send_email', 'read_file', 'write_file'],
            allowed_models=['openai', 'anthropic', 'google'],
            default_risk_profile={
                'daily_spend_cap': 100,
                'error_rate_cap': 0.1,
                'action_type': 'throttle',
                'cooldown_minutes': 60,
            },
            hierarchy_defaults={
                'role': 'supervisor',
                'can_assign_to_peers': True,
                'can_escalate_to_supervisor': False,
            },
            capability_ids=[cap.id],
        )

        # --- Step 2: Instantiate 3 agents ---
        i1 = instantiate_agent(agent.id, bp.id, 1, user.id, user.id)
        i2 = instantiate_agent(agent2.id, bp.id, 1, user.id, user.id)
        i3 = instantiate_agent(agent3.id, bp.id, 1, user.id, user.id)

        # --- Step 3: Verify capability enforcement ---
        # All 3 should have the same resolved capabilities
        for inst in [i1, i2, i3]:
            snapshot = inst.policy_snapshot
            assert snapshot is not None
            # Tool set = intersection of capability bundle + blueprint ceiling
            tools = set(snapshot.get('allowed_tools', []))
            assert 'web_search' in tools
            assert 'send_email' in tools
            assert 'read_file' in tools
            # Models = intersection of capability bundle + blueprint ceiling
            models = set(snapshot.get('allowed_models', []))
            assert 'openai' in models
            assert 'anthropic' in models

        # --- Step 4: Verify risk policies seeded for all 3 ---
        for agent_obj in [agent, agent2, agent3]:
            policies = RiskPolicy.query.filter_by(
                workspace_id=user.id, agent_id=agent_obj.id,
            ).order_by(RiskPolicy.policy_type).all()
            assert len(policies) == 2  # daily_spend_cap + error_rate_cap
            types = {p.policy_type for p in policies}
            assert types == {'daily_spend_cap', 'error_rate_cap'}
            for p in policies:
                assert p.action_type == 'throttle'
                assert p.cooldown_minutes == 60

        # --- Step 5: Verify roles seeded for all 3 ---
        for agent_obj in [agent, agent2, agent3]:
            role = AgentRole.query.filter_by(
                workspace_id=user.id, agent_id=agent_obj.id,
            ).first()
            assert role is not None
            assert role.role == 'supervisor'
            assert role.can_assign_to_peers is True
            assert role.can_escalate_to_supervisor is False

        # --- Step 6: Verify governance audit trail ---
        pub_logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='blueprint_published',
        ).all()
        assert len(pub_logs) == 1

        inst_logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id, event_type='instance_created',
        ).all()
        assert len(inst_logs) == 3

    def test_runtime_session_enforces_capabilities(self, app, user, agent):
        """Verify ToolGateway denies tools outside agent capabilities."""
        bp = create_blueprint(user.id, 'Restricted RT', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            allowed_tools=['web_search'],
            allowed_models=['openai'],
        )
        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        # Build an ExecutionContext with capabilities
        ctx = ExecutionContext(
            workspace_id=user.id,
            agent_id=agent.id,
        )
        instance = get_agent_instance(agent.id)
        ctx = ctx.with_capabilities(instance.policy_snapshot)

        gw = ToolGateway(ctx)

        # Capability check
        assert gw._check_capability('web_search') is None  # allowed
        denied = gw._check_capability('delete_database')
        assert denied is not None
        assert denied['capability_denied'] is True

        # Model check
        ok, _ = gw.check_model_allowed('openai')
        assert ok is True
        ok, reason = gw.check_model_allowed('cohere')
        assert ok is False
        assert 'cohere' in reason

    def test_runtime_session_loads_capabilities_on_start(self, app, user, agent):
        """Verify AgentRuntime.start_session loads capabilities from instance."""
        bp = create_blueprint(user.id, 'Session BP', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            allowed_tools=['web_search', 'send_email'],
        )
        instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        rt = AgentRuntime(user.id)

        with patch('core.runtime.execution_context.ExecutionContext.create') as mock_create:
            mock_create.return_value = ExecutionContext(
                workspace_id=user.id,
                agent_id=agent.id,
            )
            session = rt.start_session(user.id, agent.id)

        # Session context should have capabilities loaded
        assert session.context.has_capabilities is True
        assert session.context.allowed_tools == {'web_search', 'send_email'}


# ---------------------------------------------------------------------------
# Risk envelope applied via capability snapshot
# ---------------------------------------------------------------------------

class TestRiskEnvelopeFromBlueprint:
    """Verify risk_profile flows through to the policy snapshot."""

    def test_risk_profile_in_snapshot(self, app, user, agent):
        bp = create_blueprint(user.id, 'Risk Snap', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={
                'daily_spend_cap': 75,
                'error_rate_cap': 0.05,
                'action_type': 'model_downgrade',
            },
        )

        inst = instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        risk = inst.policy_snapshot.get('risk_profile', {})
        assert risk.get('daily_spend_cap') == 75
        assert risk.get('error_rate_cap') == 0.05

    def test_capability_bundle_risk_constrains_snapshot(self, app, user, agent):
        """When a capability bundle has tighter risk constraints, snapshot reflects it."""
        cap = create_capability_bundle(
            workspace_id=user.id,
            name='Tight Risk',
            risk_constraints={
                'daily_spend_cap': 20,
                'error_rate_cap': 0.01,
            },
        )

        bp = create_blueprint(user.id, 'Constrained', user.id)
        publish_blueprint(
            bp.id, user.id, user.id,
            default_risk_profile={
                'daily_spend_cap': 100,
                'error_rate_cap': 0.1,
            },
            capability_ids=[cap.id],
        )

        inst = instantiate_agent(agent.id, bp.id, 1, user.id, user.id)

        risk = inst.policy_snapshot.get('risk_profile', {})
        # Should be capped to the bundle's tighter constraints
        assert risk.get('daily_spend_cap') == 20
        assert risk.get('error_rate_cap') == 0.01


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestSeedingEdgeCases:
    """Edge cases for risk policy and role seeding."""

    def test_seed_risk_policies_empty_profile(self, app, user, agent):
        result = _seed_risk_policies(user.id, agent.id, {})
        assert result == []

    def test_seed_risk_policies_none_profile(self, app, user, agent):
        result = _seed_risk_policies(user.id, agent.id, None)
        assert result == []

    def test_seed_role_with_none_defaults(self, app, user, agent):
        """With no hierarchy_defaults, uses blueprint role_type mapping."""
        _seed_agent_role(user.id, agent.id, None, 'researcher')
        db.session.commit()

        role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        assert role.role == 'specialist'

    def test_threshold_stored_as_decimal(self, app, user, agent):
        """Ensure float thresholds are correctly stored as Decimal."""
        _seed_risk_policies(user.id, agent.id, {
            'daily_spend_cap': 99.99,
            'action_type': 'alert_only',
        })
        db.session.commit()

        p = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent.id,
        ).first()
        # Decimal comparison — should not lose precision
        assert float(p.threshold_value) == pytest.approx(99.99)
