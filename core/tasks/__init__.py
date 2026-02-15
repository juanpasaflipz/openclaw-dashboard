"""
core.tasks — Approval queue and action execution domain.

Public API:
    get_pending_actions       — list pending actions for a user
    approve_and_execute       — approve + execute an action
    reject_action             — reject a pending action
    create_action             — enqueue a new action
    execute_action            — dispatch to the right adapter
    get_handler               — look up an executor by (action_type, service_type)
"""

from core.tasks.queue import (
    get_pending_actions,
    approve_and_execute,
    reject_action,
    create_action,
)
from core.tasks.executor import execute_action, get_handler

__all__ = [
    'get_pending_actions',
    'approve_and_execute',
    'reject_action',
    'create_action',
    'execute_action',
    'get_handler',
]
