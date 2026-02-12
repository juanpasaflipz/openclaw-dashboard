"""
core.risk_engine — Risk Policy & Intervention Engine.

Evaluates configurable risk policies against observability metrics and
executes automated interventions (pause, downgrade, throttle) asynchronously.

Public API:
    get_active_policies, get_policy   — policy queries
    evaluate_policies                  — breach detection
    execute_pending_events             — intervention execution
    run_enforcement_cycle              — full async worker cycle
    run_evaluation_only, run_execution_only — granular triggers
    log_intervention, get_audit_trail  — audit log
"""

from core.risk_engine.policy import (
    get_active_policies,
    get_policy,
    VALID_POLICY_TYPES,
    VALID_ACTION_TYPES,
)
from core.risk_engine.evaluator import evaluate_policies
from core.risk_engine.interventions import execute_pending_events
from core.risk_engine.audit_log import log_intervention, get_audit_trail
from core.risk_engine.enforcement_worker import (
    run_enforcement_cycle,
    run_evaluation_only,
    run_execution_only,
)

__all__ = [
    'get_active_policies',
    'get_policy',
    'VALID_POLICY_TYPES',
    'VALID_ACTION_TYPES',
    'evaluate_policies',
    'execute_pending_events',
    'log_intervention',
    'get_audit_trail',
    'run_enforcement_cycle',
    'run_evaluation_only',
    'run_execution_only',
]
