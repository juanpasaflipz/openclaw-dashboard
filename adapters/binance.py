"""
adapters.binance — Binance trade execution.
"""
from __future__ import annotations

from typing import Any


def execute_trade(user_id: int, action_data: dict[str, Any]) -> tuple[dict | None, str | None]:
    """Place a trade order via Binance.

    Checks that trading is enabled before executing.

    Returns:
        (result_dict, None) on success or (None, error_message) on failure.
    """
    from binance_service import place_order, is_trading_enabled

    if not is_trading_enabled(user_id):
        return None, 'Trading is not enabled'

    result, error = place_order(
        user_id=user_id,
        symbol=action_data['symbol'],
        side=action_data['side'],
        order_type=action_data['order_type'],
        amount=action_data['amount'],
        price=action_data.get('price'),
    )

    if error:
        return None, error

    return result, None
