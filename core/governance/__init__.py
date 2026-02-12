"""
core.governance — Human-Approved Policy Delegation System.

Extends the risk engine with agent-initiated policy change requests,
human approval gates, time-bound delegation grants, and immutable
workspace boundaries. All state transitions are audited.

Public API:
    create_request, get_requests, get_request  — policy change requests
    expire_stale_requests                       — request lifecycle
    approve_request, deny_request               — human approval gate
    validate_against_boundaries                 — boundary checks
    get_active_grants, apply_delegated_change   — delegation enforcement
    expire_grants, revoke_grant                 — delegation lifecycle
    log_governance_event, get_governance_trail  — audit trail
    rollback_change                             — policy rollback
"""

from core.governance.requests import (
    create_request,
    get_requests,
    get_request,
    expire_stale_requests,
)
from core.governance.approvals import (
    approve_request,
    deny_request,
)
from core.governance.boundaries import (
    validate_against_boundaries,
    get_workspace_boundaries,
)
from core.governance.delegation import (
    get_active_grants,
    apply_delegated_change,
    expire_grants,
    revoke_grant,
)
from core.governance.governance_audit import (
    log_governance_event,
    get_governance_trail,
)
from core.governance.rollback import (
    rollback_change,
)

__all__ = [
    'create_request',
    'get_requests',
    'get_request',
    'expire_stale_requests',
    'approve_request',
    'deny_request',
    'validate_against_boundaries',
    'get_workspace_boundaries',
    'get_active_grants',
    'apply_delegated_change',
    'expire_grants',
    'revoke_grant',
    'log_governance_event',
    'get_governance_trail',
    'rollback_change',
]
