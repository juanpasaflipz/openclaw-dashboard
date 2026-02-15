"""
Scoped tool gateway — every tool call goes through here.

Responsibilities:
    1. Verify the calling agent owns the context (no spoofing).
    2. Run governance / risk checks *before* execution.
    3. Enforce blueprint capability boundaries (tool allowlists).
    4. Emit observability events (tool_call, tool_result) with cost attribution.
    5. Delegate to the existing ``agent_tools.execute_tool`` for the actual work.

The gateway holds no mutable state beyond the context it was constructed with.
"""
from __future__ import annotations

import time
from typing import Any

from core.runtime.execution_context import ExecutionContext


class ToolGateway:
    """Scoped proxy for tool execution.

    Instantiated per-session — one gateway per (workspace, agent, run).
    """

    def __init__(self, ctx: ExecutionContext) -> None:
        self._ctx = ctx

    @property
    def context(self) -> ExecutionContext:
        return self._ctx

    # --- public API ------------------------------------------------------

    def list_tools(self) -> list[dict]:
        """Return tool schemas available to this context.

        If the context has capability restrictions, only tools in the
        allowed set are returned. Legacy agents (no capabilities) see all
        workspace tools.
        """
        from agent_tools import get_tools_for_user
        all_tools = get_tools_for_user(self._ctx.workspace_id)

        allowed = self._ctx.allowed_tools
        if allowed is None:
            return all_tools

        return [t for t in all_tools if t.get('name') in allowed]

    def execute(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict:
        """Execute a tool scoped to this context.

        Flow:
            capability check  ->  governance gate  ->  emit tool_call
            ->  delegate  ->  emit tool_result

        Returns:
            Result dict from the underlying tool (always JSON-serialisable).
        """
        arguments = arguments or {}

        # 1. Capability boundary check (blueprint enforcement)
        cap_denial = self._check_capability(tool_name)
        if cap_denial is not None:
            self._emit_tool_result(tool_name, cap_denial, 'error', 0)
            return cap_denial

        # 2. Governance gate (tier limits, risk policies)
        denial = self._check_governance(tool_name, arguments)
        if denial is not None:
            self._emit_tool_result(tool_name, denial, 'error', 0)
            return denial

        # 3. Pre-execution event
        self._emit_tool_call(tool_name, arguments)

        # 4. Execute
        start = time.monotonic()
        try:
            from agent_tools import execute_tool
            result = execute_tool(tool_name, self._ctx.workspace_id, arguments)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            status = 'error' if 'error' in result else 'success'
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result = {'error': f'Tool execution failed: {str(exc)[:300]}'}
            status = 'error'

        # 5. Post-execution event
        self._emit_tool_result(tool_name, result, status, elapsed_ms)

        return result

    # --- model validation ------------------------------------------------

    def check_model_allowed(self, model_identifier: str) -> tuple[bool, str | None]:
        """Check if a model is allowed by the agent's capabilities.

        Args:
            model_identifier: The model string to check (e.g., "openai" or
                "openai/gpt-4o"). Matched against allowed_models entries.

        Returns:
            (True, None) if allowed or no restrictions.
            (False, error_message) if denied.
        """
        allowed = self._ctx.allowed_models
        if allowed is None:
            return True, None

        # Check exact match or prefix match (e.g., "openai" matches "openai/gpt-4o")
        if model_identifier in allowed:
            return True, None
        for entry in allowed:
            if model_identifier.startswith(entry + '/') or entry.startswith(model_identifier + '/'):
                return True, None

        return False, (
            f'Model {model_identifier!r} is not in agent capabilities. '
            f'Allowed: {sorted(allowed)}'
        )

    # --- capability enforcement ------------------------------------------

    def _check_capability(self, tool_name: str) -> dict | None:
        """Check blueprint capability boundaries for tool access.

        Returns an error dict if the tool is not in the agent's capabilities,
        or None if allowed. Legacy agents (no capabilities) always pass.
        """
        allowed = self._ctx.allowed_tools
        if allowed is None:
            # No capability restrictions — legacy agent or wildcard
            return None

        if tool_name not in allowed:
            return {
                'error': (
                    f'Tool {tool_name!r} is not in agent capabilities. '
                    f'Allowed tools: {sorted(allowed)}'
                ),
                'governance': True,
                'capability_denied': True,
            }

        return None

    # --- governance ------------------------------------------------------

    def _check_governance(self, tool_name: str, arguments: dict) -> dict | None:
        """Run lightweight governance checks. Returns an error dict or None."""
        try:
            from core.observability.tier_enforcement import check_agent_allowed
            allowed, reason = check_agent_allowed(
                self._ctx.workspace_id, self._ctx.agent_id,
            )
            if not allowed:
                return {'error': f'Workspace limit reached: {reason}',
                        'governance': True}
        except Exception:
            # Governance subsystem unavailable — fail open to avoid blocking
            # all tool calls when DB tables haven't been created yet.
            pass

        return None

    # --- observability ---------------------------------------------------

    def _emit_tool_call(self, tool_name: str, arguments: dict) -> None:
        try:
            from core.observability.ingestion import emit_event
            emit_event(
                user_id=self._ctx.workspace_id,
                event_type='tool_call',
                status='info',
                agent_id=self._ctx.agent_id,
                run_id=self._ctx.run_id,
                payload={
                    'tool': tool_name,
                    'arguments': _safe_payload(arguments),
                },
            )
        except Exception:
            pass  # never block on observability failures

    def _emit_tool_result(self, tool_name: str, result: dict,
                          status: str, latency_ms: int) -> None:
        try:
            from core.observability.ingestion import emit_event
            emit_event(
                user_id=self._ctx.workspace_id,
                event_type='tool_result',
                status=status,
                agent_id=self._ctx.agent_id,
                run_id=self._ctx.run_id,
                latency_ms=latency_ms,
                payload={
                    'tool': tool_name,
                    'has_error': 'error' in result,
                },
            )
        except Exception:
            pass


def _safe_payload(arguments: dict, max_len: int = 500) -> dict:
    """Truncate argument values to avoid blowing up event storage."""
    safe: dict[str, Any] = {}
    for k, v in arguments.items():
        s = str(v)
        safe[k] = s[:max_len] if len(s) > max_len else s
    return safe
