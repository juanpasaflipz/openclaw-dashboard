"""
Observability constants — event types, status values, configuration.
"""

# Stable contract: all valid event types accepted by the ingestion layer.
VALID_EVENT_TYPES = frozenset({
    'run_started', 'run_finished',
    'action_started', 'action_finished',
    'tool_call', 'tool_result',
    'llm_call',
    'error', 'metric', 'heartbeat',
})

EVENT_STATUS_VALUES = frozenset({'success', 'error', 'info'})

# Pricing cache TTL in seconds (applies to in-memory cache only).
PRICING_CACHE_TTL = 300  # 5 minutes

# Alert evaluation defaults
DEFAULT_ALERT_WINDOW_MINUTES = 60
DEFAULT_ALERT_COOLDOWN_MINUTES = 360

# Ingestion limits
MAX_BATCH_SIZE = 1000

# Health score weights (out of 100)
HEALTH_WEIGHT_SUCCESS_RATE = 40
HEALTH_WEIGHT_LATENCY = 25
HEALTH_WEIGHT_ERROR_BURST = 20
HEALTH_WEIGHT_COST_ANOMALY = 15

# Health score thresholds
HEALTH_LATENCY_GOOD_MS = 2000
HEALTH_LATENCY_BAD_MS = 10000
HEALTH_ERROR_BURST_WINDOW_MINUTES = 30
HEALTH_ERROR_BURST_THRESHOLD = 5
HEALTH_COST_ANOMALY_STDDEV_MULTIPLIER = 2.0
