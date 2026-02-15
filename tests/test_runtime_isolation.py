"""
Tests for core.runtime — agent isolation, scoped tool execution, and governance.

Verifies that:
    - One agent cannot act as another agent.
    - Cross-workspace operations are rejected.
    - Tool calls carry correct workspace_id + agent_id.
    - Observability events are emitted with proper scoping.
    - Stopped sessions reject further operations.
    - Inter-agent messages respect workspace boundaries.
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers — mock governance & obs so tests run on SQLite without obs tables
# ---------------------------------------------------------------------------

def _noop_pre_start(self, ctx):
    """Skip tier-enforcement checks that require obs tables."""
    pass


def _noop_obs(*args, **kwargs):
    """No-op replacement for observability run tracking."""
    pass


# Decorator to bypass governance + obs in session lifecycle tests
_bypass_governance = patch.object(
    __import__('core.runtime.agent_runtime', fromlist=['AgentRuntime']).AgentRuntime,
    '_pre_start_check', _noop_pre_start,
)
_bypass_start_obs = patch(
    'core.runtime.agent_runtime.AgentRuntime._start_obs_run', _noop_obs,
)
_bypass_finish_obs = patch(
    'core.runtime.agent_runtime.AgentRuntime._finish_obs_run', _noop_obs,
)


def _session_patches():
    """Context manager stack that bypasses governance + obs for session tests."""
    import contextlib
    return contextlib.ExitStack()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def second_user(app):
    """A second user in a separate workspace."""
    from models import User, db

    user = User(
        email='other@example.com',
        created_at=datetime.utcnow(),
        credit_balance=10,
        subscription_tier='free',
        subscription_status='inactive',
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def second_agent(app, second_user):
    """An agent owned by the second user."""
    from models import Agent, db

    agent = Agent(
        user_id=second_user.id,
        name='OtherAgent',
        description='Agent for other workspace',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(agent)
    db.session.commit()
    return agent


@pytest.fixture
def collaborator_agent(app, user):
    """A second agent in the same workspace as ``user``."""
    from models import Agent, db

    agent = Agent(
        user_id=user.id,
        name='CollabAgent',
        description='Collaborator in same workspace',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(agent)
    db.session.commit()
    return agent


@pytest.fixture(autouse=True)
def _mock_session_infra():
    """Bypass governance tier checks and obs run tracking for all tests."""
    from core.runtime.agent_runtime import AgentRuntime
    with patch.object(AgentRuntime, '_pre_start_check', _noop_pre_start), \
         patch.object(AgentRuntime, '_start_obs_run', _noop_obs), \
         patch.object(AgentRuntime, '_finish_obs_run', _noop_obs):
        yield


# ---------------------------------------------------------------------------
# ExecutionContext isolation
# ---------------------------------------------------------------------------

class TestExecutionContextIsolation:
    """Verify that ExecutionContext enforces workspace-agent binding."""

    def test_create_valid_context(self, app, user, agent):
        from core.runtime.execution_context import ExecutionContext

        ctx = ExecutionContext.create(user.id, agent.id)
        assert ctx.workspace_id == user.id
        assert ctx.agent_id == agent.id
        assert ctx.run_id  # non-empty

    def test_create_rejects_foreign_agent(self, app, user, second_agent):
        """User cannot create a context for an agent they don't own."""
        from core.runtime.execution_context import ExecutionContext

        with pytest.raises(PermissionError, match='does not belong'):
            ExecutionContext.create(user.id, second_agent.id)

    def test_create_rejects_nonexistent_agent(self, app, user):
        from core.runtime.execution_context import ExecutionContext

        with pytest.raises(PermissionError, match='does not belong'):
            ExecutionContext.create(user.id, 999999)

    def test_for_agent_same_workspace(self, app, user, agent, collaborator_agent):
        """Deriving a context for a sibling agent succeeds."""
        from core.runtime.execution_context import ExecutionContext

        ctx = ExecutionContext.create(user.id, agent.id)
        sibling = ctx.for_agent(collaborator_agent.id)

        assert sibling.workspace_id == ctx.workspace_id
        assert sibling.agent_id == collaborator_agent.id
        assert sibling.run_id != ctx.run_id  # new run

    def test_for_agent_cross_workspace_rejected(self, app, user, agent, second_agent):
        """Cannot derive context for an agent in a different workspace."""
        from core.runtime.execution_context import ExecutionContext

        ctx = ExecutionContext.create(user.id, agent.id)

        with pytest.raises(PermissionError, match='does not belong'):
            ctx.for_agent(second_agent.id)

    def test_context_is_immutable(self, app, user, agent):
        """Frozen dataclass prevents attribute mutation."""
        from core.runtime.execution_context import ExecutionContext

        ctx = ExecutionContext.create(user.id, agent.id)

        with pytest.raises(AttributeError):
            ctx.workspace_id = 9999

        with pytest.raises(AttributeError):
            ctx.agent_id = 9999

    def test_as_dict(self, app, user, agent):
        from core.runtime.execution_context import ExecutionContext

        ctx = ExecutionContext.create(user.id, agent.id)
        d = ctx.as_dict()
        assert d['workspace_id'] == user.id
        assert d['agent_id'] == agent.id
        assert 'run_id' in d
        assert 'created_at' in d


# ---------------------------------------------------------------------------
# ToolGateway scoping
# ---------------------------------------------------------------------------

class TestToolGatewayScoping:
    """Verify tool calls are scoped by workspace_id + agent_id."""

    def test_execute_delegates_with_workspace_id(self, app, user, agent):
        """Tool execution uses the context's workspace_id, not an arbitrary user."""
        from core.runtime.execution_context import ExecutionContext
        from core.runtime.tool_gateway import ToolGateway

        ctx = ExecutionContext.create(user.id, agent.id)
        gw = ToolGateway(ctx)

        with patch('core.observability.ingestion.emit_event'):
            with patch('agent_tools.execute_tool', return_value={'ok': True}) as mock_exec:
                result = gw.execute('list_connected_services', {})

            mock_exec.assert_called_once_with(
                'list_connected_services', ctx.workspace_id, {},
            )
        assert result == {'ok': True}

    def test_execute_emits_tool_call_event(self, app, user, agent):
        """Pre-execution observability event carries correct agent_id."""
        from core.runtime.execution_context import ExecutionContext
        from core.runtime.tool_gateway import ToolGateway

        ctx = ExecutionContext.create(user.id, agent.id)
        gw = ToolGateway(ctx)

        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event') as mock_emit:
                gw.execute('some_tool', {'key': 'val'})

        # Should have emitted tool_call and tool_result
        assert mock_emit.call_count == 2

        # First call: tool_call
        call_kwargs = mock_emit.call_args_list[0][1]
        assert call_kwargs['user_id'] == ctx.workspace_id
        assert call_kwargs['agent_id'] == ctx.agent_id
        assert call_kwargs['run_id'] == ctx.run_id
        assert call_kwargs['event_type'] == 'tool_call'

        # Second call: tool_result
        result_kwargs = mock_emit.call_args_list[1][1]
        assert result_kwargs['event_type'] == 'tool_result'
        assert result_kwargs['agent_id'] == ctx.agent_id
        assert result_kwargs['status'] == 'success'

    def test_execute_reports_error_status(self, app, user, agent):
        """Error results emit status='error' on the tool_result event."""
        from core.runtime.execution_context import ExecutionContext
        from core.runtime.tool_gateway import ToolGateway

        ctx = ExecutionContext.create(user.id, agent.id)
        gw = ToolGateway(ctx)

        with patch('agent_tools.execute_tool', return_value={'error': 'boom'}):
            with patch('core.observability.ingestion.emit_event') as mock_emit:
                result = gw.execute('bad_tool')

        assert 'error' in result
        result_kwargs = mock_emit.call_args_list[1][1]
        assert result_kwargs['status'] == 'error'

    def test_execute_catches_exception(self, app, user, agent):
        """If the underlying tool raises, gateway catches and returns error dict."""
        from core.runtime.execution_context import ExecutionContext
        from core.runtime.tool_gateway import ToolGateway

        ctx = ExecutionContext.create(user.id, agent.id)
        gw = ToolGateway(ctx)

        with patch('agent_tools.execute_tool', side_effect=ValueError('kaboom')):
            with patch('core.observability.ingestion.emit_event'):
                result = gw.execute('exploding_tool')

        assert 'error' in result
        assert 'kaboom' in result['error']

    def test_governance_blocks_tool_execution(self, app, user, agent):
        """If governance denies, no tool execution happens."""
        from core.runtime.execution_context import ExecutionContext
        from core.runtime.tool_gateway import ToolGateway

        ctx = ExecutionContext.create(user.id, agent.id)
        gw = ToolGateway(ctx)

        with patch.object(gw, '_check_governance',
                          return_value={'error': 'rate limited', 'governance': True}):
            with patch('agent_tools.execute_tool') as mock_exec:
                result = gw.execute('any_tool')

        mock_exec.assert_not_called()
        assert result['governance'] is True


# ---------------------------------------------------------------------------
# AgentRuntime isolation
# ---------------------------------------------------------------------------

class TestAgentRuntimeIsolation:
    """Verify workspace-level isolation in AgentRuntime."""

    def test_start_session_valid(self, app, user, agent):
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, agent.id)

        assert session.is_active
        assert session.context.workspace_id == user.id
        assert session.context.agent_id == agent.id

        session.stop()

    def test_start_session_rejects_foreign_agent(self, app, user, second_agent):
        """Cannot start a session for an agent from another workspace."""
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)

        with pytest.raises(PermissionError, match='does not belong'):
            rt.start_session(user.id, second_agent.id)

    def test_start_session_rejects_workspace_mismatch(self, app, user, agent, second_user):
        """Even if agent belongs to user, the runtime workspace must match."""
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=second_user.id)

        with pytest.raises(PermissionError):
            rt.start_session(user.id, agent.id)

    def test_two_runtimes_share_nothing(self, app, user, agent, second_user, second_agent):
        """Sessions in different runtimes have no cross-contamination."""
        from core.runtime.agent_runtime import AgentRuntime

        rt1 = AgentRuntime(workspace_id=user.id)
        rt2 = AgentRuntime(workspace_id=second_user.id)

        s1 = rt1.start_session(user.id, agent.id)
        s2 = rt2.start_session(second_user.id, second_agent.id)

        # Each runtime only knows about its own session
        assert len(rt1.active_sessions()) == 1
        assert len(rt2.active_sessions()) == 1

        assert rt1.get_session(s2.context.run_id) is None
        assert rt2.get_session(s1.context.run_id) is None

        s1.stop()
        s2.stop()

    def test_stopped_session_rejects_tool_calls(self, app, user, agent):
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, agent.id)
        session.stop()

        with pytest.raises(RuntimeError, match='has been stopped'):
            session.execute_tool('any_tool')

    def test_stopped_session_rejects_messages(self, app, user, agent, collaborator_agent):
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, agent.id)
        session.stop()

        with pytest.raises(RuntimeError, match='has been stopped'):
            session.send_message(collaborator_agent.id, {'text': 'hi'})

    def test_stop_is_idempotent(self, app, user, agent):
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, agent.id)
        session.stop()
        session.stop()  # should not raise

    def test_session_removed_after_stop(self, app, user, agent):
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        session = rt.start_session(user.id, agent.id)
        run_id = session.context.run_id

        session.stop()

        assert rt.get_session(run_id) is None
        assert len(rt.active_sessions()) == 0


# ---------------------------------------------------------------------------
# Inter-agent messaging
# ---------------------------------------------------------------------------

class TestInterAgentMessaging:
    """Verify message routing and workspace boundaries."""

    def test_send_receive_same_workspace(self, app, user, agent, collaborator_agent):
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        s1 = rt.start_session(user.id, agent.id)
        s2 = rt.start_session(user.id, collaborator_agent.id)

        with patch('core.observability.ingestion.emit_event'):
            msg = s1.send_message(collaborator_agent.id, {'task': 'summarize'})

        assert msg.from_agent_id == agent.id
        assert msg.to_agent_id == collaborator_agent.id
        assert msg.workspace_id == user.id

        inbox = s2.receive_messages()
        assert len(inbox) == 1
        assert inbox[0].id == msg.id
        assert inbox[0].content == {'task': 'summarize'}

        # Inbox is drained
        assert s2.receive_messages() == []

        s1.stop()
        s2.stop()

    def test_send_to_foreign_agent_rejected(self, app, user, agent, second_agent):
        """Cannot send a message to an agent in a different workspace."""
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        s = rt.start_session(user.id, agent.id)

        with pytest.raises(PermissionError, match='does not belong'):
            s.send_message(second_agent.id, {'text': 'hello'})

        s.stop()

    def test_messages_isolated_between_workspaces(self, app, user, agent,
                                                   second_user, second_agent):
        """Messages in workspace A do not appear in workspace B."""
        from core.runtime.agent_runtime import AgentRuntime

        rt_a = AgentRuntime(workspace_id=user.id)
        rt_b = AgentRuntime(workspace_id=second_user.id)

        s_a = rt_a.start_session(user.id, agent.id)
        s_b = rt_b.start_session(second_user.id, second_agent.id)

        # Nothing in either inbox
        assert s_a.receive_messages() == []
        assert s_b.receive_messages() == []

        s_a.stop()
        s_b.stop()


# ---------------------------------------------------------------------------
# Multi-session collaboration
# ---------------------------------------------------------------------------

class TestMultiSessionCollaboration:
    """Verify multiple agents can collaborate within a single workspace."""

    def test_multiple_sessions_in_one_workspace(self, app, user, agent, collaborator_agent):
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        s1 = rt.start_session(user.id, agent.id)
        s2 = rt.start_session(user.id, collaborator_agent.id)

        assert len(rt.active_sessions()) == 2

        # Both can execute tools independently
        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event'):
                r1 = s1.execute_tool('list_connected_services')
                r2 = s2.execute_tool('list_connected_services')

        assert r1 == {'ok': True}
        assert r2 == {'ok': True}

        s1.stop()
        assert len(rt.active_sessions()) == 1
        s2.stop()
        assert len(rt.active_sessions()) == 0

    def test_tool_calls_carry_distinct_agent_ids(self, app, user, agent, collaborator_agent):
        """Each session's tool calls carry the correct agent_id."""
        from core.runtime.agent_runtime import AgentRuntime

        rt = AgentRuntime(workspace_id=user.id)
        s1 = rt.start_session(user.id, agent.id)
        s2 = rt.start_session(user.id, collaborator_agent.id)

        emitted_events = []

        def capture_emit(**kwargs):
            emitted_events.append(kwargs)

        with patch('agent_tools.execute_tool', return_value={'ok': True}):
            with patch('core.observability.ingestion.emit_event', side_effect=capture_emit):
                s1.execute_tool('tool_a')
                s2.execute_tool('tool_b')

        # Should have 4 events: tool_call + tool_result for each session
        assert len(emitted_events) == 4

        s1_events = [e for e in emitted_events if e['agent_id'] == agent.id]
        s2_events = [e for e in emitted_events if e['agent_id'] == collaborator_agent.id]

        assert len(s1_events) == 2
        assert len(s2_events) == 2

        # Verify run_ids are distinct
        s1_run_ids = {e['run_id'] for e in s1_events}
        s2_run_ids = {e['run_id'] for e in s2_events}
        assert s1_run_ids.isdisjoint(s2_run_ids)

        s1.stop()
        s2.stop()
