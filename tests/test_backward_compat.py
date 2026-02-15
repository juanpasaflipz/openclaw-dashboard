"""
Phase 5 backward compatibility tests — implicit blueprint generation.

Covers:
    - Single agent conversion (generate_implicit_blueprint)
    - Workspace-wide migration (migrate_workspace_agents)
    - Already-managed agents are skipped
    - Wildcard capabilities preserve unrestricted behavior
    - Existing risk policies are NOT modified
    - Existing AgentRole is NOT overwritten
    - LLM config and identity config are captured in blueprint version
    - Role type inference from existing AgentRole and identity_config
    - Governance audit trail for implicit blueprint creation
    - API endpoints (convert single agent, migrate workspace)
"""
import pytest
from datetime import datetime
from decimal import Decimal

from models import (
    db, User, Agent,
    AgentBlueprint, AgentBlueprintVersion, AgentInstance,
    RiskPolicy, AgentRole, GovernanceAuditLog,
)
from core.identity.backward_compat import (
    generate_implicit_blueprint,
    migrate_workspace_agents,
    _infer_role_type,
    _capture_hierarchy_defaults,
)
from core.identity.agent_instance import get_agent_instance
from core.runtime.execution_context import ExecutionContext
from core.runtime.tool_gateway import ToolGateway


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent_with_config(app, user):
    """An agent with LLM and identity config."""
    a = Agent(
        user_id=user.id,
        name='ConfiguredAgent',
        is_active=True,
        created_at=datetime.utcnow(),
        llm_config={'provider': 'openai', 'model': 'gpt-4o', 'temperature': 0.7},
        identity_config={'personality': 'Helpful researcher', 'role': 'researcher'},
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def agent_with_role(app, user):
    """An agent with an existing AgentRole."""
    a = Agent(
        user_id=user.id,
        name='SupervisorAgent',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.flush()

    role = AgentRole(
        workspace_id=user.id,
        agent_id=a.id,
        role='supervisor',
        can_assign_to_peers=True,
        can_escalate_to_supervisor=False,
    )
    db.session.add(role)
    db.session.commit()
    return a


@pytest.fixture
def agent_with_risk_policies(app, user):
    """An agent with existing risk policies."""
    a = Agent(
        user_id=user.id,
        name='RiskyAgent',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.flush()

    p1 = RiskPolicy(
        workspace_id=user.id,
        agent_id=a.id,
        policy_type='daily_spend_cap',
        threshold_value=Decimal('42.50'),
        action_type='throttle',
        cooldown_minutes=120,
        is_enabled=True,
    )
    p2 = RiskPolicy(
        workspace_id=user.id,
        agent_id=a.id,
        policy_type='error_rate_cap',
        threshold_value=Decimal('0.05'),
        action_type='pause_agent',
        cooldown_minutes=60,
        is_enabled=True,
    )
    db.session.add_all([p1, p2])
    db.session.commit()
    return a


@pytest.fixture
def auth_client(client, user):
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['user_email'] = user.email
    return client


# ---------------------------------------------------------------------------
# Single agent conversion
# ---------------------------------------------------------------------------

class TestGenerateImplicitBlueprint:

    def test_creates_published_blueprint(self, app, user, agent):
        bp, ver, inst = generate_implicit_blueprint(agent)

        assert bp.status == 'published'
        assert bp.workspace_id == user.id
        assert bp.name == f'{agent.name} (Auto)'
        assert bp.created_by == user.id

    def test_version_has_unrestricted_wildcards(self, app, user, agent):
        bp, ver, inst = generate_implicit_blueprint(agent)

        assert ver.version == 1
        assert ver.allowed_tools == ['*']
        assert ver.allowed_models == ['*']
        assert ver.default_risk_profile == {}
        assert ver.override_policy == {'allowed_overrides': ['*']}

    def test_policy_snapshot_is_unrestricted(self, app, user, agent):
        bp, ver, inst = generate_implicit_blueprint(agent)

        snapshot = inst.policy_snapshot
        assert snapshot['allowed_tools'] == ['*']
        assert snapshot['allowed_models'] == ['*']

    def test_captures_llm_config(self, app, user, agent_with_config):
        bp, ver, inst = generate_implicit_blueprint(agent_with_config)

        assert ver.llm_defaults == {
            'provider': 'openai',
            'model': 'gpt-4o',
            'temperature': 0.7,
        }

    def test_captures_identity_config(self, app, user, agent_with_config):
        bp, ver, inst = generate_implicit_blueprint(agent_with_config)

        assert ver.identity_defaults == {
            'personality': 'Helpful researcher',
            'role': 'researcher',
        }

    def test_infers_role_from_identity_config(self, app, user, agent_with_config):
        bp, ver, inst = generate_implicit_blueprint(agent_with_config)
        assert bp.role_type == 'researcher'

    def test_infers_role_from_existing_agent_role(self, app, user, agent_with_role):
        bp, ver, inst = generate_implicit_blueprint(agent_with_role)
        assert bp.role_type == 'supervisor'

    def test_captures_existing_hierarchy_defaults(self, app, user, agent_with_role):
        bp, ver, inst = generate_implicit_blueprint(agent_with_role)

        assert ver.hierarchy_defaults == {
            'role': 'supervisor',
            'can_assign_to_peers': True,
            'can_escalate_to_supervisor': False,
        }

    def test_default_role_type_is_worker(self, app, user, agent):
        bp, ver, inst = generate_implicit_blueprint(agent)
        assert bp.role_type == 'worker'

    def test_raises_if_already_managed(self, app, user, agent):
        generate_implicit_blueprint(agent)

        with pytest.raises(ValueError, match='already has a blueprint binding'):
            generate_implicit_blueprint(agent)

    def test_custom_created_by(self, app, user, agent, premium_user):
        bp, ver, inst = generate_implicit_blueprint(agent, created_by=premium_user.id)

        assert bp.created_by == premium_user.id
        assert ver.published_by == premium_user.id
        assert inst.instantiated_by == premium_user.id

    def test_changelog_is_descriptive(self, app, user, agent):
        bp, ver, inst = generate_implicit_blueprint(agent)
        assert 'Auto-generated' in ver.changelog
        assert 'legacy' in ver.changelog.lower()


# ---------------------------------------------------------------------------
# Preservation guarantees
# ---------------------------------------------------------------------------

class TestPreservation:

    def test_existing_risk_policies_untouched(self, app, user, agent_with_risk_policies):
        """Risk policies must NOT be modified during implicit blueprint generation."""
        original_policies = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent_with_risk_policies.id,
        ).all()
        original_data = {
            p.policy_type: (float(p.threshold_value), p.action_type, p.cooldown_minutes)
            for p in original_policies
        }

        generate_implicit_blueprint(agent_with_risk_policies)

        after_policies = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent_with_risk_policies.id,
        ).all()
        after_data = {
            p.policy_type: (float(p.threshold_value), p.action_type, p.cooldown_minutes)
            for p in after_policies
        }

        assert original_data == after_data

    def test_existing_agent_role_untouched(self, app, user, agent_with_role):
        """AgentRole must NOT be modified during implicit blueprint generation."""
        original_role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent_with_role.id,
        ).first()
        original_data = (
            original_role.role,
            original_role.can_assign_to_peers,
            original_role.can_escalate_to_supervisor,
        )

        generate_implicit_blueprint(agent_with_role)

        after_role = AgentRole.query.filter_by(
            workspace_id=user.id, agent_id=agent_with_role.id,
        ).first()
        after_data = (
            after_role.role,
            after_role.can_assign_to_peers,
            after_role.can_escalate_to_supervisor,
        )

        assert original_data == after_data

    def test_converted_agent_has_no_capability_restrictions(self, app, user, agent):
        """After conversion, the agent should still pass all tool/model checks."""
        generate_implicit_blueprint(agent)

        instance = get_agent_instance(agent.id)
        ctx = ExecutionContext(
            workspace_id=user.id,
            agent_id=agent.id,
        ).with_capabilities(instance.policy_snapshot)

        gw = ToolGateway(ctx)

        # All tools should be allowed (wildcards)
        assert gw._check_capability('any_tool') is None
        assert gw._check_capability('web_search') is None
        assert gw._check_capability('binance_trade') is None

        # allowed_tools/allowed_models should be None (unrestricted) for wildcard
        assert ctx.allowed_tools is None
        assert ctx.allowed_models is None


# ---------------------------------------------------------------------------
# Role inference
# ---------------------------------------------------------------------------

class TestRoleInference:

    def test_infer_from_agent_role_supervisor(self, app, user, agent_with_role):
        assert _infer_role_type(agent_with_role) == 'supervisor'

    def test_infer_from_identity_config(self, app, user, agent_with_config):
        assert _infer_role_type(agent_with_config) == 'researcher'

    def test_infer_default_worker(self, app, user, agent):
        assert _infer_role_type(agent) == 'worker'

    def test_infer_agent_role_takes_priority(self, app, user):
        """AgentRole should take priority over identity_config."""
        a = Agent(
            user_id=user.id,
            name='PriorityTest',
            is_active=True,
            created_at=datetime.utcnow(),
            identity_config={'role': 'executor'},
        )
        db.session.add(a)
        db.session.flush()

        role = AgentRole(
            workspace_id=user.id,
            agent_id=a.id,
            role='specialist',
        )
        db.session.add(role)
        db.session.commit()

        # specialist maps to researcher in blueprint role_types
        assert _infer_role_type(a) == 'researcher'

    def test_capture_hierarchy_no_role(self, app, user, agent):
        assert _capture_hierarchy_defaults(agent) is None

    def test_capture_hierarchy_with_role(self, app, user, agent_with_role):
        defaults = _capture_hierarchy_defaults(agent_with_role)
        assert defaults == {
            'role': 'supervisor',
            'can_assign_to_peers': True,
            'can_escalate_to_supervisor': False,
        }


# ---------------------------------------------------------------------------
# Workspace-wide migration
# ---------------------------------------------------------------------------

class TestMigrateWorkspace:

    def test_migrate_all_legacy_agents(self, app, user, agent):
        a2 = Agent(user_id=user.id, name='Agent2', is_active=True, created_at=datetime.utcnow())
        a3 = Agent(user_id=user.id, name='Agent3', is_active=True, created_at=datetime.utcnow())
        db.session.add_all([a2, a3])
        db.session.commit()

        results = migrate_workspace_agents(user.id)

        converted = [r for r in results if r['status'] == 'converted']
        assert len(converted) == 3

        # All should now have instances
        for a in [agent, a2, a3]:
            assert get_agent_instance(a.id) is not None

    def test_skips_already_managed(self, app, user, agent):
        # Convert first
        generate_implicit_blueprint(agent)

        a2 = Agent(user_id=user.id, name='Legacy', is_active=True, created_at=datetime.utcnow())
        db.session.add(a2)
        db.session.commit()

        results = migrate_workspace_agents(user.id)

        skipped = [r for r in results if r['status'] == 'skipped']
        converted = [r for r in results if r['status'] == 'converted']
        assert len(skipped) == 1
        assert skipped[0]['agent_id'] == agent.id
        assert len(converted) == 1
        assert converted[0]['agent_id'] == a2.id

    def test_empty_workspace(self, app, user):
        results = migrate_workspace_agents(user.id)
        assert results == []

    def test_each_agent_gets_own_blueprint(self, app, user, agent):
        a2 = Agent(user_id=user.id, name='Agent2', is_active=True, created_at=datetime.utcnow())
        db.session.add(a2)
        db.session.commit()

        results = migrate_workspace_agents(user.id)

        bp_ids = {r['blueprint_id'] for r in results if r['status'] == 'converted'}
        assert len(bp_ids) == 2  # each agent gets its own blueprint


# ---------------------------------------------------------------------------
# Governance audit trail
# ---------------------------------------------------------------------------

class TestGovernanceAudit:

    def test_conversion_logs_event(self, app, user, agent):
        generate_implicit_blueprint(agent)

        logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id,
            event_type='instance_created',
        ).all()
        assert len(logs) == 1
        assert logs[0].details['implicit'] is True
        assert logs[0].details['source'] == 'backward_compat'
        assert logs[0].agent_id == agent.id

    def test_workspace_migration_logs_all_events(self, app, user, agent):
        a2 = Agent(user_id=user.id, name='Agent2', is_active=True, created_at=datetime.utcnow())
        db.session.add(a2)
        db.session.commit()

        migrate_workspace_agents(user.id)

        logs = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id,
            event_type='instance_created',
        ).all()
        assert len(logs) == 2
        agent_ids = {log.agent_id for log in logs}
        assert agent_ids == {agent.id, a2.id}


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestConvertAgentAPI:

    def test_convert_single_agent(self, auth_client, user, agent):
        resp = auth_client.post(f'/api/agents/{agent.id}/convert-to-blueprint')
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['blueprint']['status'] == 'published'
        assert data['version']['allowed_tools'] == ['*']
        assert data['instance']['agent_id'] == agent.id

    def test_convert_already_managed_returns_400(self, auth_client, user, agent):
        auth_client.post(f'/api/agents/{agent.id}/convert-to-blueprint')

        resp = auth_client.post(f'/api/agents/{agent.id}/convert-to-blueprint')
        assert resp.status_code == 400
        assert 'already has a blueprint' in resp.get_json()['error']

    def test_convert_nonexistent_agent_returns_404(self, auth_client):
        resp = auth_client.post('/api/agents/99999/convert-to-blueprint')
        assert resp.status_code == 404

    def test_convert_requires_auth(self, client, agent):
        resp = client.post(f'/api/agents/{agent.id}/convert-to-blueprint')
        assert resp.status_code == 401


class TestMigrateWorkspaceAPI:

    def test_migrate_workspace(self, auth_client, user, agent):
        a2 = Agent(user_id=user.id, name='Agent2', is_active=True, created_at=datetime.utcnow())
        db.session.add(a2)
        db.session.commit()

        resp = auth_client.post('/api/blueprints/migrate-workspace')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['summary']['converted'] == 2
        assert data['summary']['skipped'] == 0
        assert data['summary']['total'] == 2

    def test_migrate_idempotent(self, auth_client, user, agent):
        auth_client.post('/api/blueprints/migrate-workspace')
        resp = auth_client.post('/api/blueprints/migrate-workspace')

        data = resp.get_json()
        assert data['summary']['converted'] == 0
        assert data['summary']['skipped'] == 1

    def test_migrate_empty_workspace(self, auth_client, user):
        # No agents in workspace
        resp = auth_client.post('/api/blueprints/migrate-workspace')
        data = resp.get_json()
        assert data['summary']['total'] == 0

    def test_migrate_requires_auth(self, client):
        resp = client.post('/api/blueprints/migrate-workspace')
        assert resp.status_code == 401

    def test_migrate_preserves_risk_policies(self, auth_client, user, agent_with_risk_policies):
        original = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent_with_risk_policies.id,
        ).all()
        original_data = {
            p.policy_type: float(p.threshold_value)
            for p in original
        }

        auth_client.post('/api/blueprints/migrate-workspace')

        after = RiskPolicy.query.filter_by(
            workspace_id=user.id, agent_id=agent_with_risk_policies.id,
        ).all()
        after_data = {
            p.policy_type: float(p.threshold_value)
            for p in after
        }

        assert original_data == after_data
