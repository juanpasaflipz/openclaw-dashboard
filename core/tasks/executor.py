"""
core.tasks.executor — Dispatch and execute approved agent actions.

Maps (action_type, service_type) pairs to adapter functions.
Each handler receives (user_id, action_data_dict) and returns
(result_dict | None, error_string | None).
"""
from __future__ import annotations

import json
from typing import Any, Callable

from adapters.gmail import send_email
from adapters.calendar import create_event, update_event, delete_event
from adapters.drive import create_folder, upload_file
from adapters.binance import execute_trade

# Type alias for executor handlers
Handler = Callable[[int, dict[str, Any]], tuple[dict | None, str | None]]

# Registry: (action_type, service_type) -> handler
_HANDLERS: dict[tuple[str, str], Handler] = {
    ('send_email', 'gmail'): send_email,
    ('place_order', 'binance'): execute_trade,
    ('create_event', 'calendar'): create_event,
    ('update_event', 'calendar'): update_event,
    ('delete_event', 'calendar'): delete_event,
    ('create_folder', 'drive'): create_folder,
    ('upload_file', 'drive'): upload_file,
}


def get_handler(action_type: str, service_type: str) -> Handler | None:
    """Look up the executor for a given action/service pair."""
    return _HANDLERS.get((action_type, service_type))


def execute_action(user_id: int, action_type: str, service_type: str,
                   action_data_json: str) -> tuple[dict | None, str | None]:
    """Parse action_data JSON and dispatch to the right adapter.

    Returns:
        (result_dict, None) on success, or (None, error_message) on failure.
    """
    handler = get_handler(action_type, service_type)
    if handler is None:
        return None, f'No executor for ({action_type}, {service_type})'

    action_data = json.loads(action_data_json)
    return handler(user_id, action_data)
