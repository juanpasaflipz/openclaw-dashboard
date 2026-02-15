"""
Tests for capability enforcement at the runtime boundary.

Phase 2 of the Blueprint system — verifies that:
    - Tool access is denied when not in agent capabilities.
    - Tool access is allowed when in agent capabilities.
    - Legacy agents (no blueprint) have unrestricted access.
    - Model validation checks allowed_models.
    - Capabilities flow from blueprint -> instance -> runtime session.
    - list_tools() is filtered by capabilities.
    - Wildcard capabilities ("*") mean unrestricted.
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from models import db, User, Agent
from core.runtime.execution_context import ExecutionContext
from core.runtime.tool_gateway import ToolGateway
from core.runtime.agent_runtime import AgentRuntime
from core.identity.agent_blueprint import create_blueprint, publish_blueprint
from core.identity.agent_capabilities import create_capability_bundle
from core.identity.agent_instance import instantiate_agent


# ---------------------------------------------------------------------------
# Helpers — bypass governance + obs for runtime tests
# ---------------------------------------------------------------------------

def _noop(*args, **kwargs):
    pass


@pytest.fixture(autouse=True)
def _bypass_runtime_infra():
    """Bypass governance tier checks and obs run tracking."""
    with patch.object(AgentRuntime, '_pre_start_check', _noop), \
         patch.object(AgentRuntime, '_start_obs_run', _noop), \
         patch.object(AgentRuntime, '_finish_obs_run', _noop):
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def second_agent(app, user):
    """A second agent in the same workspace (legacy, no blueprint)."""
    a = Agent(
        user_id=user.id,
        name='LegacyAgent',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def restricted_blueprint(app, user):
    """A published blueprint with restricted tools and models."""
    bp = create_blueprint(
        workspace_id=user.id,
        name='Restricted Agent',
        created_by=user.id,
        role_type='worker',
    )
    publish_blueprint(
        blueprint_id=bp.id,
        workspace_id=user.id,
        published_by=user.id,
        allowed_models=['openai/gpt-4o', 'anthropic/claude-sonnet-4-5-20250929'],
        allowed_tools=['gmail_send', 'calendar_read', 'web_search'],
        default_risk_profile={'daily_spend_cap': 10.0},
        override_policy={'allowed_overrides': ['temperature']},
        changelog='Restricted version',
    )
    return bp


@pytest.fixture
def wildcard_blueprint(app, user):
    """A published blueprint with wildcard (unrestricted) capabilities."""
    bp = create_blueprint(
        workspace_id=user.id,
        name='Unrestricted Agent',
        created_by=user.id,
    )
    publish_blueprint(
        blueprint_id=bp.id,
        workspace_id=user.id,
        published_by=user.id,
        allowed_models=['*'],
        allowed_tools=['*'],
        changelog='Wildcard version',
    )
    return bp


@pytest.fixture
def capability_blueprint(app, user):
    """A published blueprint with capability bundles attached."""
    email_cap = create_capability_bundle(
        workspace_id=user.id,
        name='Email Cap (enforce)',
        tool_set=['gmail_send', 'gmail_read'],
        model_constraints={'allowed_providers': ['openai', 'anthropic']},
        risk_constraints={'max_daily_spend': 5.0},
    )
    calendar_cap = create_capability_bundle(
        workspace_id=user.id,
        name='Calendar Cap (enforce)',
        tool_set=['calendar_read', 'calendar_create'],
        model_constraints={'allowed_providers': ['openai']},
    )
    bp = create_blueprint(
        workspace_id=user.id,
        name='Capability Agent',
        created_by=user.id,
    )
    publish_blueprint(
        blueprint_id=bp.id,
        workspace_id=user.id,
        published_by=user.id,
        allowed_tools=['*'],  # no ceiling — bundles define the tools
        capability_ids=[email_cap.id, calendar_cap.id],
        changelog='With capabilities',
    )
    return bp


@pytest.fixture
def restricted_agent(app, user, agent, restricted_blueprint):
    """An agent bound to the restricted blueprint."""
    instantiate_agent(
        agent_id=agent.id,
        blueprint_id=restricted_blueprint.id,
        version=1,
        workspace_id=user.id,
        instantiated_by=user.id,
    )
    return agent


@pytest.fixture
def wildcard_agent(app, user, agent, wildcard_blueprint):
    """An agent bound to the wildcard blueprint."""
    instantiate_agent(
        agent_id=agent.id,
        blueprint_id=wildcard_blueprint.id,
        version=1,
        workspace_id=user.id,
        instantiated_by=user.id,
    )
    return agent


@pytest.fixture
def capability_agent(app, user, agent, capability_blueprint):
    """An agent bound to a blueprint with capability bundles."""
    instantiate_agent(
        agent_id=agent.id,
        blueprint_id=capability_blueprint.id,
        version=1,
        workspace_id=user.id,
        instantiated_by=user.id,
    )
    return agent


# ===========================================================================
# ExecutionContext capability properties
# ===========================================================================

@pytest.mark.blueprints
class TestExecutionContextCapabilities:

    def test_no_capabilities_by_default(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        assert ctx.has_capabilities is False
        assert ctx.allowed_tools is None
        assert ctx.allowed_models is None

    def test_with_capabilities_creates_new_context(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        caps = {
            'allowed_tools': ['gmail_send', 'web_search'],
            'allowed_models': ['openai/gpt-4o'],
        }
        new_ctx = ctx.with_capabilities(caps)

        # Original unchanged
        assert ctx.has_capabilities is False

        # New context has capabilities
        assert new_ctx.has_capabilities is True
        assert new_ctx.allowed_tools == {'gmail_send', 'web_search'}
        assert new_ctx.allowed_models == {'openai/gpt-4o'}
        # Preserves other fields
        assert new_ctx.workspace_id == ctx.workspace_id
        assert new_ctx.agent_id == ctx.agent_id
        assert new_ctx.run_id == ctx.run_id

    def test_wildcard_tools_returns_none(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        new_ctx = ctx.with_capabilities({
            'allowed_tools': ['*'],
            'allowed_models': ['*'],
        })
        assert new_ctx.has_capabilities is True
        assert new_ctx.allowed_tools is None  # wildcard = unrestricted
        assert new_ctx.allowed_models is None

    def test_empty_tools_returns_none(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        new_ctx = ctx.with_capabilities({
            'allowed_tools': [],
            'allowed_models': [],
        })
        assert new_ctx.allowed_tools is None
        assert new_ctx.allowed_models is None

    def test_as_dict_includes_capability_flag(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        assert 'has_capabilities' not in ctx.as_dict()

        new_ctx = ctx.with_capabilities({'allowed_tools': ['x']})
        assert new_ctx.as_dict()['has_capabilities'] is True

    def test_context_with_capabilities_is_still_frozen(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        new_ctx = ctx.with_capabilities({'allowed_tools': ['x']})

        with pytest.raises(AttributeError):
            new_ctx.resolved_capabilities = {}


# ===========================================================================
# ToolGateway capability enforcement
# ===========================================================================

@pytest.mark.blueprints
class TestToolGatewayCapabilityEnforcement:

    def test_tool_denied_not_in_capabilities(self, app, user, agent):
        """Tool not in allowed_tools is denied."""
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({
            'allowed_tools': ['gmail_send', 'calendar_read'],
        })
        gw = ToolGateway(ctx)

        with patch('core.observability.ingestion.emit_event'):
            result = gw.execute('binance_trade', {'symbol': 'BTC'})

        assert 'error' in result
        assert result['capability_denied'] is True
        assert 'binance_trade' in result['error']

    def test_tool_allowed_in_capabilities(self, app, user, agent):
        """Tool in allowed_tools passes capability check."""
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({
            'allowed_tools': ['gmail_send', 'calendar_read'],
        })
        gw = ToolGateway(ctx)

        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event'):
                result = gw.execute('gmail_send', {'to': 'test@example.com'})

        assert result == {'ok': True}

    def test_legacy_agent_unrestricted(self, app, user, agent):
        """Agent without capabilities can use any tool."""
        ctx = ExecutionContext.create(user.id, agent.id)
        # No capabilities attached
        assert ctx.has_capabilities is False

        gw = ToolGateway(ctx)

        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event'):
                result = gw.execute('binance_trade', {'symbol': 'BTC'})

        assert result == {'ok': True}

    def test_wildcard_tools_unrestricted(self, app, user, agent):
        """Agent with ["*"] tools can use any tool."""
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({'allowed_tools': ['*']})
        gw = ToolGateway(ctx)

        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event'):
                result = gw.execute('any_tool_at_all')

        assert result == {'ok': True}

    def test_denied_tool_does_not_execute(self, app, user, agent):
        """When capability denies a tool, execute_tool is never called."""
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({'allowed_tools': ['web_search']})
        gw = ToolGateway(ctx)

        with patch('agent_tools.execute_tool') as mock_exec:
            with patch('core.observability.ingestion.emit_event'):
                result = gw.execute('binance_trade')

        mock_exec.assert_not_called()
        assert result['capability_denied'] is True

    def test_denied_tool_emits_error_event(self, app, user, agent):
        """Capability denial still emits a tool_result error event."""
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({'allowed_tools': ['web_search']})
        gw = ToolGateway(ctx)

        with patch('core.observability.ingestion.emit_event') as mock_emit:
            gw.execute('forbidden_tool')

        # Should have emitted tool_result with error status
        assert mock_emit.call_count == 1
        kwargs = mock_emit.call_args[1]
        assert kwargs['event_type'] == 'tool_result'
        assert kwargs['status'] == 'error'


# ===========================================================================
# ToolGateway model validation
# ===========================================================================

@pytest.mark.blueprints
class TestModelValidation:

    def test_model_allowed_exact_match(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({
            'allowed_models': ['openai/gpt-4o', 'anthropic/claude-sonnet-4-5-20250929'],
        })
        gw = ToolGateway(ctx)

        ok, error = gw.check_model_allowed('openai/gpt-4o')
        assert ok is True
        assert error is None

    def test_model_denied(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({
            'allowed_models': ['openai/gpt-4o'],
        })
        gw = ToolGateway(ctx)

        ok, error = gw.check_model_allowed('anthropic/claude-sonnet-4-5-20250929')
        assert ok is False
        assert 'not in agent capabilities' in error

    def test_model_prefix_match(self, app, user, agent):
        """Provider prefix matches specific model."""
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({
            'allowed_models': ['openai/gpt-4o'],
        })
        gw = ToolGateway(ctx)

        # "openai" as a prefix should match "openai/gpt-4o"
        ok, error = gw.check_model_allowed('openai')
        assert ok is True

    def test_model_unrestricted_legacy(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        gw = ToolGateway(ctx)

        ok, error = gw.check_model_allowed('anything/at/all')
        assert ok is True

    def test_model_unrestricted_wildcard(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({'allowed_models': ['*']})
        gw = ToolGateway(ctx)

        ok, error = gw.check_model_allowed('anything/at/all')
        assert ok is True


# ===========================================================================
# ToolGateway list_tools filtering
# ===========================================================================

@pytest.mark.blueprints
class TestListToolsFiltering:

    def test_legacy_agent_sees_all_tools(self, app, user, agent):
        """Without capabilities, list_tools returns everything."""
        ctx = ExecutionContext.create(user.id, agent.id)
        gw = ToolGateway(ctx)

        mock_tools = [
            {'name': 'gmail_send'},
            {'name': 'binance_trade'},
            {'name': 'web_search'},
        ]

        with patch('agent_tools.get_tools_for_user', return_value=mock_tools):
            tools = gw.list_tools()

        assert len(tools) == 3

    def test_restricted_agent_sees_only_allowed(self, app, user, agent):
        """With capabilities, list_tools filters to allowed set."""
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({
            'allowed_tools': ['gmail_send', 'web_search'],
        })
        gw = ToolGateway(ctx)

        mock_tools = [
            {'name': 'gmail_send'},
            {'name': 'binance_trade'},
            {'name': 'web_search'},
        ]

        with patch('agent_tools.get_tools_for_user', return_value=mock_tools):
            tools = gw.list_tools()

        names = {t['name'] for t in tools}
        assert names == {'gmail_send', 'web_search'}

    def test_wildcard_agent_sees_all_tools(self, app, user, agent):
        ctx = ExecutionContext.create(user.id, agent.id)
        ctx = ctx.with_capabilities({'allowed_tools': ['*']})
        gw = ToolGateway(ctx)

        mock_tools = [
            {'name': 'gmail_send'},
            {'name': 'binance_trade'},
        ]

        with patch('agent_tools.get_tools_for_user', return_value=mock_tools):
            tools = gw.list_tools()

        assert len(tools) == 2


# ===========================================================================
# Runtime session capability integration
# ===========================================================================

@pytest.mark.blueprints
class TestRuntimeCapabilityIntegration:

    def test_session_loads_capabilities_from_blueprint(self, app, user, restricted_agent):
        """AgentRuntime loads blueprint capabilities at session start."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, restricted_agent.id)

        ctx = session.context
        assert ctx.has_capabilities is True
        assert ctx.allowed_tools is not None
        assert 'gmail_send' in ctx.allowed_tools
        assert 'calendar_read' in ctx.allowed_tools
        assert 'web_search' in ctx.allowed_tools

        session.stop()

    def test_session_legacy_agent_no_capabilities(self, app, user, second_agent):
        """Legacy agent (no instance) starts session without capabilities."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, second_agent.id)

        ctx = session.context
        assert ctx.has_capabilities is False
        assert ctx.allowed_tools is None

        session.stop()

    def test_session_wildcard_agent_unrestricted(self, app, user, wildcard_agent):
        """Agent with wildcard capabilities shows as unrestricted."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, wildcard_agent.id)

        ctx = session.context
        assert ctx.has_capabilities is True
        assert ctx.allowed_tools is None  # wildcard = unrestricted

        session.stop()

    def test_restricted_session_denies_tool(self, app, user, restricted_agent):
        """Tool not in blueprint capabilities is denied through session."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, restricted_agent.id)

        with patch('core.observability.ingestion.emit_event'):
            result = session.execute_tool('binance_trade', {'symbol': 'BTC'})

        assert 'error' in result
        assert result['capability_denied'] is True

        session.stop()

    def test_restricted_session_allows_tool(self, app, user, restricted_agent):
        """Tool in blueprint capabilities executes normally."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, restricted_agent.id)

        with patch('agent_tools.execute_tool', return_value={'sent': True}):
            with patch('core.observability.ingestion.emit_event'):
                result = session.execute_tool('gmail_send', {'to': 'x@y.com'})

        assert result == {'sent': True}

        session.stop()

    def test_legacy_session_allows_everything(self, app, user, second_agent):
        """Legacy agent can execute any tool."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, second_agent.id)

        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event'):
                result = session.execute_tool('any_tool_at_all')

        assert result == {'ok': True}

        session.stop()


# ===========================================================================
# Capability bundle inheritance through runtime
# ===========================================================================

@pytest.mark.blueprints
class TestCapabilityInheritance:

    def test_capability_bundles_resolve_in_session(self, app, user, capability_agent):
        """Agent with capability bundles gets resolved tool union."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, capability_agent.id)

        ctx = session.context
        assert ctx.has_capabilities is True
        tools = ctx.allowed_tools
        # Union of email + calendar bundles:
        # gmail_send, gmail_read, calendar_read, calendar_create
        assert 'gmail_send' in tools
        assert 'gmail_read' in tools
        assert 'calendar_read' in tools
        assert 'calendar_create' in tools
        # Not in any bundle:
        assert 'binance_trade' not in tools

        session.stop()

    def test_capability_bundles_restrict_models(self, app, user, capability_agent):
        """Model constraints are intersection across bundles."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, capability_agent.id)

        gw = session.tools

        # email_cap: openai, anthropic
        # calendar_cap: openai
        # intersection: openai only
        ok, _ = gw.check_model_allowed('openai')
        assert ok is True

        ok, error = gw.check_model_allowed('anthropic')
        assert ok is False

        session.stop()

    def test_denied_tool_via_bundles(self, app, user, capability_agent):
        """Tool not in any capability bundle is denied at execution."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, capability_agent.id)

        with patch('core.observability.ingestion.emit_event'):
            result = session.execute_tool('binance_trade')

        assert result['capability_denied'] is True

        session.stop()

    def test_allowed_tool_via_bundles(self, app, user, capability_agent):
        """Tool in a capability bundle executes normally."""
        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, capability_agent.id)

        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event'):
                result = session.execute_tool('gmail_read')

        assert result == {'ok': True}

        session.stop()


# ===========================================================================
# Edge cases
# ===========================================================================

@pytest.mark.blueprints
class TestCapabilityEdgeCases:

    def test_blueprint_tables_missing_fails_open(self, app, user, agent):
        """If blueprint tables don't exist, agent runs as legacy."""
        rt = AgentRuntime(workspace_id=user.id)

        # Simulate import error in _load_capabilities
        with patch('core.identity.agent_instance.get_agent_instance',
                   side_effect=Exception('table missing')):
            session = rt.start_session(user.id, agent.id)

        assert session.context.has_capabilities is False

        session.stop()

    def test_instance_with_empty_snapshot(self, app, user, agent, restricted_blueprint):
        """Instance with empty policy_snapshot treated as legacy."""
        from models import AgentInstance
        instance = AgentInstance(
            agent_id=agent.id,
            blueprint_id=restricted_blueprint.id,
            blueprint_version=1,
            workspace_id=user.id,
            overrides=None,
            policy_snapshot={},  # empty
            instantiated_by=user.id,
        )
        db.session.add(instance)
        db.session.commit()

        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, agent.id)

        # Empty snapshot means no capabilities loaded
        assert session.context.has_capabilities is False

        session.stop()

    def test_multiple_sessions_different_capabilities(self, app, user, agent, second_agent,
                                                        restricted_blueprint):
        """Two agents in same workspace can have different capabilities."""
        # agent = restricted, second_agent = legacy
        instantiate_agent(
            agent_id=agent.id,
            blueprint_id=restricted_blueprint.id,
            version=1,
            workspace_id=user.id,
            instantiated_by=user.id,
        )

        rt = AgentRuntime(workspace_id=user.id)
        s1 = rt.start_session(user.id, agent.id)
        s2 = rt.start_session(user.id, second_agent.id)

        assert s1.context.has_capabilities is True
        assert s2.context.has_capabilities is False

        # s1 is restricted
        with patch('core.observability.ingestion.emit_event'):
            result = s1.execute_tool('binance_trade')
        assert result['capability_denied'] is True

        # s2 is unrestricted
        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event'):
                result = s2.execute_tool('binance_trade')
        assert result == {'ok': True}

        s1.stop()
        s2.stop()
