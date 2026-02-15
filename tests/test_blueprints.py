"""
Tests for the Agent Blueprint & Capability System — Phase 1.

Covers:
    - Model CRUD (AgentBlueprint, AgentBlueprintVersion, CapabilityBundle, AgentInstance)
    - Blueprint lifecycle (draft -> published -> archived)
    - Version immutability
    - Blueprint cloning
    - Capability bundle management
    - Capability resolution algorithm
    - Agent instantiation from blueprint
    - Override validation
    - Policy snapshot creation
    - Workspace isolation
    - Instance refresh / version upgrade
"""
import pytest
from datetime import datetime
from models import (
    db, User, Agent,
    AgentBlueprint, AgentBlueprintVersion, CapabilityBundle,
    AgentInstance, blueprint_capabilities,
    BLUEPRINT_ROLE_TYPES, BLUEPRINT_STATUSES,
)
from core.identity.agent_blueprint import (
    create_blueprint, get_blueprint, update_draft_blueprint,
    publish_blueprint, archive_blueprint, clone_blueprint,
    get_blueprint_version,
)
from core.identity.agent_capabilities import (
    create_capability_bundle, get_capability_bundle,
    update_capability_bundle, list_capability_bundles,
    resolve_capabilities, attach_capabilities,
)
from core.identity.agent_instance import (
    instantiate_agent, get_agent_instance,
    refresh_instance_policy, validate_overrides,
    remove_agent_instance,
)
from core.identity.blueprint_registry import (
    list_blueprints, list_blueprint_versions, count_blueprints,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def other_user(app):
    """A second user for workspace isolation tests."""
    u = User(
        email='other-bp@example.com',
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
    """An agent belonging to other_user."""
    a = Agent(
        user_id=other_user.id,
        name='OtherAgent',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def second_agent(app, user):
    """A second agent for the same user."""
    a = Agent(
        user_id=user.id,
        name='SecondAgent',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def draft_blueprint(app, user):
    """A draft blueprint."""
    return create_blueprint(
        workspace_id=user.id,
        name='Research Agent',
        created_by=user.id,
        description='An agent for research tasks',
        role_type='researcher',
    )


@pytest.fixture
def published_blueprint(app, user):
    """A published blueprint with one version."""
    bp = create_blueprint(
        workspace_id=user.id,
        name='Executor Agent',
        created_by=user.id,
        role_type='executor',
    )
    publish_blueprint(
        blueprint_id=bp.id,
        workspace_id=user.id,
        published_by=user.id,
        allowed_models=['openai/gpt-4o', 'anthropic/claude-sonnet-4-5-20250929'],
        allowed_tools=['gmail_send', 'calendar_read', 'web_search'],
        default_risk_profile={'daily_spend_cap': 10.0, 'action_type': 'alert_only'},
        hierarchy_defaults={'role': 'worker', 'can_assign_to_peers': False},
        llm_defaults={'provider': 'openai', 'model': 'gpt-4o', 'temperature': 0.7},
        identity_defaults={'personality': 'helpful executor'},
        override_policy={
            'allowed_overrides': ['temperature', 'system_prompt'],
            'denied_overrides': ['provider', 'allowed_tools'],
        },
        changelog='Initial version',
    )
    return bp


@pytest.fixture
def email_capability(app, user):
    """An email capability bundle."""
    return create_capability_bundle(
        workspace_id=user.id,
        name='Email Access',
        description='Grants email tools',
        tool_set=['gmail_send', 'gmail_read', 'gmail_draft'],
        model_constraints={'allowed_providers': ['openai', 'anthropic']},
        risk_constraints={'max_daily_spend': 5.0},
    )


@pytest.fixture
def calendar_capability(app, user):
    """A calendar capability bundle."""
    return create_capability_bundle(
        workspace_id=user.id,
        name='Calendar Access',
        description='Grants calendar tools',
        tool_set=['calendar_read', 'calendar_create', 'calendar_update'],
        model_constraints={'allowed_providers': ['openai', 'anthropic', 'google']},
        risk_constraints={'max_daily_spend': 8.0},
    )


# ===========================================================================
# Blueprint Model Tests
# ===========================================================================

@pytest.mark.blueprints
class TestBlueprintModel:

    def test_create_blueprint(self, app, user):
        bp = create_blueprint(
            workspace_id=user.id,
            name='Test Blueprint',
            created_by=user.id,
        )
        assert bp.id is not None
        assert len(bp.id) == 36  # UUID
        assert bp.workspace_id == user.id
        assert bp.name == 'Test Blueprint'
        assert bp.status == 'draft'
        assert bp.role_type == 'worker'
        assert bp.created_by == user.id
        assert bp.created_at is not None

    def test_create_with_role_type(self, app, user):
        bp = create_blueprint(
            workspace_id=user.id,
            name='Supervisor',
            created_by=user.id,
            role_type='supervisor',
        )
        assert bp.role_type == 'supervisor'

    def test_create_invalid_role_type(self, app, user):
        with pytest.raises(ValueError, match='Invalid role_type'):
            create_blueprint(
                workspace_id=user.id,
                name='Bad Role',
                created_by=user.id,
                role_type='invalid_role',
            )

    def test_to_dict(self, draft_blueprint):
        d = draft_blueprint.to_dict()
        assert d['id'] == draft_blueprint.id
        assert d['name'] == 'Research Agent'
        assert d['status'] == 'draft'
        assert d['role_type'] == 'researcher'
        assert d['latest_version'] == 0

    def test_latest_version_zero_for_draft(self, draft_blueprint):
        assert draft_blueprint.latest_version == 0

    def test_latest_version_increments(self, published_blueprint, user):
        assert published_blueprint.latest_version == 1

        publish_blueprint(
            blueprint_id=published_blueprint.id,
            workspace_id=user.id,
            published_by=user.id,
            changelog='v2',
        )
        assert published_blueprint.latest_version == 2


# ===========================================================================
# Blueprint Lifecycle Tests
# ===========================================================================

@pytest.mark.blueprints
class TestBlueprintLifecycle:

    def test_draft_to_published(self, draft_blueprint, user):
        assert draft_blueprint.status == 'draft'

        publish_blueprint(
            blueprint_id=draft_blueprint.id,
            workspace_id=user.id,
            published_by=user.id,
            allowed_tools=['web_search'],
            changelog='First publish',
        )

        assert draft_blueprint.status == 'published'
        assert draft_blueprint.latest_version == 1

    def test_published_stays_published_on_new_version(self, published_blueprint, user):
        assert published_blueprint.status == 'published'

        publish_blueprint(
            blueprint_id=published_blueprint.id,
            workspace_id=user.id,
            published_by=user.id,
            changelog='v2 update',
        )

        assert published_blueprint.status == 'published'
        assert published_blueprint.latest_version == 2

    def test_published_to_archived(self, published_blueprint, user):
        archive_blueprint(published_blueprint.id, user.id)
        assert published_blueprint.status == 'archived'

    def test_archive_is_idempotent(self, published_blueprint, user):
        archive_blueprint(published_blueprint.id, user.id)
        archive_blueprint(published_blueprint.id, user.id)
        assert published_blueprint.status == 'archived'

    def test_cannot_archive_draft(self, draft_blueprint, user):
        with pytest.raises(ValueError, match='Cannot archive a draft'):
            archive_blueprint(draft_blueprint.id, user.id)

    def test_cannot_publish_archived(self, published_blueprint, user):
        archive_blueprint(published_blueprint.id, user.id)

        with pytest.raises(ValueError, match='Cannot publish an archived'):
            publish_blueprint(
                blueprint_id=published_blueprint.id,
                workspace_id=user.id,
                published_by=user.id,
            )

    def test_update_draft_name(self, draft_blueprint, user):
        update_draft_blueprint(draft_blueprint.id, user.id, name='Renamed')
        assert draft_blueprint.name == 'Renamed'

    def test_update_draft_role_type(self, draft_blueprint, user):
        update_draft_blueprint(draft_blueprint.id, user.id, role_type='supervisor')
        assert draft_blueprint.role_type == 'supervisor'

    def test_cannot_update_published(self, published_blueprint, user):
        with pytest.raises(ValueError, match='Only drafts are mutable'):
            update_draft_blueprint(published_blueprint.id, user.id, name='Nope')

    def test_cannot_update_invalid_field(self, draft_blueprint, user):
        with pytest.raises(ValueError, match='Cannot update field'):
            update_draft_blueprint(draft_blueprint.id, user.id, status='published')


# ===========================================================================
# Version Immutability Tests
# ===========================================================================

@pytest.mark.blueprints
class TestVersionImmutability:

    def test_version_fields_persisted(self, published_blueprint, user):
        ver = get_blueprint_version(published_blueprint.id, 1, user.id)
        assert ver is not None
        assert ver.version == 1
        assert ver.allowed_models == ['openai/gpt-4o', 'anthropic/claude-sonnet-4-5-20250929']
        assert ver.allowed_tools == ['gmail_send', 'calendar_read', 'web_search']
        assert ver.default_risk_profile == {'daily_spend_cap': 10.0, 'action_type': 'alert_only'}
        assert ver.llm_defaults == {'provider': 'openai', 'model': 'gpt-4o', 'temperature': 0.7}
        assert ver.override_policy['allowed_overrides'] == ['temperature', 'system_prompt']
        assert ver.changelog == 'Initial version'
        assert ver.published_by == user.id
        assert ver.published_at is not None

    def test_version_to_dict(self, published_blueprint, user):
        ver = get_blueprint_version(published_blueprint.id, 1, user.id)
        d = ver.to_dict()
        assert d['blueprint_id'] == published_blueprint.id
        assert d['version'] == 1
        assert d['allowed_tools'] == ['gmail_send', 'calendar_read', 'web_search']

    def test_versions_are_sequential(self, published_blueprint, user):
        publish_blueprint(
            blueprint_id=published_blueprint.id,
            workspace_id=user.id,
            published_by=user.id,
            allowed_tools=['web_search_only'],
            changelog='v2',
        )
        publish_blueprint(
            blueprint_id=published_blueprint.id,
            workspace_id=user.id,
            published_by=user.id,
            changelog='v3',
        )

        v1 = get_blueprint_version(published_blueprint.id, 1, user.id)
        v2 = get_blueprint_version(published_blueprint.id, 2, user.id)
        v3 = get_blueprint_version(published_blueprint.id, 3, user.id)

        assert v1.version == 1
        assert v2.version == 2
        assert v3.version == 3
        # v1 unchanged by later versions
        assert v1.allowed_tools == ['gmail_send', 'calendar_read', 'web_search']
        assert v2.allowed_tools == ['web_search_only']

    def test_unique_constraint_on_version(self, published_blueprint, user):
        """Direct DB insert of duplicate version should fail."""
        dup = AgentBlueprintVersion(
            blueprint_id=published_blueprint.id,
            version=1,  # already exists
            published_at=datetime.utcnow(),
            published_by=user.id,
        )
        db.session.add(dup)
        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()
        db.session.rollback()


# ===========================================================================
# Blueprint Cloning Tests
# ===========================================================================

@pytest.mark.blueprints
class TestBlueprintCloning:

    def test_clone_creates_draft(self, published_blueprint, user):
        clone = clone_blueprint(
            source_blueprint_id=published_blueprint.id,
            source_version=1,
            workspace_id=user.id,
            created_by=user.id,
        )
        assert clone.status == 'draft'
        assert clone.id != published_blueprint.id
        assert clone.name == 'Executor Agent (Clone)'
        assert clone.role_type == published_blueprint.role_type
        assert clone.description == published_blueprint.description
        assert clone.latest_version == 0

    def test_clone_with_custom_name(self, published_blueprint, user):
        clone = clone_blueprint(
            source_blueprint_id=published_blueprint.id,
            source_version=1,
            workspace_id=user.id,
            created_by=user.id,
            name='My Custom Clone',
        )
        assert clone.name == 'My Custom Clone'

    def test_clone_not_found(self, app, user):
        with pytest.raises(LookupError, match='not found'):
            clone_blueprint(
                source_blueprint_id='nonexistent',
                source_version=1,
                workspace_id=user.id,
                created_by=user.id,
            )

    def test_clone_version_not_found(self, published_blueprint, user):
        with pytest.raises(LookupError, match='Version 99 not found'):
            clone_blueprint(
                source_blueprint_id=published_blueprint.id,
                source_version=99,
                workspace_id=user.id,
                created_by=user.id,
            )


# ===========================================================================
# Capability Bundle Tests
# ===========================================================================

@pytest.mark.blueprints
class TestCapabilityBundle:

    def test_create_bundle(self, email_capability, user):
        assert email_capability.id is not None
        assert email_capability.workspace_id == user.id
        assert email_capability.name == 'Email Access'
        assert email_capability.tool_set == ['gmail_send', 'gmail_read', 'gmail_draft']
        assert email_capability.model_constraints == {'allowed_providers': ['openai', 'anthropic']}
        assert email_capability.risk_constraints == {'max_daily_spend': 5.0}
        assert email_capability.is_system is False

    def test_duplicate_name_rejected(self, email_capability, user):
        with pytest.raises(ValueError, match='already exists'):
            create_capability_bundle(
                workspace_id=user.id,
                name='Email Access',
            )

    def test_get_bundle(self, email_capability, user):
        fetched = get_capability_bundle(email_capability.id, user.id)
        assert fetched is not None
        assert fetched.name == 'Email Access'

    def test_get_bundle_wrong_workspace(self, email_capability, other_user):
        fetched = get_capability_bundle(email_capability.id, other_user.id)
        assert fetched is None

    def test_update_bundle(self, email_capability, user):
        updated = update_capability_bundle(
            email_capability.id, user.id,
            description='Updated description',
            tool_set=['gmail_send', 'gmail_read'],
        )
        assert updated.description == 'Updated description'
        assert updated.tool_set == ['gmail_send', 'gmail_read']

    def test_update_system_bundle_rejected(self, app, user):
        bundle = CapabilityBundle(
            workspace_id=user.id,
            name='System Bundle',
            is_system=True,
            created_at=datetime.utcnow(),
        )
        db.session.add(bundle)
        db.session.commit()

        with pytest.raises(ValueError, match='system capability'):
            update_capability_bundle(bundle.id, user.id, name='Renamed')

    def test_list_bundles(self, email_capability, calendar_capability, user):
        bundles = list_capability_bundles(user.id)
        names = [b.name for b in bundles]
        assert 'Calendar Access' in names
        assert 'Email Access' in names

    def test_to_dict(self, email_capability):
        d = email_capability.to_dict()
        assert d['name'] == 'Email Access'
        assert d['tool_set'] == ['gmail_send', 'gmail_read', 'gmail_draft']
        assert d['is_system'] is False

    def test_attach_to_version(self, published_blueprint, email_capability, user):
        ver = get_blueprint_version(published_blueprint.id, 1, user.id)
        attach_capabilities(ver.id, [email_capability.id], user.id)

        # Refresh and verify
        db.session.expire(ver)
        assert len(ver.capabilities) == 1
        assert ver.capabilities[0].name == 'Email Access'


# ===========================================================================
# Capability Resolution Tests
# ===========================================================================

@pytest.mark.blueprints
class TestCapabilityResolution:

    def test_no_bundles_uses_blueprint_values(self, published_blueprint, user):
        ver = get_blueprint_version(published_blueprint.id, 1, user.id)
        caps = resolve_capabilities(ver)

        assert caps['allowed_tools'] == ['gmail_send', 'calendar_read', 'web_search']
        assert caps['allowed_models'] == ['openai/gpt-4o', 'anthropic/claude-sonnet-4-5-20250929']
        assert caps['risk_profile'] == {'daily_spend_cap': 10.0, 'action_type': 'alert_only'}
        assert caps['llm_defaults'] == {'provider': 'openai', 'model': 'gpt-4o', 'temperature': 0.7}

    def test_no_bundles_empty_lists_become_wildcard(self, app, user):
        bp = create_blueprint(workspace_id=user.id, name='Empty', created_by=user.id)
        ver = publish_blueprint(
            blueprint_id=bp.id,
            workspace_id=user.id,
            published_by=user.id,
        )
        caps = resolve_capabilities(ver)
        assert caps['allowed_tools'] == ['*']
        assert caps['allowed_models'] == ['*']

    def test_tool_set_union_across_bundles(self, app, user, email_capability, calendar_capability):
        bp = create_blueprint(workspace_id=user.id, name='Multi', created_by=user.id)
        ver = publish_blueprint(
            blueprint_id=bp.id,
            workspace_id=user.id,
            published_by=user.id,
            allowed_tools=['*'],  # no ceiling
            capability_ids=[email_capability.id, calendar_capability.id],
        )
        caps = resolve_capabilities(ver)
        tools = set(caps['allowed_tools'])
        # Union: all tools from both bundles
        assert 'gmail_send' in tools
        assert 'gmail_read' in tools
        assert 'gmail_draft' in tools
        assert 'calendar_read' in tools
        assert 'calendar_create' in tools
        assert 'calendar_update' in tools

    def test_tool_set_capped_by_blueprint(self, app, user, email_capability, calendar_capability):
        bp = create_blueprint(workspace_id=user.id, name='Capped', created_by=user.id)
        ver = publish_blueprint(
            blueprint_id=bp.id,
            workspace_id=user.id,
            published_by=user.id,
            allowed_tools=['gmail_send', 'calendar_read'],  # ceiling
            capability_ids=[email_capability.id, calendar_capability.id],
        )
        caps = resolve_capabilities(ver)
        tools = set(caps['allowed_tools'])
        # Only tools in both the union AND the blueprint ceiling
        assert tools == {'calendar_read', 'gmail_send'}

    def test_model_constraints_intersection(self, app, user, email_capability, calendar_capability):
        bp = create_blueprint(workspace_id=user.id, name='Models', created_by=user.id)
        ver = publish_blueprint(
            blueprint_id=bp.id,
            workspace_id=user.id,
            published_by=user.id,
            capability_ids=[email_capability.id, calendar_capability.id],
        )
        caps = resolve_capabilities(ver)
        # email allows: openai, anthropic
        # calendar allows: openai, anthropic, google
        # intersection: openai, anthropic
        models = set(caps['allowed_models'])
        assert models == {'anthropic', 'openai'}

    def test_risk_constraints_minimum(self, app, user, email_capability, calendar_capability):
        bp = create_blueprint(workspace_id=user.id, name='Risk', created_by=user.id)
        ver = publish_blueprint(
            blueprint_id=bp.id,
            workspace_id=user.id,
            published_by=user.id,
            default_risk_profile={'daily_spend_cap': 20.0},
            capability_ids=[email_capability.id, calendar_capability.id],
        )
        caps = resolve_capabilities(ver)
        # email: max_daily_spend=5.0, calendar: max_daily_spend=8.0
        # blueprint: daily_spend_cap=20.0
        # min(20.0, 5.0, 8.0) for overlapping keys
        assert caps['risk_profile']['max_daily_spend'] == 5.0
        assert caps['risk_profile']['daily_spend_cap'] == 20.0  # only from blueprint, not in bundles


# ===========================================================================
# Override Validation Tests
# ===========================================================================

@pytest.mark.blueprints
class TestOverrideValidation:

    def test_no_overrides_always_valid(self):
        valid, error = validate_overrides(None, None)
        assert valid is True

    def test_empty_overrides_always_valid(self):
        valid, error = validate_overrides({}, {'allowed_overrides': []})
        assert valid is True

    def test_allowed_override(self):
        valid, error = validate_overrides(
            {'temperature': 0.5},
            {'allowed_overrides': ['temperature', 'system_prompt']},
        )
        assert valid is True

    def test_denied_override(self):
        valid, error = validate_overrides(
            {'provider': 'anthropic'},
            {
                'allowed_overrides': ['temperature'],
                'denied_overrides': ['provider'],
            },
        )
        assert valid is False
        assert 'explicitly denied' in error

    def test_not_in_allowed_list(self):
        valid, error = validate_overrides(
            {'model': 'gpt-3.5'},
            {'allowed_overrides': ['temperature']},
        )
        assert valid is False
        assert 'not in allowed_overrides' in error

    def test_wildcard_allows_everything(self):
        valid, error = validate_overrides(
            {'temperature': 0.5, 'model': 'gpt-3.5'},
            {'allowed_overrides': ['*']},
        )
        assert valid is True

    def test_wildcard_still_checks_denied(self):
        valid, error = validate_overrides(
            {'provider': 'anthropic'},
            {'allowed_overrides': ['*'], 'denied_overrides': ['provider']},
        )
        assert valid is False
        assert 'explicitly denied' in error

    def test_no_policy_means_no_overrides(self):
        valid, error = validate_overrides(
            {'temperature': 0.5},
            None,
        )
        assert valid is False
        assert 'not permitted' in error


# ===========================================================================
# Agent Instantiation Tests
# ===========================================================================

@pytest.mark.blueprints
class TestAgentInstantiation:

    def test_basic_instantiation(self, app, user, agent, published_blueprint):
        instance = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        assert instance.id is not None
        assert instance.agent_id == agent.id
        assert instance.blueprint_id == published_blueprint.id
        assert instance.blueprint_version == 1
        assert instance.workspace_id == user.id
        assert instance.policy_snapshot is not None
        assert instance.instantiated_at is not None
        assert instance.overrides is None

    def test_policy_snapshot_populated(self, app, user, agent, published_blueprint):
        instance = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        snap = instance.policy_snapshot
        assert 'allowed_tools' in snap
        assert 'allowed_models' in snap
        assert 'risk_profile' in snap
        assert 'gmail_send' in snap['allowed_tools']

    def test_instantiation_with_valid_overrides(self, app, user, agent, published_blueprint):
        instance = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
            overrides={'temperature': 0.3},
        )
        assert instance.overrides == {'temperature': 0.3}

    def test_instantiation_with_denied_override(self, app, user, agent, published_blueprint):
        with pytest.raises(ValueError, match='Override validation failed'):
            instantiate_agent(
                agent_id=agent.id,
                blueprint_id=published_blueprint.id,
                version=1,
                workspace_id=user.id,
                instantiated_by=user.id,
                overrides={'provider': 'anthropic'},  # denied in override_policy
            )

    def test_cannot_instantiate_draft(self, app, user, agent, draft_blueprint):
        with pytest.raises(ValueError, match='Only published blueprints'):
            instantiate_agent(
                agent_id=agent.id,
                blueprint_id=draft_blueprint.id,
                version=1,
                workspace_id=user.id,
                instantiated_by=user.id,
            )

    def test_cannot_instantiate_twice(self, app, user, agent, published_blueprint):
        instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        with pytest.raises(ValueError, match='already has an instance'):
            instantiate_agent(
                agent_id=agent.id,
                blueprint_id=published_blueprint.id,
                version=1,
                workspace_id=user.id,
                instantiated_by=user.id,
            )

    def test_agent_not_found(self, app, user, published_blueprint):
        with pytest.raises(LookupError, match='Agent 99999 not found'):
            instantiate_agent(
                agent_id=99999,
                blueprint_id=published_blueprint.id,
                version=1,
                workspace_id=user.id,
                instantiated_by=user.id,
            )

    def test_version_not_found(self, app, user, agent, published_blueprint):
        with pytest.raises(LookupError, match='Version 99 not found'):
            instantiate_agent(
                agent_id=agent.id,
                blueprint_id=published_blueprint.id,
                version=99,
                workspace_id=user.id,
                instantiated_by=user.id,
            )

    def test_to_dict(self, app, user, agent, published_blueprint):
        instance = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        d = instance.to_dict()
        assert d['agent_id'] == agent.id
        assert d['blueprint_id'] == published_blueprint.id
        assert d['blueprint_version'] == 1
        assert d['policy_snapshot'] is not None

    def test_agent_backref(self, app, user, agent, published_blueprint):
        instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        # Agent.instance backref (uselist=False)
        db.session.expire(agent)
        assert agent.instance is not None
        assert agent.instance.blueprint_id == published_blueprint.id


# ===========================================================================
# Instance Refresh & Version Upgrade Tests
# ===========================================================================

@pytest.mark.blueprints
class TestInstanceRefresh:

    def test_refresh_snapshot(self, app, user, agent, published_blueprint):
        instance = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        assert instance.last_policy_refresh is None

        refreshed = refresh_instance_policy(agent.id, user.id)
        assert refreshed.last_policy_refresh is not None

    def test_upgrade_version(self, app, user, agent, published_blueprint):
        instance = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        assert instance.blueprint_version == 1

        # Publish v2
        publish_blueprint(
            blueprint_id=published_blueprint.id,
            workspace_id=user.id,
            published_by=user.id,
            allowed_tools=['web_search'],
            changelog='v2 — fewer tools',
        )

        refreshed = refresh_instance_policy(
            agent.id, user.id, new_version=2,
        )
        assert refreshed.blueprint_version == 2
        assert 'web_search' in refreshed.policy_snapshot['allowed_tools']

    def test_update_overrides_on_refresh(self, app, user, agent, published_blueprint):
        instance = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )

        refreshed = refresh_instance_policy(
            agent.id, user.id,
            new_overrides={'temperature': 0.2},
        )
        assert refreshed.overrides == {'temperature': 0.2}

    def test_refresh_rejects_invalid_overrides(self, app, user, agent, published_blueprint):
        instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        with pytest.raises(ValueError, match='Override validation failed'):
            refresh_instance_policy(
                agent.id, user.id,
                new_overrides={'provider': 'anthropic'},
            )


# ===========================================================================
# Instance Removal Tests
# ===========================================================================

@pytest.mark.blueprints
class TestInstanceRemoval:

    def test_remove_instance(self, app, user, agent, published_blueprint):
        instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        assert get_agent_instance(agent.id) is not None

        removed = remove_agent_instance(agent.id, user.id)
        assert removed is True
        assert get_agent_instance(agent.id) is None

    def test_remove_nonexistent_returns_false(self, app, user, agent):
        removed = remove_agent_instance(agent.id, user.id)
        assert removed is False


# ===========================================================================
# Workspace Isolation Tests
# ===========================================================================

@pytest.mark.blueprints
class TestWorkspaceIsolation:

    def test_blueprint_not_visible_cross_workspace(self, draft_blueprint, other_user):
        fetched = get_blueprint(draft_blueprint.id, other_user.id)
        assert fetched is None

    def test_cannot_publish_cross_workspace(self, draft_blueprint, other_user):
        with pytest.raises(LookupError):
            publish_blueprint(
                blueprint_id=draft_blueprint.id,
                workspace_id=other_user.id,
                published_by=other_user.id,
            )

    def test_cannot_instantiate_cross_workspace(self, published_blueprint, other_user, other_agent):
        with pytest.raises(LookupError):
            instantiate_agent(
                agent_id=other_agent.id,
                blueprint_id=published_blueprint.id,
                version=1,
                workspace_id=other_user.id,
                instantiated_by=other_user.id,
            )

    def test_capability_not_visible_cross_workspace(self, email_capability, other_user):
        fetched = get_capability_bundle(email_capability.id, other_user.id)
        assert fetched is None

    def test_cannot_clone_cross_workspace(self, published_blueprint, other_user):
        with pytest.raises(LookupError):
            clone_blueprint(
                source_blueprint_id=published_blueprint.id,
                source_version=1,
                workspace_id=other_user.id,
                created_by=other_user.id,
            )

    def test_list_only_own_blueprints(self, draft_blueprint, published_blueprint, other_user, user):
        own = list_blueprints(user.id)
        other = list_blueprints(other_user.id)

        assert len(own) == 2
        assert len(other) == 0


# ===========================================================================
# Blueprint Registry Tests
# ===========================================================================

@pytest.mark.blueprints
class TestBlueprintRegistry:

    def test_list_all(self, draft_blueprint, published_blueprint, user):
        bps = list_blueprints(user.id)
        assert len(bps) == 2

    def test_filter_by_status(self, draft_blueprint, published_blueprint, user):
        drafts = list_blueprints(user.id, status='draft')
        published = list_blueprints(user.id, status='published')

        assert len(drafts) == 1
        assert drafts[0].name == 'Research Agent'
        assert len(published) == 1
        assert published[0].name == 'Executor Agent'

    def test_filter_by_role_type(self, draft_blueprint, published_blueprint, user):
        researchers = list_blueprints(user.id, role_type='researcher')
        executors = list_blueprints(user.id, role_type='executor')

        assert len(researchers) == 1
        assert len(executors) == 1

    def test_list_versions(self, published_blueprint, user):
        publish_blueprint(
            blueprint_id=published_blueprint.id,
            workspace_id=user.id,
            published_by=user.id,
            changelog='v2',
        )
        versions = list_blueprint_versions(published_blueprint.id, user.id)
        assert len(versions) == 2
        # Ordered by version desc
        assert versions[0].version == 2
        assert versions[1].version == 1

    def test_count_blueprints(self, draft_blueprint, published_blueprint, user):
        assert count_blueprints(user.id) == 2
        assert count_blueprints(user.id, status='draft') == 1
        assert count_blueprints(user.id, status='published') == 1
        assert count_blueprints(user.id, status='archived') == 0

    def test_pagination(self, app, user):
        for i in range(5):
            create_blueprint(
                workspace_id=user.id,
                name=f'BP-{i}',
                created_by=user.id,
            )
        page1 = list_blueprints(user.id, limit=3, offset=0)
        page2 = list_blueprints(user.id, limit=3, offset=3)

        assert len(page1) == 3
        assert len(page2) == 2


# ===========================================================================
# Publish with Capabilities Tests
# ===========================================================================

@pytest.mark.blueprints
class TestPublishWithCapabilities:

    def test_publish_with_capability_ids(self, app, user, email_capability, calendar_capability):
        bp = create_blueprint(workspace_id=user.id, name='WithCaps', created_by=user.id)
        ver = publish_blueprint(
            blueprint_id=bp.id,
            workspace_id=user.id,
            published_by=user.id,
            capability_ids=[email_capability.id, calendar_capability.id],
        )
        assert len(ver.capabilities) == 2
        names = {c.name for c in ver.capabilities}
        assert names == {'Email Access', 'Calendar Access'}

    def test_publish_with_invalid_capability_id(self, app, user):
        bp = create_blueprint(workspace_id=user.id, name='BadCap', created_by=user.id)
        with pytest.raises(ValueError, match='CapabilityBundle 99999 not found'):
            publish_blueprint(
                blueprint_id=bp.id,
                workspace_id=user.id,
                published_by=user.id,
                capability_ids=[99999],
            )
        # Blueprint should still be draft (rollback)
        db.session.expire(bp)
        assert bp.status == 'draft'

    def test_publish_with_cross_workspace_capability(self, app, user, other_user):
        other_cap = create_capability_bundle(
            workspace_id=other_user.id,
            name='Other Cap',
            tool_set=['secret_tool'],
        )
        bp = create_blueprint(workspace_id=user.id, name='Cross', created_by=user.id)
        with pytest.raises(ValueError, match='not found in workspace'):
            publish_blueprint(
                blueprint_id=bp.id,
                workspace_id=user.id,
                published_by=user.id,
                capability_ids=[other_cap.id],
            )


# ===========================================================================
# Multi-Agent Instance Tests
# ===========================================================================

@pytest.mark.blueprints
class TestMultiAgentInstance:

    def test_multiple_agents_same_blueprint(self, app, user, agent, second_agent, published_blueprint):
        inst1 = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        inst2 = instantiate_agent(
            agent_id=second_agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        assert inst1.agent_id != inst2.agent_id
        assert inst1.blueprint_id == inst2.blueprint_id
        assert inst1.policy_snapshot == inst2.policy_snapshot

    def test_instances_pinned_after_new_version(self, app, user, agent, second_agent, published_blueprint):
        """Publishing a new version does NOT change existing instances."""
        inst1 = instantiate_agent(
            agent_id=agent.id,
            blueprint_id=published_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        original_tools = inst1.policy_snapshot['allowed_tools']

        # Publish v2 with different tools
        publish_blueprint(
            blueprint_id=published_blueprint.id,
            workspace_id=user.id,
            published_by=user.id,
            allowed_tools=['only_web_search'],
            changelog='v2',
        )

        # inst1 is still on v1
        db.session.expire(inst1)
        assert inst1.blueprint_version == 1
        assert inst1.policy_snapshot['allowed_tools'] == original_tools

        # New instance can use v2
        inst2 = instantiate_agent(
            agent_id=second_agent.id,
            blueprint_id=published_blueprint.id,
            version=2,
            workspace_id=user.id,
            instantiated_by=user.id,
        )
        assert inst2.blueprint_version == 2
        assert inst2.policy_snapshot['allowed_tools'] == ['only_web_search']
