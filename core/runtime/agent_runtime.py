"""
AgentRuntime — governed lifecycle manager for autonomous agent sessions.

An AgentRuntime instance is scoped to a single workspace.  It can start
sessions for any agent that belongs to that workspace, and those sessions
can exchange messages through a governed message bus.

No global mutable state: the runtime holds its own session registry.
Two AgentRuntime instances for different workspaces share nothing.
"""
from __future__ import annotations

import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.runtime.execution_context import ExecutionContext
from core.runtime.tool_gateway import ToolGateway


# -------------------------------------------------------------------------
# Message primitive
# -------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentMessage:
    """Immutable message exchanged between agents within a workspace."""
    id: str
    from_agent_id: int
    to_agent_id: int
    workspace_id: int
    content: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)


# -------------------------------------------------------------------------
# Session — the active handle an agent works through
# -------------------------------------------------------------------------

class RuntimeSession:
    """Active, governed session for a single agent.

    Provides scoped tool access and inter-agent messaging.
    Must be obtained via ``AgentRuntime.start_session()``; should not be
    constructed directly.
    """

    def __init__(self, ctx: ExecutionContext, runtime: AgentRuntime) -> None:
        self._ctx = ctx
        self._runtime = runtime
        self._gateway = ToolGateway(ctx)
        self._stopped = False

    @property
    def context(self) -> ExecutionContext:
        return self._ctx

    @property
    def tools(self) -> ToolGateway:
        return self._gateway

    @property
    def is_active(self) -> bool:
        return not self._stopped

    # --- tool execution (convenience delegation) -------------------------

    def execute_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        self._assert_active()
        return self._gateway.execute(tool_name, arguments)

    def list_tools(self) -> list[dict]:
        self._assert_active()
        return self._gateway.list_tools()

    # --- inter-agent messaging -------------------------------------------

    def send_message(self, to_agent_id: int, content: dict[str, Any]) -> AgentMessage:
        """Send a message to another agent in the same workspace.

        Raises:
            PermissionError: if the target agent is not in this workspace.
            RuntimeError: if the session has been stopped.
        """
        self._assert_active()
        return self._runtime._deliver_message(self._ctx, to_agent_id, content)

    def receive_messages(self) -> list[AgentMessage]:
        """Drain the inbox for this agent. Returns messages in send order."""
        self._assert_active()
        return self._runtime._drain_inbox(self._ctx)

    # --- lifecycle -------------------------------------------------------

    def stop(self, status: str = 'success', error: str | None = None) -> None:
        """Finalize this session's observability run."""
        if self._stopped:
            return
        self._stopped = True
        self._runtime._finalize_session(self._ctx, status, error)

    def _assert_active(self) -> None:
        if self._stopped:
            raise RuntimeError(
                f'Session for agent {self._ctx.agent_id} (run {self._ctx.run_id}) '
                f'has been stopped'
            )


# -------------------------------------------------------------------------
# AgentRuntime — workspace-scoped manager
# -------------------------------------------------------------------------

class AgentRuntime:
    """Governed runtime for one workspace.

    Holds:
        - a registry of active sessions (thread-safe)
        - per-agent message inboxes

    Create one per workspace; never share across workspaces.
    """

    def __init__(self, workspace_id: int) -> None:
        self._workspace_id = workspace_id
        self._lock = threading.Lock()
        self._sessions: dict[str, RuntimeSession] = {}          # run_id -> session
        self._inboxes: dict[int, deque[AgentMessage]] = defaultdict(deque)  # agent_id -> messages

    @property
    def workspace_id(self) -> int:
        return self._workspace_id

    # --- session lifecycle -----------------------------------------------

    def start_session(self, user_id: int, agent_id: int) -> RuntimeSession:
        """Start a governed session for *agent_id* in this workspace.

        1. Creates an ExecutionContext (verifies ownership).
        2. Loads blueprint capabilities if the agent has an instance binding.
        3. Checks pre-start governance (tier limits, risk policies).
        4. Opens an observability run.
        5. Returns a RuntimeSession handle.

        Raises:
            PermissionError: Agent does not belong to this workspace.
            RuntimeError: Governance check blocks the session.
        """
        ctx = ExecutionContext.create(user_id, agent_id)

        if ctx.workspace_id != self._workspace_id:
            raise PermissionError(
                f'Agent {agent_id} resolved to workspace {ctx.workspace_id}, '
                f'but this runtime serves workspace {self._workspace_id}'
            )

        # Load blueprint capabilities (if agent has an instance binding)
        ctx = self._load_capabilities(ctx)

        # Pre-start governance
        self._pre_start_check(ctx)

        # Open observability run
        self._start_obs_run(ctx)

        session = RuntimeSession(ctx, self)
        with self._lock:
            self._sessions[ctx.run_id] = session

        return session

    def get_session(self, run_id: str) -> RuntimeSession | None:
        """Look up an active session by run_id."""
        with self._lock:
            return self._sessions.get(run_id)

    def active_sessions(self) -> list[RuntimeSession]:
        """Snapshot of currently active sessions."""
        with self._lock:
            return [s for s in self._sessions.values() if s.is_active]

    # --- inter-agent messaging (internal) --------------------------------

    def _deliver_message(self, from_ctx: ExecutionContext,
                         to_agent_id: int, content: dict) -> AgentMessage:
        """Route a message between agents in this workspace."""
        from core.observability.workspace import verify_agent_ownership

        target = verify_agent_ownership(to_agent_id, self._workspace_id)
        if target is None:
            raise PermissionError(
                f'Agent {to_agent_id} does not belong to workspace {self._workspace_id}'
            )

        msg = AgentMessage(
            id=str(uuid.uuid4()),
            from_agent_id=from_ctx.agent_id,
            to_agent_id=to_agent_id,
            workspace_id=self._workspace_id,
            content=content,
        )

        with self._lock:
            self._inboxes[to_agent_id].append(msg)

        # Emit observability event for the message
        try:
            from core.observability.ingestion import emit_event
            emit_event(
                user_id=self._workspace_id,
                event_type='action_started',
                status='info',
                agent_id=from_ctx.agent_id,
                run_id=from_ctx.run_id,
                payload={
                    'type': 'agent_message',
                    'to_agent_id': to_agent_id,
                    'message_id': msg.id,
                },
            )
        except Exception:
            pass

        return msg

    def _drain_inbox(self, ctx: ExecutionContext) -> list[AgentMessage]:
        with self._lock:
            inbox = self._inboxes.get(ctx.agent_id)
            if not inbox:
                return []
            messages = list(inbox)
            inbox.clear()
            return messages

    # --- session finalization --------------------------------------------

    def _finalize_session(self, ctx: ExecutionContext,
                          status: str, error: str | None) -> None:
        self._finish_obs_run(ctx, status, error)
        with self._lock:
            self._sessions.pop(ctx.run_id, None)

    # --- blueprint capabilities ------------------------------------------

    def _load_capabilities(self, ctx: ExecutionContext) -> ExecutionContext:
        """Load blueprint capabilities for the agent, if an instance exists.

        If the agent has an AgentInstance binding, the policy_snapshot is
        attached to the context. Legacy agents (no instance) get None.

        Returns a new context with capabilities attached (or the original
        context unchanged for legacy agents).
        """
        try:
            from core.identity.agent_instance import get_agent_instance
            instance = get_agent_instance(ctx.agent_id)
            if instance is not None and instance.policy_snapshot:
                return ctx.with_capabilities(instance.policy_snapshot)
        except Exception:
            # Blueprint tables may not exist (e.g., during migrations).
            # Fail open — treat as legacy agent.
            pass
        return ctx

    # --- governance ------------------------------------------------------

    def _pre_start_check(self, ctx: ExecutionContext) -> None:
        """Run governance checks before allowing a session to begin.

        Only checks agent-relevant limits (not alert rules, API keys, etc.).
        """
        try:
            from core.observability.tier_enforcement import (
                check_agent_limit, check_agent_allowed,
            )

            allowed, reason = check_agent_limit(ctx.workspace_id)
            if not allowed:
                raise RuntimeError(f'Workspace limit reached: {reason}')

            agent_ok, agent_reason = check_agent_allowed(
                ctx.workspace_id, ctx.agent_id,
            )
            if not agent_ok:
                raise RuntimeError(f'Agent blocked: {agent_reason}')
        except (ImportError, Exception) as exc:
            # If governance tables are missing (e.g. local dev with SQLite),
            # fail open so the runtime is still usable.
            if isinstance(exc, RuntimeError):
                raise

    # --- observability helpers -------------------------------------------

    def _start_obs_run(self, ctx: ExecutionContext) -> None:
        try:
            from core.observability.run_tracker import start_run
            start_run(
                user_id=ctx.workspace_id,
                agent_id=ctx.agent_id,
                metadata={'source': 'agent_runtime'},
            )
        except Exception:
            pass

    def _finish_obs_run(self, ctx: ExecutionContext,
                        status: str, error: str | None) -> None:
        try:
            from core.observability.run_tracker import finish_run
            finish_run(
                run_id=ctx.run_id,
                status=status,
                error_message=error,
            )
        except Exception:
            pass
