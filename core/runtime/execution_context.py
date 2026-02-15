"""
Immutable execution context — scopes every runtime operation.

An ExecutionContext binds a workspace, agent, and observability run together.
It is threaded through every tool call and message so that ownership,
cost attribution, and audit trail are always unambiguous.

No mutable state lives here; create a new context for a new scope.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable scope token for a single agent execution.

    Every tool invocation, message dispatch, and governance check receives
    this object.  Because it is frozen, it cannot be mutated after creation
    — an agent cannot escalate its own privileges by changing workspace_id.
    """

    workspace_id: int
    agent_id: int
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Blueprint capability snapshot — None means legacy agent (no restrictions).
    # When set, contains: {allowed_tools, allowed_models, risk_profile, ...}
    resolved_capabilities: dict[str, Any] | None = field(default=None, repr=False)

    # --- factories -------------------------------------------------------

    @classmethod
    def create(cls, user_id: int, agent_id: int, run_id: str | None = None) -> ExecutionContext:
        """Build a context after verifying the agent belongs to the workspace.

        Args:
            user_id: The authenticated user (maps to workspace_id in v1).
            agent_id: The agent that will operate under this context.
            run_id: Optional explicit run id (generated if omitted).

        Raises:
            PermissionError: If the agent does not belong to the workspace.
        """
        from core.observability.workspace import get_workspace_id, verify_agent_ownership

        workspace_id = get_workspace_id(user_id)
        agent = verify_agent_ownership(agent_id, user_id)
        if agent is None:
            raise PermissionError(
                f'Agent {agent_id} does not belong to workspace {workspace_id}'
            )

        return cls(
            workspace_id=workspace_id,
            agent_id=agent_id,
            run_id=run_id or str(uuid.uuid4()),
        )

    def with_capabilities(self, capabilities: dict[str, Any]) -> ExecutionContext:
        """Return a new context with blueprint capabilities attached.

        The original context is not mutated (frozen dataclass).
        Used by AgentRuntime to attach resolved capabilities at session start.

        Args:
            capabilities: Resolved capability dict from AgentInstance.policy_snapshot.

        Returns:
            A new ExecutionContext with resolved_capabilities set.
        """
        return ExecutionContext(
            workspace_id=self.workspace_id,
            agent_id=self.agent_id,
            run_id=self.run_id,
            created_at=self.created_at,
            resolved_capabilities=capabilities,
        )

    def for_agent(self, agent_id: int) -> ExecutionContext:
        """Derive a sibling context for another agent in the *same* workspace.

        Used for intra-workspace collaboration: agent A spawns a task for
        agent B, both sharing the same workspace scope.  A new run_id is
        generated so their cost/observability streams stay separate.

        Raises:
            PermissionError: If the target agent is not in this workspace.
        """
        from core.observability.workspace import verify_agent_ownership

        agent = verify_agent_ownership(agent_id, self.workspace_id)
        if agent is None:
            raise PermissionError(
                f'Agent {agent_id} does not belong to workspace {self.workspace_id}'
            )

        return ExecutionContext(
            workspace_id=self.workspace_id,
            agent_id=agent_id,
        )

    # --- capability queries ----------------------------------------------

    @property
    def has_capabilities(self) -> bool:
        """True if this context has blueprint-resolved capabilities."""
        return self.resolved_capabilities is not None

    @property
    def allowed_tools(self) -> set[str] | None:
        """The set of allowed tool names, or None for unrestricted (legacy).

        Returns None if no capabilities are set or if the allowlist is ["*"].
        """
        if self.resolved_capabilities is None:
            return None
        tools = self.resolved_capabilities.get('allowed_tools', [])
        if not tools or tools == ['*']:
            return None
        return set(tools)

    @property
    def allowed_models(self) -> set[str] | None:
        """The set of allowed model identifiers, or None for unrestricted (legacy).

        Returns None if no capabilities are set or if the allowlist is ["*"].
        """
        if self.resolved_capabilities is None:
            return None
        models = self.resolved_capabilities.get('allowed_models', [])
        if not models or models == ['*']:
            return None
        return set(models)

    # --- helpers ---------------------------------------------------------

    def as_dict(self) -> dict:
        """Serialise to a plain dict (useful for logging / event payloads)."""
        d = {
            'workspace_id': self.workspace_id,
            'agent_id': self.agent_id,
            'run_id': self.run_id,
            'created_at': self.created_at.isoformat(),
        }
        if self.resolved_capabilities is not None:
            d['has_capabilities'] = True
        return d
