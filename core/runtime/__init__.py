"""
core.runtime — Governed multi-agent runtime.

Public API:
    ExecutionContext       — immutable scope for every operation
    ToolGateway            — scoped tool execution with observability + governance
    AgentRuntime           — lifecycle manager for agent sessions
"""

from core.runtime.execution_context import ExecutionContext
from core.runtime.tool_gateway import ToolGateway
from core.runtime.agent_runtime import AgentRuntime

__all__ = ['ExecutionContext', 'ToolGateway', 'AgentRuntime']
