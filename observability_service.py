"""
Observability service — BACKWARD-COMPATIBLE SHIM.

All logic has been extracted to core/observability/ package.
This file re-exports the public API so existing imports continue working:
    from observability_service import emit_event, calculate_cost, ...
"""

# Re-export everything from the new package
from core.observability.ingestion import emit_event, emit_event_batch, _commit_one_by_one
from core.observability.run_tracker import start_run, finish_run
from core.observability.cost_engine import (
    calculate_cost as _calculate_cost_decimal,
    _load_pricing,
    _pricing_cache,
    _pricing_cache_ts,
)
from core.observability.metrics import aggregate_daily, _percentile
from core.observability.alert_engine import evaluate_alerts
from core.observability.constants import (
    VALID_EVENT_TYPES,
    EVENT_STATUS_VALUES,
    PRICING_CACHE_TTL,
)


def calculate_cost(provider, model, tokens_in, tokens_out):
    """Backward-compatible wrapper: returns float (original contract)."""
    return float(_calculate_cost_decimal(provider, model, tokens_in, tokens_out))
