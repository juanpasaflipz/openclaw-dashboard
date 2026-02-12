"""
core.observability — AI Agent Observability & Governance subsystem.

Public API:
    emit_event, emit_event_batch       — ingestion
    start_run, finish_run              — run lifecycle
    calculate_cost, calculate_cost_float — cost calculation
    aggregate_daily                    — daily metrics rollup
    evaluate_alerts                    — alert rule evaluation
    compute_agent_health, compute_all_health_scores — health scoring
    VALID_EVENT_TYPES, EVENT_STATUS_VALUES — constants
    get_workspace_tier, invalidate_tier_cache, verify_workspace_limits — tier enforcement
"""

from core.observability.ingestion import emit_event, emit_event_batch
from core.observability.run_tracker import start_run, finish_run
from core.observability.cost_engine import calculate_cost, calculate_cost_float, invalidate_pricing_cache
from core.observability.metrics import aggregate_daily
from core.observability.alert_engine import evaluate_alerts
from core.observability.health_score import compute_agent_health, compute_all_health_scores
from core.observability.constants import VALID_EVENT_TYPES, EVENT_STATUS_VALUES
from core.observability.workspace import (
    get_workspace_id, scope_query, verify_agent_ownership, verify_api_key_ownership,
)
from core.observability.notifications import dispatch_alert_notification, notify_slack
from core.observability.tier_enforcement import (
    get_workspace_tier, invalidate_tier_cache, verify_workspace_limits,
    check_agent_limit, check_agent_allowed, check_alert_rule_limit,
    check_api_key_limit, check_anomaly_detection, check_slack_notifications,
    get_retention_cutoff, clamp_date_range, get_health_history_cutoff,
    get_max_batch_size,
)
from core.observability.retention import cleanup_expired_events, get_retention_stats

__all__ = [
    'emit_event', 'emit_event_batch',
    'start_run', 'finish_run',
    'calculate_cost', 'calculate_cost_float', 'invalidate_pricing_cache',
    'aggregate_daily',
    'evaluate_alerts',
    'compute_agent_health', 'compute_all_health_scores',
    'VALID_EVENT_TYPES', 'EVENT_STATUS_VALUES',
    'get_workspace_id', 'scope_query', 'verify_agent_ownership', 'verify_api_key_ownership',
    'dispatch_alert_notification', 'notify_slack',
    # Tier enforcement
    'get_workspace_tier', 'invalidate_tier_cache', 'verify_workspace_limits',
    'check_agent_limit', 'check_agent_allowed', 'check_alert_rule_limit',
    'check_api_key_limit', 'check_anomaly_detection', 'check_slack_notifications',
    'get_retention_cutoff', 'clamp_date_range', 'get_health_history_cutoff',
    'get_max_batch_size',
    # Retention cleanup
    'cleanup_expired_events', 'get_retention_stats',
]
