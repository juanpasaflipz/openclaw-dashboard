"""
Tests for the Human-Approved Policy Delegation System — Phase 1.

Covers: models (schema/CRUD), request creation, workspace isolation,
agent ownership, cooldown, listing/filtering, expiration, audit logging.
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from models import (
    db, User, Agent, RiskPolicy, WorkspaceTier,
    PolicyChangeRequest, DelegationGrant, GovernanceAuditLog,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def risk_policy(app, user, agent):
    """Create a daily_spend_cap policy for the test agent."""
    policy = RiskPolicy(
        workspace_id=user.id,
        agent_id=agent.id,
        policy_type='daily_spend_cap',
        threshold_value=Decimal('10.0000'),
        action_type='pause_agent',
        cooldown_minutes=360,
        is_enabled=True,
    )
    db.session.add(policy)
    db.session.commit()
    return policy


@pytest.fixture
def other_user(app):
    """Create a second user for workspace isolation tests."""
    u = User(
        email='other@example.com',
        created_at=datetime.utcnow(),
        credit_balance=10,
        subscription_tier='free',
        subscription_status='inactive',
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def other_agent(app, other_user):
    """Create an agent belonging to other_user."""
    a = Agent(
        user_id=other_user.id,
        name='OtherAgent',
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(a)
    db.session.commit()
    return a


# ---------------------------------------------------------------------------
# PolicyChangeRequest Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPolicyChangeRequestModel:

    def test_create_request(self, app, user, agent, risk_policy):
        pcr = PolicyChangeRequest(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '10.0000',
                'requested_value': '15.0000',
            },
            reason='Need higher spend cap for campaign',
            status='pending',
            requested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            policy_snapshot=risk_policy.to_dict(),
        )
        db.session.add(pcr)
        db.session.commit()

        assert pcr.id is not None
        assert pcr.workspace_id == user.id
        assert pcr.agent_id == agent.id
        assert pcr.policy_id == risk_policy.id
        assert pcr.status == 'pending'
        assert pcr.reviewed_by is None
        assert pcr.reviewed_at is None
        assert pcr.expires_at is not None
        assert pcr.policy_snapshot is not None

    def test_to_dict(self, app, user, agent, risk_policy):
        pcr = PolicyChangeRequest(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'field': 'threshold_value'},
            reason='test',
            status='pending',
            requested_at=datetime.utcnow(),
        )
        db.session.add(pcr)
        db.session.commit()

        d = pcr.to_dict()
        assert d['id'] == pcr.id
        assert d['workspace_id'] == user.id
        assert d['status'] == 'pending'
        assert 'requested_at' in d
        assert 'reviewed_by' in d

    def test_valid_statuses(self, app):
        assert 'pending' in PolicyChangeRequest.VALID_STATUSES
        assert 'approved' in PolicyChangeRequest.VALID_STATUSES
        assert 'denied' in PolicyChangeRequest.VALID_STATUSES
        assert 'expired' in PolicyChangeRequest.VALID_STATUSES
        assert 'applied' in PolicyChangeRequest.VALID_STATUSES

    def test_relationships(self, app, user, agent, risk_policy):
        pcr = PolicyChangeRequest(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'field': 'threshold_value'},
            reason='test',
            status='pending',
            requested_at=datetime.utcnow(),
        )
        db.session.add(pcr)
        db.session.commit()

        assert pcr.workspace.id == user.id
        assert pcr.agent.id == agent.id
        assert pcr.policy.id == risk_policy.id


# ---------------------------------------------------------------------------
# DelegationGrant Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestDelegationGrantModel:

    def test_create_grant(self, app, user, agent):
        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id,
            agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={'policy_id': 1, 'fields': {}},
            duration_minutes=120,
            valid_from=now,
            valid_to=now + timedelta(minutes=120),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        assert grant.id is not None
        assert grant.active is True
        assert grant.revoked_at is None

    def test_to_dict(self, app, user, agent):
        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id,
            agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={},
            max_spend_delta=Decimal('5.0000'),
            duration_minutes=60,
            valid_from=now,
            valid_to=now + timedelta(minutes=60),
        )
        db.session.add(grant)
        db.session.commit()

        d = grant.to_dict()
        assert d['max_spend_delta'] == '5.0000'
        assert d['duration_minutes'] == 60
        assert d['active'] is True


# ---------------------------------------------------------------------------
# GovernanceAuditLog Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestGovernanceAuditLogModel:

    def test_create_log_entry(self, app, user, agent):
        entry = GovernanceAuditLog(
            workspace_id=user.id,
            agent_id=agent.id,
            actor_id=user.id,
            event_type='request_submitted',
            details={'request_id': 1, 'reason': 'test'},
        )
        db.session.add(entry)
        db.session.commit()

        assert entry.id is not None
        assert entry.event_type == 'request_submitted'
        assert entry.created_at is not None

    def test_to_dict(self, app, user):
        entry = GovernanceAuditLog(
            workspace_id=user.id,
            event_type='request_expired',
            details={'request_id': 1},
        )
        db.session.add(entry)
        db.session.commit()

        d = entry.to_dict()
        assert d['event_type'] == 'request_expired'
        assert d['agent_id'] is None
        assert d['actor_id'] is None


# ---------------------------------------------------------------------------
# Governance Module Exports
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestGovernanceModuleExports:

    def test_module_imports(self, app):
        from core.governance import (
            create_request, get_requests, get_request,
            expire_stale_requests,
            log_governance_event, get_governance_trail,
        )
        assert callable(create_request)
        assert callable(get_requests)
        assert callable(get_request)
        assert callable(expire_stale_requests)
        assert callable(log_governance_event)
        assert callable(get_governance_trail)


# ---------------------------------------------------------------------------
# Request Creation Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestCreateRequest:

    def test_successful_request(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='Need higher cap',
        )

        assert error is None
        assert pcr is not None
        assert pcr.status == 'pending'
        assert pcr.workspace_id == user.id
        assert pcr.agent_id == agent.id
        assert pcr.policy_id == risk_policy.id
        assert pcr.policy_snapshot is not None
        assert pcr.expires_at is not None

    def test_auto_fills_current_value(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        assert pcr.requested_changes['current_value'] == '10.0000'

    def test_preserves_provided_current_value(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '10.0000',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        assert pcr.requested_changes['current_value'] == '10.0000'

    def test_agent_not_in_workspace(self, app, user, agent, risk_policy,
                                    other_user, other_agent):
        from core.governance.requests import create_request

        # other_agent belongs to other_user, not user
        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=other_agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        assert pcr is None
        assert 'does not belong to workspace' in error

    def test_policy_not_in_workspace(self, app, user, agent, risk_policy,
                                     other_user, other_agent):
        from core.governance.requests import create_request

        # Create a policy in other_user's workspace
        other_policy = RiskPolicy(
            workspace_id=other_user.id,
            agent_id=other_agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('20.0000'),
            action_type='alert_only',
        )
        db.session.add(other_policy)
        db.session.commit()

        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': other_policy.id,
                'field': 'threshold_value',
                'requested_value': '25.0000',
            },
            reason='test',
        )

        assert pcr is None
        assert 'Policy not found' in error

    def test_immutable_field_rejected(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'policy_type',
                'requested_value': 'error_rate_cap',
            },
            reason='test',
        )

        assert pcr is None
        assert 'not mutable' in error

    def test_workspace_id_field_rejected(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'workspace_id',
                'requested_value': '999',
            },
            reason='test',
        )

        assert pcr is None
        assert 'not mutable' in error

    def test_missing_policy_id(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        assert pcr is None
        assert 'policy_id is required' in error

    def test_invalid_requested_changes_type(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes='not a dict',
            reason='test',
        )

        assert pcr is None
        assert 'must be a dict' in error

    def test_creates_audit_entry(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='audit test',
        )

        entries = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id,
            event_type='request_submitted',
        ).all()
        assert len(entries) == 1
        assert entries[0].agent_id == agent.id
        assert entries[0].details['reason'] == 'audit test'

    def test_no_immediate_policy_mutation(self, app, user, agent, risk_policy):
        """Critical: submitting a request must NOT change the policy."""
        from core.governance.requests import create_request

        original_threshold = risk_policy.threshold_value

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '99.0000',
            },
            reason='test',
        )

        # Refresh from DB
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == original_threshold


# ---------------------------------------------------------------------------
# Request Cooldown Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestRequestCooldown:

    def test_cooldown_blocks_rapid_requests(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        # First request succeeds
        pcr1, err1 = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='first',
        )
        assert err1 is None

        # Second request within cooldown fails
        pcr2, err2 = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '20.0000',
            },
            reason='second',
        )
        assert pcr2 is None
        assert 'less than' in err2

    def test_cooldown_allows_different_policies(self, app, user, agent, risk_policy):
        """Cooldown is per-policy, not per-workspace."""
        from core.governance.requests import create_request

        # Create a second policy
        policy2 = RiskPolicy(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_type='error_rate_cap',
            threshold_value=Decimal('5.0000'),
            action_type='alert_only',
        )
        db.session.add(policy2)
        db.session.commit()

        # Request for policy 1
        _, err1 = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='first policy',
        )
        assert err1 is None

        # Request for policy 2 should succeed despite cooldown on policy 1
        _, err2 = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': policy2.id,
                'field': 'threshold_value',
                'requested_value': '10.0000',
            },
            reason='second policy',
        )
        assert err2 is None

    def test_cooldown_allows_after_expiry(self, app, user, agent, risk_policy):
        """Requests allowed after cooldown period passes."""
        from core.governance.requests import create_request, REQUEST_COOLDOWN_MINUTES

        # Create a request with a past timestamp
        old_request = PolicyChangeRequest(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='old',
            status='pending',
            requested_at=datetime.utcnow() - timedelta(
                minutes=REQUEST_COOLDOWN_MINUTES + 1
            ),
        )
        db.session.add(old_request)
        db.session.commit()

        # New request should succeed
        pcr, err = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '20.0000',
            },
            reason='new',
        )
        assert err is None
        assert pcr is not None


# ---------------------------------------------------------------------------
# Request Listing / Filtering Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestGetRequests:

    def test_list_all_for_workspace(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request, get_requests

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        results = get_requests(workspace_id=user.id)
        assert len(results) == 1
        assert results[0].workspace_id == user.id

    def test_filter_by_status(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request, get_requests

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        pending = get_requests(workspace_id=user.id, status='pending')
        assert len(pending) == 1

        denied = get_requests(workspace_id=user.id, status='denied')
        assert len(denied) == 0

    def test_filter_by_agent(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request, get_requests

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        results = get_requests(workspace_id=user.id, agent_id=agent.id)
        assert len(results) == 1

        results = get_requests(workspace_id=user.id, agent_id=9999)
        assert len(results) == 0

    def test_workspace_isolation(self, app, user, agent, risk_policy,
                                 other_user, other_agent):
        from core.governance.requests import create_request, get_requests

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        # other_user should see nothing
        results = get_requests(workspace_id=other_user.id)
        assert len(results) == 0

    def test_get_single_request(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request, get_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        found = get_request(pcr.id, workspace_id=user.id)
        assert found is not None
        assert found.id == pcr.id

    def test_get_request_wrong_workspace(self, app, user, agent, risk_policy,
                                         other_user):
        from core.governance.requests import create_request, get_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='test',
        )

        found = get_request(pcr.id, workspace_id=other_user.id)
        assert found is None

    def test_ordered_by_requested_at_desc(self, app, user, agent, risk_policy):
        from core.governance.requests import get_requests

        old = PolicyChangeRequest(
            workspace_id=user.id, agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'policy_id': risk_policy.id, 'field': 'threshold_value',
                               'requested_value': '15'},
            reason='old', status='pending',
            requested_at=datetime.utcnow() - timedelta(hours=2),
        )
        new = PolicyChangeRequest(
            workspace_id=user.id, agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'policy_id': risk_policy.id, 'field': 'threshold_value',
                               'requested_value': '20'},
            reason='new', status='denied',
            requested_at=datetime.utcnow(),
        )
        db.session.add_all([old, new])
        db.session.commit()

        results = get_requests(workspace_id=user.id)
        assert len(results) == 2
        assert results[0].reason == 'new'
        assert results[1].reason == 'old'


# ---------------------------------------------------------------------------
# Request Expiration Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestExpireStaleRequests:

    def test_expires_old_requests(self, app, user, agent, risk_policy):
        from core.governance.requests import expire_stale_requests

        old = PolicyChangeRequest(
            workspace_id=user.id, agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'policy_id': risk_policy.id, 'field': 'threshold_value',
                               'requested_value': '15'},
            reason='old', status='pending',
            requested_at=datetime.utcnow() - timedelta(hours=25),
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.session.add(old)
        db.session.commit()

        count = expire_stale_requests()
        assert count == 1

        db.session.refresh(old)
        assert old.status == 'expired'

    def test_does_not_expire_recent(self, app, user, agent, risk_policy):
        from core.governance.requests import expire_stale_requests

        fresh = PolicyChangeRequest(
            workspace_id=user.id, agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'policy_id': risk_policy.id, 'field': 'threshold_value',
                               'requested_value': '15'},
            reason='fresh', status='pending',
            requested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=23),
        )
        db.session.add(fresh)
        db.session.commit()

        count = expire_stale_requests()
        assert count == 0

        db.session.refresh(fresh)
        assert fresh.status == 'pending'

    def test_does_not_expire_non_pending(self, app, user, agent, risk_policy):
        from core.governance.requests import expire_stale_requests

        denied = PolicyChangeRequest(
            workspace_id=user.id, agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'policy_id': risk_policy.id, 'field': 'threshold_value',
                               'requested_value': '15'},
            reason='denied', status='denied',
            requested_at=datetime.utcnow() - timedelta(hours=48),
            expires_at=datetime.utcnow() - timedelta(hours=24),
        )
        db.session.add(denied)
        db.session.commit()

        count = expire_stale_requests()
        assert count == 0

    def test_fallback_expiry_without_expires_at(self, app, user, agent, risk_policy):
        from core.governance.requests import expire_stale_requests

        no_expiry = PolicyChangeRequest(
            workspace_id=user.id, agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'policy_id': risk_policy.id, 'field': 'threshold_value',
                               'requested_value': '15'},
            reason='no expiry', status='pending',
            requested_at=datetime.utcnow() - timedelta(hours=25),
            expires_at=None,
        )
        db.session.add(no_expiry)
        db.session.commit()

        count = expire_stale_requests()
        assert count == 1

    def test_expiration_creates_audit_entry(self, app, user, agent, risk_policy):
        from core.governance.requests import expire_stale_requests

        old = PolicyChangeRequest(
            workspace_id=user.id, agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={'policy_id': risk_policy.id, 'field': 'threshold_value',
                               'requested_value': '15'},
            reason='old', status='pending',
            requested_at=datetime.utcnow() - timedelta(hours=25),
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.session.add(old)
        db.session.commit()

        expire_stale_requests()

        entries = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id,
            event_type='request_expired',
        ).all()
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# Governance Audit Log Helper Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestGovernanceAuditHelpers:

    def test_log_event(self, app, user, agent):
        from core.governance.governance_audit import log_governance_event

        entry = log_governance_event(
            workspace_id=user.id,
            event_type='request_submitted',
            details={'request_id': 1, 'reason': 'test'},
            agent_id=agent.id,
            actor_id=None,
        )
        db.session.commit()

        assert entry.id is not None
        assert entry.event_type == 'request_submitted'
        assert entry.workspace_id == user.id

    def test_get_trail_by_workspace(self, app, user, agent, other_user):
        from core.governance.governance_audit import (
            log_governance_event, get_governance_trail,
        )

        log_governance_event(
            workspace_id=user.id,
            event_type='request_submitted',
            details={'test': True},
            agent_id=agent.id,
        )
        db.session.commit()

        trail = get_governance_trail(workspace_id=user.id)
        assert len(trail) == 1

        other_trail = get_governance_trail(workspace_id=other_user.id)
        assert len(other_trail) == 0

    def test_get_trail_by_event_type(self, app, user, agent):
        from core.governance.governance_audit import (
            log_governance_event, get_governance_trail,
        )

        log_governance_event(
            workspace_id=user.id,
            event_type='request_submitted',
            details={'test': True},
            agent_id=agent.id,
        )
        log_governance_event(
            workspace_id=user.id,
            event_type='request_expired',
            details={'test': True},
        )
        db.session.commit()

        submitted = get_governance_trail(
            workspace_id=user.id, event_type='request_submitted',
        )
        assert len(submitted) == 1

        expired = get_governance_trail(
            workspace_id=user.id, event_type='request_expired',
        )
        assert len(expired) == 1

    def test_get_trail_by_agent(self, app, user, agent):
        from core.governance.governance_audit import (
            log_governance_event, get_governance_trail,
        )

        log_governance_event(
            workspace_id=user.id,
            event_type='request_submitted',
            details={'test': True},
            agent_id=agent.id,
        )
        log_governance_event(
            workspace_id=user.id,
            event_type='request_submitted',
            details={'test': True},
            agent_id=None,
        )
        db.session.commit()

        by_agent = get_governance_trail(
            workspace_id=user.id, agent_id=agent.id,
        )
        assert len(by_agent) == 1

    def test_trail_ordered_desc(self, app, user):
        from core.governance.governance_audit import (
            log_governance_event, get_governance_trail,
        )

        e1 = GovernanceAuditLog(
            workspace_id=user.id, event_type='first',
            details={}, created_at=datetime.utcnow() - timedelta(hours=2),
        )
        e2 = GovernanceAuditLog(
            workspace_id=user.id, event_type='second',
            details={}, created_at=datetime.utcnow(),
        )
        db.session.add_all([e1, e2])
        db.session.commit()

        trail = get_governance_trail(workspace_id=user.id)
        assert trail[0].event_type == 'second'
        assert trail[1].event_type == 'first'

    def test_trail_limit(self, app, user):
        from core.governance.governance_audit import (
            log_governance_event, get_governance_trail,
        )

        for i in range(5):
            log_governance_event(
                workspace_id=user.id,
                event_type='test',
                details={'i': i},
            )
        db.session.commit()

        trail = get_governance_trail(workspace_id=user.id, limit=3)
        assert len(trail) == 3


# ---------------------------------------------------------------------------
# Route Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestGovernanceSubmitRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.post('/api/governance/request', json={
            'agent_id': 1,
            'requested_changes': {},
            'reason': 'test',
        })
        assert resp.status_code == 401

    def test_missing_body(self, app, user, agent, risk_policy):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/request',
                           content_type='application/json')
        assert resp.status_code == 400

    def test_missing_agent_id(self, app, user, agent, risk_policy):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/request', json={
            'requested_changes': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15',
            },
            'reason': 'test',
        })
        assert resp.status_code == 400
        assert 'agent_id' in resp.get_json()['error']

    def test_missing_reason(self, app, user, agent, risk_policy):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/request', json={
            'agent_id': agent.id,
            'requested_changes': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15',
            },
            'reason': '',
        })
        assert resp.status_code == 400

    def test_successful_submit(self, app, user, agent, risk_policy):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/request', json={
            'agent_id': agent.id,
            'requested_changes': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            'reason': 'Higher cap needed',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['request']['status'] == 'pending'
        assert data['request']['policy_id'] == risk_policy.id

    def test_validation_error_returns_400(self, app, user, agent, risk_policy):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/request', json={
            'agent_id': agent.id,
            'requested_changes': {
                'policy_id': risk_policy.id,
                'field': 'policy_type',
                'requested_value': 'error_rate_cap',
            },
            'reason': 'test',
        })
        assert resp.status_code == 400
        assert 'not mutable' in resp.get_json()['error']


@pytest.mark.governance
class TestGovernanceListRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.get('/api/governance/requests')
        assert resp.status_code == 401

    def test_list_empty(self, app, user):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/requests')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['requests'] == []
        assert data['count'] == 0

    def test_list_with_results(self, app, user, agent, risk_policy):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        # Submit a request
        client.post('/api/governance/request', json={
            'agent_id': agent.id,
            'requested_changes': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            'reason': 'test',
        })

        resp = client.get('/api/governance/requests')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1
        assert data['requests'][0]['status'] == 'pending'

    def test_filter_by_status(self, app, user, agent, risk_policy):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        client.post('/api/governance/request', json={
            'agent_id': agent.id,
            'requested_changes': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            'reason': 'test',
        })

        resp = client.get('/api/governance/requests?status=pending')
        assert resp.get_json()['count'] == 1

        resp = client.get('/api/governance/requests?status=denied')
        assert resp.get_json()['count'] == 0

    def test_workspace_isolation(self, app, user, agent, risk_policy,
                                 other_user):
        client = app.test_client()

        # Submit as user
        with client.session_transaction() as sess:
            sess['user_id'] = user.id
        client.post('/api/governance/request', json={
            'agent_id': agent.id,
            'requested_changes': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            'reason': 'test',
        })

        # List as other_user should return empty
        with client.session_transaction() as sess:
            sess['user_id'] = other_user.id
        resp = client.get('/api/governance/requests')
        assert resp.get_json()['count'] == 0


# ---------------------------------------------------------------------------
# Safety: No Silent Mutation
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestSafetyNoSilentMutation:

    def test_request_does_not_mutate_policy_via_module(self, app, user, agent,
                                                       risk_policy):
        """The governance request module never writes to risk_policies."""
        from core.governance.requests import create_request

        original = risk_policy.to_dict()

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '999.0000',
            },
            reason='large change',
        )

        db.session.refresh(risk_policy)
        assert risk_policy.to_dict() == original

    def test_request_does_not_mutate_policy_via_route(self, app, user, agent,
                                                      risk_policy):
        """The governance route never writes to risk_policies."""
        original = risk_policy.to_dict()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        client.post('/api/governance/request', json={
            'agent_id': agent.id,
            'requested_changes': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '999.0000',
            },
            'reason': 'large change via route',
        })

        db.session.refresh(risk_policy)
        assert risk_policy.to_dict() == original

    def test_policy_snapshot_captured(self, app, user, agent, risk_policy):
        """Request stores a snapshot of the policy at submission time."""
        from core.governance.requests import create_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='snapshot test',
        )

        assert pcr.policy_snapshot is not None
        assert pcr.policy_snapshot['threshold_value'] == '10.0000'
        assert pcr.policy_snapshot['action_type'] == 'pause_agent'


# ---------------------------------------------------------------------------
# Backwards Compatibility: Existing Risk Engine Tests Unaffected
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestBackwardsCompatibility:

    def test_risk_policy_model_unchanged(self, app, user, agent):
        """RiskPolicy model works exactly as before."""
        policy = RiskPolicy(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'),
            action_type='pause_agent',
        )
        db.session.add(policy)
        db.session.commit()

        assert policy.id is not None
        assert policy.to_dict()['threshold_value'] == '10.0000'

    def test_risk_engine_imports_still_work(self, app):
        """core.risk_engine public API is unchanged."""
        from core.risk_engine import (
            get_active_policies, get_policy,
            VALID_POLICY_TYPES, VALID_ACTION_TYPES,
            evaluate_policies, execute_pending_events,
            log_intervention, get_audit_trail,
            run_enforcement_cycle, run_evaluation_only, run_execution_only,
        )
        assert callable(evaluate_policies)
        assert callable(execute_pending_events)

    def test_governance_does_not_import_risk_engine_internals(self, app):
        """Governance module does not import risk engine internals."""
        import core.governance.requests as req_mod
        import core.governance.governance_audit as audit_mod

        # These modules should not import evaluator/interventions
        for mod in [req_mod, audit_mod]:
            source = open(mod.__file__).read()
            assert 'from core.risk_engine.evaluator' not in source
            assert 'from core.risk_engine.interventions' not in source


# ===================================================================
# PHASE 2 — Human Approval Flow
# ===================================================================

# ---------------------------------------------------------------------------
# Fixtures for Phase 2
# ---------------------------------------------------------------------------

@pytest.fixture
def pending_request(app, user, agent, risk_policy):
    """Create a pending policy change request."""
    from core.governance.requests import create_request

    pcr, _ = create_request(
        workspace_id=user.id,
        agent_id=agent.id,
        requested_changes={
            'policy_id': risk_policy.id,
            'field': 'threshold_value',
            'current_value': '10.0000',
            'requested_value': '15.0000',
        },
        reason='Need higher cap for campaign',
    )
    return pcr


# ---------------------------------------------------------------------------
# Boundary Validation Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestBoundaryValidation:

    def test_threshold_within_boundary(self, app, user, agent, risk_policy):
        from core.governance.boundaries import validate_against_boundaries

        # Free tier cap is $50 — requesting $15 should pass
        valid, error = validate_against_boundaries(
            user.id, risk_policy.id, 'threshold_value', '15.0000',
        )
        assert valid is True
        assert error is None

    def test_threshold_exceeds_boundary(self, app, user, agent, risk_policy):
        from core.governance.boundaries import validate_against_boundaries

        # Free tier cap is $50 — requesting $100 should fail
        valid, error = validate_against_boundaries(
            user.id, risk_policy.id, 'threshold_value', '100.0000',
        )
        assert valid is False
        assert 'exceeds workspace boundary' in error
        assert 'free' in error

    def test_negative_threshold_rejected(self, app, user, agent, risk_policy):
        from core.governance.boundaries import validate_against_boundaries

        valid, error = validate_against_boundaries(
            user.id, risk_policy.id, 'threshold_value', '-5.0000',
        )
        assert valid is False
        assert 'negative' in error

    def test_cooldown_above_minimum(self, app, user, agent, risk_policy):
        from core.governance.boundaries import validate_against_boundaries

        valid, error = validate_against_boundaries(
            user.id, risk_policy.id, 'cooldown_minutes', '60',
        )
        assert valid is True

    def test_cooldown_below_minimum(self, app, user, agent, risk_policy):
        from core.governance.boundaries import validate_against_boundaries

        valid, error = validate_against_boundaries(
            user.id, risk_policy.id, 'cooldown_minutes', '10',
        )
        assert valid is False
        assert 'below minimum' in error

    def test_action_type_escalation_allowed(self, app, user, agent):
        """Can escalate from alert_only to pause_agent."""
        from core.governance.boundaries import validate_against_boundaries

        policy = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='daily_spend_cap',
            threshold_value=Decimal('10.0000'),
            action_type='alert_only',
        )
        db.session.add(policy)
        db.session.commit()

        valid, error = validate_against_boundaries(
            user.id, policy.id, 'action_type', 'pause_agent',
        )
        assert valid is True

    def test_action_type_deescalation_blocked(self, app, user, agent, risk_policy):
        """Cannot de-escalate from pause_agent to alert_only."""
        from core.governance.boundaries import validate_against_boundaries

        # risk_policy has action_type='pause_agent'
        valid, error = validate_against_boundaries(
            user.id, risk_policy.id, 'action_type', 'alert_only',
        )
        assert valid is False
        assert 'Cannot de-escalate' in error

    def test_get_workspace_boundaries(self, app, user):
        from core.governance.boundaries import get_workspace_boundaries

        bounds = get_workspace_boundaries(user.id)
        assert 'max_daily_spend_cap' in bounds
        assert 'min_cooldown_minutes' in bounds
        assert bounds['tier_name'] == 'free'
        assert bounds['max_daily_spend_cap'] == Decimal('50.00')


# ---------------------------------------------------------------------------
# Approve One-Time Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestApproveOneTime:

    def test_approve_mutates_policy(self, app, user, agent, risk_policy,
                                    pending_request):
        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        assert error is None
        assert result['status'] == 'applied'
        assert result['mode'] == 'one_time'
        assert result['old_value'] == '10.0000'
        assert result['new_value'] == '15.0000'

        # Policy actually changed
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('15.0000')

    def test_approve_updates_request_status(self, app, user, agent,
                                             risk_policy, pending_request):
        from core.governance.approvals import approve_request

        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        db.session.refresh(pending_request)
        assert pending_request.status == 'applied'
        assert pending_request.reviewed_by == user.id
        assert pending_request.reviewed_at is not None

    def test_approve_creates_audit_entries(self, app, user, agent,
                                           risk_policy, pending_request):
        from core.governance.approvals import approve_request

        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        approved = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id,
            event_type='request_approved',
        ).all()
        assert len(approved) == 1
        assert approved[0].details['mode'] == 'one_time'

        applied = GovernanceAuditLog.query.filter_by(
            workspace_id=user.id,
            event_type='change_applied',
        ).all()
        assert len(applied) == 1
        assert applied[0].details['policy_before'] is not None
        assert applied[0].details['policy_after'] is not None

    def test_approve_boundary_violation_rejected(self, app, user, agent,
                                                  risk_policy):
        """Approval blocked if change exceeds workspace boundary."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request

        # Request value exceeding free tier ($50 cap)
        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '100.0000',
            },
            reason='want more',
        )

        result, error = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        assert result is None
        assert 'Boundary violation' in error

        # Policy unchanged
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

        # Boundary violation logged
        violations = GovernanceAuditLog.query.filter_by(
            event_type='boundary_violation',
        ).all()
        assert len(violations) == 1

    def test_approve_cooldown_change(self, app, user, agent, risk_policy):
        """Approve a cooldown_minutes change."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'cooldown_minutes',
                'requested_value': '120',
            },
            reason='shorter cooldown',
        )

        result, error = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        assert error is None
        db.session.refresh(risk_policy)
        assert risk_policy.cooldown_minutes == 120


# ---------------------------------------------------------------------------
# Approve Delegate Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestApproveDelegate:

    def test_delegate_creates_grant(self, app, user, agent, risk_policy,
                                     pending_request):
        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 120},
        )

        assert error is None
        assert result['mode'] == 'delegate'
        assert result['grant_id'] is not None
        assert result['duration_minutes'] == 120

    def test_delegate_sets_request_approved(self, app, user, agent,
                                             risk_policy, pending_request):
        from core.governance.approvals import approve_request

        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )

        db.session.refresh(pending_request)
        assert pending_request.status == 'approved'
        assert pending_request.reviewed_by == user.id

    def test_delegate_does_not_mutate_policy(self, app, user, agent,
                                              risk_policy, pending_request):
        """Delegate mode only creates a grant — no immediate policy change."""
        from core.governance.approvals import approve_request

        original_threshold = risk_policy.threshold_value

        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == original_threshold

    def test_delegate_grant_has_correct_bounds(self, app, user, agent,
                                                risk_policy, pending_request):
        from core.governance.approvals import approve_request

        result, _ = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )

        grant = DelegationGrant.query.get(result['grant_id'])
        assert grant is not None
        assert grant.active is True
        assert grant.duration_minutes == 60
        assert grant.agent_id == agent.id
        assert grant.workspace_id == user.id
        assert grant.granted_by == user.id

        # Allowed changes envelope should span from current to requested
        fields = grant.allowed_changes.get('fields', {})
        tv = fields.get('threshold_value', {})
        assert tv.get('min_value') == '10.0000'
        assert tv.get('max_value') == '15.0000'

    def test_delegate_creates_audit_entries(self, app, user, agent,
                                             risk_policy, pending_request):
        from core.governance.approvals import approve_request

        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )

        approved = GovernanceAuditLog.query.filter_by(
            event_type='request_approved',
        ).all()
        assert len(approved) == 1
        assert approved[0].details['mode'] == 'delegate'

        grants = GovernanceAuditLog.query.filter_by(
            event_type='grant_created',
        ).all()
        assert len(grants) == 1
        assert grants[0].details['duration_minutes'] == 60

    def test_delegate_missing_duration(self, app, user, agent, risk_policy,
                                       pending_request):
        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={},
        )

        assert result is None
        assert 'duration_minutes is required' in error

    def test_delegate_excessive_duration(self, app, user, agent, risk_policy,
                                         pending_request):
        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 9999},
        )

        assert result is None
        assert 'cannot exceed' in error

    def test_delegate_boundary_violation(self, app, user, agent, risk_policy):
        """Delegation rejected if requested value exceeds boundary."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '100.0000',
            },
            reason='too high',
        )

        result, error = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )

        assert result is None
        assert 'Boundary violation' in error


# ---------------------------------------------------------------------------
# Deny Request Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestDenyRequest:

    def test_deny_sets_status(self, app, user, agent, risk_policy,
                               pending_request):
        from core.governance.approvals import deny_request

        result, error = deny_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            reason='Not justified',
        )

        assert error is None
        assert result['status'] == 'denied'

        db.session.refresh(pending_request)
        assert pending_request.status == 'denied'
        assert pending_request.reviewed_by == user.id
        assert pending_request.reviewed_at is not None

    def test_deny_does_not_mutate_policy(self, app, user, agent,
                                          risk_policy, pending_request):
        from core.governance.approvals import deny_request

        original = risk_policy.to_dict()

        deny_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
        )

        db.session.refresh(risk_policy)
        assert risk_policy.to_dict() == original

    def test_deny_creates_audit_entry(self, app, user, agent, risk_policy,
                                       pending_request):
        from core.governance.approvals import deny_request

        deny_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            reason='Rejected by admin',
        )

        entries = GovernanceAuditLog.query.filter_by(
            event_type='request_denied',
        ).all()
        assert len(entries) == 1
        assert entries[0].details['reason'] == 'Rejected by admin'

    def test_deny_without_reason(self, app, user, agent, risk_policy,
                                  pending_request):
        from core.governance.approvals import deny_request

        result, error = deny_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
        )

        assert error is None
        assert result['status'] == 'denied'


# ---------------------------------------------------------------------------
# Authorization Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestApprovalAuthorization:

    def test_non_owner_non_admin_cannot_approve(self, app, user, agent,
                                                 risk_policy, pending_request,
                                                 other_user):
        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=other_user.id,
            mode='one_time',
        )

        assert result is None
        assert 'Only the workspace owner or an admin' in error

    def test_admin_can_approve_any_workspace(self, app, user, agent,
                                              risk_policy, pending_request,
                                              admin_user):
        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=admin_user.id,
            mode='one_time',
        )

        assert error is None
        assert result['status'] == 'applied'

    def test_non_owner_non_admin_cannot_deny(self, app, user, agent,
                                              risk_policy, pending_request,
                                              other_user):
        from core.governance.approvals import deny_request

        result, error = deny_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=other_user.id,
        )

        assert result is None
        assert 'Only the workspace owner or an admin' in error

    def test_cannot_approve_already_denied(self, app, user, agent,
                                            risk_policy, pending_request):
        from core.governance.approvals import approve_request, deny_request

        deny_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
        )

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        assert result is None
        assert 'already denied' in error

    def test_cannot_deny_already_applied(self, app, user, agent,
                                          risk_policy, pending_request):
        from core.governance.approvals import approve_request, deny_request

        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        result, error = deny_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
        )

        assert result is None
        assert 'already applied' in error

    def test_approve_wrong_workspace(self, app, user, agent, risk_policy,
                                      pending_request, other_user):
        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=other_user.id,
            approver_id=other_user.id,
            mode='one_time',
        )

        assert result is None
        assert 'not found' in error

    def test_invalid_mode_rejected(self, app, user, agent, risk_policy,
                                    pending_request):
        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='auto_apply',
        )

        assert result is None
        assert 'Invalid mode' in error


# ---------------------------------------------------------------------------
# Phase 2 Route Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestApproveRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.post('/api/governance/approve/1', json={
            'mode': 'one_time',
        })
        assert resp.status_code == 401

    def test_missing_mode(self, app, user, agent, risk_policy, pending_request):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post(
            f'/api/governance/approve/{pending_request.id}',
            json={},
        )
        assert resp.status_code == 400
        assert 'mode' in resp.get_json()['error']

    def test_one_time_via_route(self, app, user, agent, risk_policy,
                                 pending_request):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post(
            f'/api/governance/approve/{pending_request.id}',
            json={'mode': 'one_time'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['mode'] == 'one_time'
        assert data['status'] == 'applied'

        # Policy changed
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('15.0000')

    def test_delegate_via_route(self, app, user, agent, risk_policy,
                                 pending_request):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post(
            f'/api/governance/approve/{pending_request.id}',
            json={
                'mode': 'delegate',
                'delegation_params': {'duration_minutes': 120},
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['mode'] == 'delegate'
        assert data['grant_id'] is not None

    def test_boundary_violation_returns_403(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '100.0000',
            },
            reason='too high',
        )

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post(
            f'/api/governance/approve/{pcr.id}',
            json={'mode': 'one_time'},
        )
        assert resp.status_code == 403
        assert 'Boundary violation' in resp.get_json()['error']


@pytest.mark.governance
class TestDenyRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.post('/api/governance/deny/1', json={})
        assert resp.status_code == 401

    def test_deny_via_route(self, app, user, agent, risk_policy,
                             pending_request):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post(
            f'/api/governance/deny/{pending_request.id}',
            json={'reason': 'Not approved'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['status'] == 'denied'

    def test_deny_nonexistent_returns_400(self, app, user):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/deny/9999', json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Phase 2 Safety
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPhase2Safety:

    def test_one_time_approval_stores_before_after(self, app, user, agent,
                                                     risk_policy, pending_request):
        """change_applied audit entry has full before/after snapshots."""
        from core.governance.approvals import approve_request

        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        entry = GovernanceAuditLog.query.filter_by(
            event_type='change_applied',
        ).first()
        assert entry is not None

        before = entry.details['policy_before']
        after = entry.details['policy_after']
        assert before['threshold_value'] == '10.0000'
        assert after['threshold_value'] == '15.0000'

    def test_approve_does_not_affect_other_policies(self, app, user, agent,
                                                      risk_policy,
                                                      pending_request):
        """Only the targeted policy is modified."""
        from core.governance.approvals import approve_request

        # Create a second policy
        policy2 = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='error_rate_cap',
            threshold_value=Decimal('5.0000'),
            action_type='alert_only',
        )
        db.session.add(policy2)
        db.session.commit()
        original_p2 = policy2.to_dict()

        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        db.session.refresh(policy2)
        assert policy2.to_dict() == original_p2

    def test_module_exports_phase2(self, app):
        """Phase 2 public API exports work."""
        from core.governance import (
            approve_request, deny_request,
            validate_against_boundaries, get_workspace_boundaries,
        )
        assert callable(approve_request)
        assert callable(deny_request)
        assert callable(validate_against_boundaries)
        assert callable(get_workspace_boundaries)


# ===================================================================
# PHASE 3 — Delegation Enforcement
# ===================================================================

# ---------------------------------------------------------------------------
# Fixtures for Phase 3
# ---------------------------------------------------------------------------

@pytest.fixture
def active_grant(app, user, agent, risk_policy, pending_request):
    """Create an active delegation grant via the approval flow."""
    from core.governance.approvals import approve_request as do_approve

    result, _ = do_approve(
        request_id=pending_request.id,
        workspace_id=user.id,
        approver_id=user.id,
        mode='delegate',
        delegation_params={'duration_minutes': 120},
    )
    return DelegationGrant.query.get(result['grant_id'])


# ---------------------------------------------------------------------------
# Apply Delegated Change Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestApplyDelegatedChange:

    def test_apply_within_envelope(self, app, user, agent, risk_policy,
                                    active_grant):
        from core.governance.delegation import apply_delegated_change

        result, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '12.0000',
            },
        )

        assert error is None
        assert result['old_value'] == '10.0000'
        assert result['new_value'] == '12.0000'

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('12.0000')

    def test_apply_at_max_envelope(self, app, user, agent, risk_policy,
                                    active_grant):
        """Applying exactly at the envelope max is allowed."""
        from core.governance.delegation import apply_delegated_change

        result, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '15.0000',
            },
        )

        assert error is None
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('15.0000')

    def test_apply_exceeds_envelope(self, app, user, agent, risk_policy,
                                     active_grant):
        """Value above grant max is rejected."""
        from core.governance.delegation import apply_delegated_change

        result, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '20.0000',
            },
        )

        assert result is None
        assert 'envelope violation' in error

        # Policy unchanged
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

    def test_apply_below_envelope(self, app, user, agent, risk_policy,
                                   active_grant):
        """Value below grant min is rejected."""
        from core.governance.delegation import apply_delegated_change

        result, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '5.0000',
            },
        )

        assert result is None
        assert 'envelope violation' in error

    def test_apply_wrong_field(self, app, user, agent, risk_policy,
                                active_grant):
        """Field not in grant is rejected."""
        from core.governance.delegation import apply_delegated_change

        result, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'cooldown_minutes',
                'new_value': '60',
            },
        )

        assert result is None
        assert 'not covered by this grant' in error

    def test_apply_wrong_policy(self, app, user, agent, risk_policy,
                                 active_grant):
        """Policy not matching grant is rejected."""
        from core.governance.delegation import apply_delegated_change

        # Create another policy
        p2 = RiskPolicy(
            workspace_id=user.id, agent_id=agent.id,
            policy_type='error_rate_cap',
            threshold_value=Decimal('5.0000'),
            action_type='alert_only',
        )
        db.session.add(p2)
        db.session.commit()

        result, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': p2.id,
                'field': 'threshold_value',
                'new_value': '10.0000',
            },
        )

        assert result is None
        assert 'not policy' in error

    def test_apply_creates_audit_entries(self, app, user, agent, risk_policy,
                                          active_grant):
        from core.governance.delegation import apply_delegated_change

        apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '13.0000',
            },
        )

        used = GovernanceAuditLog.query.filter_by(
            event_type='grant_used',
        ).all()
        assert len(used) == 1
        assert used[0].details['grant_id'] == active_grant.id

        applied = GovernanceAuditLog.query.filter_by(
            event_type='change_applied',
        ).filter(
            GovernanceAuditLog.details['source'].as_string() == 'delegation'
        ).all()
        assert len(applied) >= 1

    def test_apply_multiple_times_within_envelope(self, app, user, agent,
                                                    risk_policy, active_grant):
        """Agent can use a grant multiple times as long as values stay in envelope."""
        from core.governance.delegation import apply_delegated_change

        # First: set to 12
        r1, e1 = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '12.0000',
            },
        )
        assert e1 is None

        # Second: set to 14
        r2, e2 = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '14.0000',
            },
        )
        assert e2 is None

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('14.0000')


# ---------------------------------------------------------------------------
# Expired Grant Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestExpiredGrant:

    def test_expired_grant_rejected(self, app, user, agent, risk_policy):
        """Cannot use a grant after its valid_to has passed."""
        from core.governance.delegation import apply_delegated_change

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={
                'policy_id': risk_policy.id,
                'fields': {
                    'threshold_value': {'min_value': '10', 'max_value': '20'},
                },
            },
            duration_minutes=60,
            valid_from=now - timedelta(hours=2),
            valid_to=now - timedelta(hours=1),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        result, error = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '15.0000',
            },
        )

        assert result is None
        assert 'expired' in error

        # Grant should have been auto-deactivated
        db.session.refresh(grant)
        assert grant.active is False

    def test_not_yet_valid_grant_rejected(self, app, user, agent, risk_policy):
        """Cannot use a grant before its valid_from."""
        from core.governance.delegation import apply_delegated_change

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={
                'policy_id': risk_policy.id,
                'fields': {
                    'threshold_value': {'min_value': '10', 'max_value': '20'},
                },
            },
            duration_minutes=60,
            valid_from=now + timedelta(hours=1),
            valid_to=now + timedelta(hours=2),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        result, error = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '15.0000',
            },
        )

        assert result is None
        assert 'not yet valid' in error


# ---------------------------------------------------------------------------
# Grant Expiration Cron Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestExpireGrants:

    def test_expire_deactivates_old_grants(self, app, user, agent):
        from core.governance.delegation import expire_grants

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={},
            duration_minutes=60,
            valid_from=now - timedelta(hours=2),
            valid_to=now - timedelta(hours=1),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        count = expire_grants()
        assert count == 1

        db.session.refresh(grant)
        assert grant.active is False

    def test_expire_skips_active_grants(self, app, user, agent):
        from core.governance.delegation import expire_grants

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={},
            duration_minutes=120,
            valid_from=now,
            valid_to=now + timedelta(hours=2),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        count = expire_grants()
        assert count == 0

        db.session.refresh(grant)
        assert grant.active is True

    def test_expire_skips_already_inactive(self, app, user, agent):
        from core.governance.delegation import expire_grants

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={},
            duration_minutes=60,
            valid_from=now - timedelta(hours=2),
            valid_to=now - timedelta(hours=1),
            active=False,
        )
        db.session.add(grant)
        db.session.commit()

        count = expire_grants()
        assert count == 0

    def test_expire_creates_audit_entries(self, app, user, agent):
        from core.governance.delegation import expire_grants

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={},
            duration_minutes=60,
            valid_from=now - timedelta(hours=2),
            valid_to=now - timedelta(hours=1),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        expire_grants()

        entries = GovernanceAuditLog.query.filter_by(
            event_type='grant_expired',
        ).all()
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# Grant Revocation Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestRevokeGrant:

    def test_revoke_deactivates_grant(self, app, user, agent, risk_policy,
                                      active_grant):
        from core.governance.delegation import revoke_grant

        result, error = revoke_grant(
            grant_id=active_grant.id,
            workspace_id=user.id,
            revoker_id=user.id,
        )

        assert error is None
        assert result['status'] == 'revoked'

        db.session.refresh(active_grant)
        assert active_grant.active is False
        assert active_grant.revoked_at is not None
        assert active_grant.revoked_by == user.id

    def test_revoked_grant_cannot_be_used(self, app, user, agent, risk_policy,
                                           active_grant):
        from core.governance.delegation import revoke_grant, apply_delegated_change

        revoke_grant(
            grant_id=active_grant.id,
            workspace_id=user.id,
            revoker_id=user.id,
        )

        result, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '12.0000',
            },
        )

        assert result is None
        assert 'no longer active' in error

    def test_revoke_creates_audit_entry(self, app, user, agent, risk_policy,
                                         active_grant):
        from core.governance.delegation import revoke_grant

        revoke_grant(
            grant_id=active_grant.id,
            workspace_id=user.id,
            revoker_id=user.id,
        )

        entries = GovernanceAuditLog.query.filter_by(
            event_type='grant_revoked',
        ).all()
        assert len(entries) == 1
        assert entries[0].details['revoked_by'] == user.id

    def test_revoke_already_inactive(self, app, user, agent, risk_policy,
                                      active_grant):
        from core.governance.delegation import revoke_grant

        active_grant.active = False
        db.session.commit()

        result, error = revoke_grant(
            grant_id=active_grant.id,
            workspace_id=user.id,
            revoker_id=user.id,
        )

        assert result is None
        assert 'already inactive' in error

    def test_non_owner_cannot_revoke(self, app, user, agent, risk_policy,
                                      active_grant, other_user):
        from core.governance.delegation import revoke_grant

        result, error = revoke_grant(
            grant_id=active_grant.id,
            workspace_id=user.id,
            revoker_id=other_user.id,
        )

        assert result is None
        assert 'Only the workspace owner' in error

    def test_admin_can_revoke(self, app, user, agent, risk_policy,
                               active_grant, admin_user):
        from core.governance.delegation import revoke_grant

        result, error = revoke_grant(
            grant_id=active_grant.id,
            workspace_id=user.id,
            revoker_id=admin_user.id,
        )

        assert error is None
        assert result['status'] == 'revoked'


# ---------------------------------------------------------------------------
# No Stacking Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestNoGrantStacking:

    def test_grants_do_not_stack(self, app, user, agent, risk_policy):
        """Two grants for the same policy — each enforces its own envelope."""
        from core.governance.delegation import apply_delegated_change

        now = datetime.utcnow()

        # Grant 1: allows 10-15
        g1 = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={
                'policy_id': risk_policy.id,
                'fields': {
                    'threshold_value': {'min_value': '10', 'max_value': '15'},
                },
            },
            duration_minutes=120,
            valid_from=now, valid_to=now + timedelta(hours=2),
            active=True,
        )
        # Grant 2: allows 12-20
        g2 = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={
                'policy_id': risk_policy.id,
                'fields': {
                    'threshold_value': {'min_value': '12', 'max_value': '20'},
                },
            },
            duration_minutes=120,
            valid_from=now, valid_to=now + timedelta(hours=2),
            active=True,
        )
        db.session.add_all([g1, g2])
        db.session.commit()

        # Using grant 1 to set 18 should fail (max is 15)
        r1, e1 = apply_delegated_change(
            grant_id=g1.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '18.0000',
            },
        )
        assert r1 is None
        assert 'envelope violation' in e1

        # Using grant 2 to set 18 should succeed (max is 20)
        r2, e2 = apply_delegated_change(
            grant_id=g2.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '18.0000',
            },
        )
        assert e2 is None
        assert r2['new_value'] == '18.0000'

    def test_grant_envelope_is_absolute_not_relative(self, app, user, agent,
                                                       risk_policy):
        """Grant bounds are absolute values, not relative to current policy."""
        from core.governance.delegation import apply_delegated_change

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={
                'policy_id': risk_policy.id,
                'fields': {
                    'threshold_value': {'min_value': '10', 'max_value': '15'},
                },
            },
            duration_minutes=120,
            valid_from=now, valid_to=now + timedelta(hours=2),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        # Set to 15
        apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '15.0000',
            },
        )

        # Now try to set to 16 — should fail even though current is 15
        r, e = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '16.0000',
            },
        )
        assert r is None
        assert 'envelope violation' in e


# ---------------------------------------------------------------------------
# Get Active Grants Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestGetActiveGrants:

    def test_returns_active_grants(self, app, user, agent, risk_policy,
                                    active_grant):
        from core.governance.delegation import get_active_grants

        grants = get_active_grants(workspace_id=user.id)
        assert len(grants) == 1
        assert grants[0].id == active_grant.id

    def test_excludes_expired(self, app, user, agent):
        from core.governance.delegation import get_active_grants

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id, allowed_changes={},
            duration_minutes=60,
            valid_from=now - timedelta(hours=2),
            valid_to=now - timedelta(hours=1),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        grants = get_active_grants(workspace_id=user.id)
        assert len(grants) == 0

    def test_excludes_inactive(self, app, user, agent):
        from core.governance.delegation import get_active_grants

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id, allowed_changes={},
            duration_minutes=120,
            valid_from=now, valid_to=now + timedelta(hours=2),
            active=False,
        )
        db.session.add(grant)
        db.session.commit()

        grants = get_active_grants(workspace_id=user.id)
        assert len(grants) == 0

    def test_filters_by_agent(self, app, user, agent, risk_policy,
                               active_grant, other_user, other_agent):
        from core.governance.delegation import get_active_grants

        by_agent = get_active_grants(
            workspace_id=user.id, agent_id=agent.id,
        )
        assert len(by_agent) == 1

        by_other = get_active_grants(
            workspace_id=user.id, agent_id=9999,
        )
        assert len(by_other) == 0

    def test_workspace_isolation(self, app, user, agent, risk_policy,
                                  active_grant, other_user):
        from core.governance.delegation import get_active_grants

        grants = get_active_grants(workspace_id=other_user.id)
        assert len(grants) == 0


# ---------------------------------------------------------------------------
# Workspace Boundary on Delegated Apply
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestDelegationWorkspaceBoundary:

    def test_workspace_boundary_enforced_on_delegation(self, app, user, agent,
                                                        risk_policy):
        """Even if grant envelope allows it, workspace boundary blocks it."""
        from core.governance.delegation import apply_delegated_change

        now = datetime.utcnow()
        # Grant allows up to 100 — but free tier caps at 50
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={
                'policy_id': risk_policy.id,
                'fields': {
                    'threshold_value': {'min_value': '10', 'max_value': '100'},
                },
            },
            duration_minutes=120,
            valid_from=now, valid_to=now + timedelta(hours=2),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        result, error = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '75.0000',
            },
        )

        assert result is None
        assert 'Workspace boundary violation' in error

        # Policy unchanged
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

    def test_within_both_grant_and_workspace(self, app, user, agent,
                                              risk_policy):
        """Value within both grant envelope and workspace boundary succeeds."""
        from core.governance.delegation import apply_delegated_change

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={
                'policy_id': risk_policy.id,
                'fields': {
                    'threshold_value': {'min_value': '10', 'max_value': '40'},
                },
            },
            duration_minutes=120,
            valid_from=now, valid_to=now + timedelta(hours=2),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        result, error = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '35.0000',
            },
        )

        assert error is None
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('35.0000')


# ---------------------------------------------------------------------------
# Phase 3 Route Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestDelegateApplyRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.post('/api/governance/delegate/apply', json={})
        assert resp.status_code == 401

    def test_apply_via_route(self, app, user, agent, risk_policy, active_grant):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/delegate/apply', json={
            'grant_id': active_grant.id,
            'agent_id': agent.id,
            'requested_change': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '13.0000',
            },
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['new_value'] == '13.0000'

    def test_envelope_violation_returns_403(self, app, user, agent,
                                             risk_policy, active_grant):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/delegate/apply', json={
            'grant_id': active_grant.id,
            'agent_id': agent.id,
            'requested_change': {
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '99.0000',
            },
        })
        assert resp.status_code == 403

    def test_missing_fields(self, app, user, agent, risk_policy, active_grant):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/delegate/apply', json={
            'agent_id': agent.id,
            'requested_change': {},
        })
        assert resp.status_code == 400


@pytest.mark.governance
class TestDelegationsListRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.get('/api/governance/delegations')
        assert resp.status_code == 401

    def test_list_active(self, app, user, agent, risk_policy, active_grant):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/delegations')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1

    def test_list_empty(self, app, user):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/delegations')
        assert resp.status_code == 200
        assert resp.get_json()['count'] == 0


@pytest.mark.governance
class TestRevokeRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.post('/api/governance/delegations/1/revoke')
        assert resp.status_code == 401

    def test_revoke_via_route(self, app, user, agent, risk_policy, active_grant):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post(
            f'/api/governance/delegations/{active_grant.id}/revoke',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['status'] == 'revoked'


@pytest.mark.governance
class TestExpireCronRoute:

    def test_unauthenticated_rejected(self, app):
        client = app.test_client()
        resp = client.post('/api/governance/internal/expire', json={})
        assert resp.status_code == 401

    def test_with_admin_password(self, app):
        import os
        os.environ['ADMIN_PASSWORD'] = 'test_admin_pass'

        client = app.test_client()
        resp = client.post('/api/governance/internal/expire', json={
            'password': 'test_admin_pass',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'requests_expired' in data
        assert 'grants_expired' in data

        del os.environ['ADMIN_PASSWORD']

    def test_with_cron_secret(self, app):
        import os
        os.environ['CRON_SECRET'] = 'test_cron_secret'

        client = app.test_client()
        resp = client.post(
            '/api/governance/internal/expire',
            headers={'Authorization': 'Bearer test_cron_secret'},
        )
        assert resp.status_code == 200

        del os.environ['CRON_SECRET']


# ---------------------------------------------------------------------------
# Phase 3 Module Exports
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPhase3Exports:

    def test_module_exports_phase3(self, app):
        from core.governance import (
            get_active_grants, apply_delegated_change,
            expire_grants, revoke_grant,
        )
        assert callable(get_active_grants)
        assert callable(apply_delegated_change)
        assert callable(expire_grants)
        assert callable(revoke_grant)


# ---------------------------------------------------------------------------
# Phase 3 Determinism
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestDelegationDeterminism:

    def test_same_input_same_result(self, app, user, agent, risk_policy):
        """Identical delegated applies produce identical results."""
        from core.governance.delegation import apply_delegated_change

        now = datetime.utcnow()
        grant = DelegationGrant(
            workspace_id=user.id, agent_id=agent.id,
            granted_by=user.id,
            allowed_changes={
                'policy_id': risk_policy.id,
                'fields': {
                    'threshold_value': {'min_value': '10', 'max_value': '20'},
                },
            },
            duration_minutes=120,
            valid_from=now, valid_to=now + timedelta(hours=2),
            active=True,
        )
        db.session.add(grant)
        db.session.commit()

        r1, _ = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '15.0000',
            },
        )

        # Apply same value again — idempotent
        r2, _ = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '15.0000',
            },
        )

        assert r1['new_value'] == r2['new_value']
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('15.0000')

    def test_wrong_agent_cannot_use_grant(self, app, user, agent, risk_policy,
                                           active_grant):
        """Grant is bound to a specific agent."""
        from core.governance.delegation import apply_delegated_change

        agent2 = Agent(
            user_id=user.id, name='Agent2', is_active=True,
            created_at=datetime.utcnow(),
        )
        db.session.add(agent2)
        db.session.commit()

        result, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent2.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '12.0000',
            },
        )

        assert result is None
        assert 'does not belong to this agent' in error


# ===========================================================================
# Phase 4: Safety Guarantees — Rollback, Invariants, Failure Simulation
# ===========================================================================


# ---------------------------------------------------------------------------
# Rollback Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def applied_change(app, user, agent, risk_policy, pending_request):
    """Apply a one-time change and return the audit entry for the application."""
    from core.governance.approvals import approve_request as do_approve
    from core.governance.governance_audit import get_governance_trail

    do_approve(
        request_id=pending_request.id,
        workspace_id=user.id,
        approver_id=user.id,
        mode='one_time',
    )

    entries = get_governance_trail(
        workspace_id=user.id,
        event_type='change_applied',
    )
    assert len(entries) >= 1
    return entries[0]


@pytest.mark.governance
class TestRollbackChange:

    def test_rollback_restores_policy(self, app, user, agent, risk_policy,
                                      pending_request, applied_change):
        """Rolling back a change_applied event restores policy_before."""
        from core.governance.rollback import rollback_change

        # Policy should be at the approved value now
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('15.0000')

        result, error = rollback_change(
            audit_entry_id=applied_change.id,
            workspace_id=user.id,
            actor_id=user.id,
        )

        assert error is None
        assert result['policy_id'] == risk_policy.id

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

    def test_rollback_creates_audit_entry(self, app, user, agent, risk_policy,
                                          pending_request, applied_change):
        """Rollback creates a change_rolled_back audit entry."""
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail

        rollback_change(
            audit_entry_id=applied_change.id,
            workspace_id=user.id,
            actor_id=user.id,
        )

        entries = get_governance_trail(
            workspace_id=user.id,
            event_type='change_rolled_back',
        )
        assert len(entries) == 1
        entry = entries[0]
        assert entry.details['rolled_back_entry_id'] == applied_change.id
        assert entry.details['policy_id'] == risk_policy.id
        assert 'policy_before' in entry.details
        assert 'policy_after' in entry.details

    def test_rollback_audit_stores_before_and_after(self, app, user, agent,
                                                     risk_policy,
                                                     pending_request,
                                                     applied_change):
        """Rollback audit entry contains pre-rollback and post-rollback state."""
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail

        result, _ = rollback_change(
            audit_entry_id=applied_change.id,
            workspace_id=user.id,
            actor_id=user.id,
        )

        entries = get_governance_trail(
            workspace_id=user.id,
            event_type='change_rolled_back',
        )
        entry = entries[0]

        # policy_before in the rollback entry = state before rollback (15.0000)
        assert entry.details['policy_before']['threshold_value'] == '15.0000'
        # policy_after in the rollback entry = state after rollback (10.0000)
        assert entry.details['policy_after']['threshold_value'] == '10.0000'

    def test_rollback_of_rollback(self, app, user, agent, risk_policy,
                                   pending_request, applied_change):
        """Rolling back a rollback restores the state before the rollback."""
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail

        # First rollback: 15 -> 10
        rollback_change(
            audit_entry_id=applied_change.id,
            workspace_id=user.id,
            actor_id=user.id,
        )
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

        # Get the rollback audit entry
        rollback_entries = get_governance_trail(
            workspace_id=user.id,
            event_type='change_rolled_back',
        )
        rollback_entry = rollback_entries[0]

        # Second rollback (of the rollback): 10 -> 15
        result, error = rollback_change(
            audit_entry_id=rollback_entry.id,
            workspace_id=user.id,
            actor_id=user.id,
        )

        assert error is None
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('15.0000')

    def test_rollback_boundary_revalidation(self, app, user, agent,
                                             risk_policy):
        """Rollback is blocked if restoring would violate current boundaries."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request as do_approve
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail
        from core.observability.tier_enforcement import invalidate_tier_cache

        # Start with pro tier: boundary $500
        tier = WorkspaceTier(
            workspace_id=user.id,
            tier_name='pro',
            **WorkspaceTier.TIER_DEFAULTS['pro'],
        )
        db.session.add(tier)
        db.session.commit()
        invalidate_tier_cache(user.id)

        # Set policy threshold to $400 (within pro boundary)
        risk_policy.threshold_value = Decimal('400.0000')
        db.session.commit()

        # Request change to $200 — within pro boundary
        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '400.0000',
                'requested_value': '200.0000',
            },
            reason='Lower the cap',
        )

        result, error = do_approve(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )
        assert error is None, f'Approval failed: {error}'

        entries = get_governance_trail(
            workspace_id=user.id,
            event_type='change_applied',
        )
        change_entry = entries[0]

        # Now downgrade tier to free (boundary $50)
        tier.tier_name = 'free'
        db.session.commit()
        invalidate_tier_cache(user.id)

        # Try to rollback: would restore $400, but free tier cap is $50
        result, error = rollback_change(
            audit_entry_id=change_entry.id,
            workspace_id=user.id,
            actor_id=user.id,
        )

        assert result is None
        assert 'boundary' in error.lower()
        # Policy should still be at $200
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('200.0000')

    def test_rollback_non_mutation_event_rejected(self, app, user, agent,
                                                   risk_policy,
                                                   pending_request):
        """Cannot rollback a non-mutation event like request_submitted."""
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail

        entries = get_governance_trail(
            workspace_id=user.id,
            event_type='request_submitted',
        )
        assert len(entries) >= 1

        result, error = rollback_change(
            audit_entry_id=entries[0].id,
            workspace_id=user.id,
            actor_id=user.id,
        )

        assert result is None
        assert 'Cannot rollback event type' in error

    def test_rollback_wrong_workspace(self, app, user, agent, risk_policy,
                                       pending_request, applied_change,
                                       other_user):
        """Cannot rollback a change from another workspace."""
        from core.governance.rollback import rollback_change

        result, error = rollback_change(
            audit_entry_id=applied_change.id,
            workspace_id=other_user.id,
            actor_id=other_user.id,
        )

        assert result is None
        assert 'not found' in error.lower()

    def test_rollback_authorization(self, app, user, agent, risk_policy,
                                     pending_request, applied_change,
                                     other_user):
        """Non-owner, non-admin cannot rollback."""
        from core.governance.rollback import rollback_change

        result, error = rollback_change(
            audit_entry_id=applied_change.id,
            workspace_id=user.id,
            actor_id=other_user.id,
        )

        assert result is None
        assert 'Only the workspace owner or an admin' in error

    def test_admin_can_rollback(self, app, user, agent, risk_policy,
                                 pending_request, applied_change, admin_user):
        """Admin user can rollback changes for any workspace."""
        from core.governance.rollback import rollback_change

        result, error = rollback_change(
            audit_entry_id=applied_change.id,
            workspace_id=user.id,
            actor_id=admin_user.id,
        )

        assert error is None
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

    def test_rollback_delegation_applied_change(self, app, user, agent,
                                                 risk_policy, active_grant):
        """Can rollback a change that was applied via delegation."""
        from core.governance.delegation import apply_delegated_change
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail

        # Apply via delegation
        apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '14.0000',
            },
        )

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('14.0000')

        entries = get_governance_trail(
            workspace_id=user.id,
            event_type='change_applied',
        )
        change_entry = entries[0]

        result, error = rollback_change(
            audit_entry_id=change_entry.id,
            workspace_id=user.id,
            actor_id=user.id,
        )

        assert error is None
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')


# ---------------------------------------------------------------------------
# Rollback Route Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestRollbackRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.post('/api/governance/rollback/1')
        assert resp.status_code == 401

    def test_rollback_via_route(self, app, user, agent, risk_policy,
                                 pending_request, applied_change, client):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post(f'/api/governance/rollback/{applied_change.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['policy_id'] == risk_policy.id

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

    def test_rollback_nonexistent_returns_400(self, app, user, client):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post('/api/governance/rollback/99999')
        assert resp.status_code == 400

    def test_rollback_boundary_violation_returns_403(self, app, user, agent,
                                                      risk_policy, client):
        """Rollback that would violate boundaries returns 403."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request as do_approve
        from core.governance.governance_audit import get_governance_trail
        from core.observability.tier_enforcement import invalidate_tier_cache

        tier = WorkspaceTier(
            workspace_id=user.id,
            tier_name='pro',
            **WorkspaceTier.TIER_DEFAULTS['pro'],
        )
        db.session.add(tier)
        db.session.commit()
        invalidate_tier_cache(user.id)

        risk_policy.threshold_value = Decimal('300.0000')
        db.session.commit()

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '300.0000',
                'requested_value': '100.0000',
            },
            reason='Lower cap',
        )
        result, error = do_approve(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )
        assert error is None, f'Approval failed: {error}'

        entries = get_governance_trail(
            workspace_id=user.id,
            event_type='change_applied',
        )

        # Downgrade to free tier
        tier.tier_name = 'free'
        db.session.commit()
        invalidate_tier_cache(user.id)

        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.post(f'/api/governance/rollback/{entries[0].id}')
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Audit Trail Route Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestAuditTrailRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.get('/api/governance/audit')
        assert resp.status_code == 401

    def test_empty_trail(self, app, user, client):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/audit')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 0
        assert data['audit_trail'] == []

    def test_trail_with_entries(self, app, user, agent, risk_policy,
                                 pending_request, client):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/audit')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] >= 1

    def test_filter_by_event_type(self, app, user, agent, risk_policy,
                                    pending_request, client):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/audit?event_type=request_submitted')
        data = resp.get_json()
        assert data['count'] >= 1
        for entry in data['audit_trail']:
            assert entry['event_type'] == 'request_submitted'

    def test_filter_by_agent(self, app, user, agent, risk_policy,
                              pending_request, client):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get(f'/api/governance/audit?agent_id={agent.id}')
        data = resp.get_json()
        assert data['count'] >= 1
        for entry in data['audit_trail']:
            assert entry['agent_id'] == agent.id

    def test_workspace_isolation(self, app, user, agent, risk_policy,
                                  pending_request, other_user, client):
        with client.session_transaction() as sess:
            sess['user_id'] = other_user.id

        resp = client.get('/api/governance/audit')
        data = resp.get_json()
        assert data['count'] == 0

    def test_limit_parameter(self, app, user, agent, risk_policy,
                              pending_request, client):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/audit?limit=1')
        data = resp.get_json()
        assert data['count'] <= 1


# ---------------------------------------------------------------------------
# Policy Diff Validation: No Full Overwrite
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPolicyDiffValidation:
    """Ensure governance only allows single-field changes, not full overwrites."""

    def test_only_single_field_per_request(self, app, user, agent, risk_policy):
        """Each request targets exactly one mutable field."""
        from core.governance.requests import create_request

        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='Single field change',
        )
        # This should succeed — single field
        assert error is None
        assert pcr.requested_changes['field'] == 'threshold_value'

    def test_immutable_field_policy_type_rejected(self, app, user, agent,
                                                    risk_policy):
        """Cannot request a change to policy_type (structural field)."""
        from core.governance.requests import create_request

        _, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'policy_type',
                'requested_value': 'token_rate',
            },
            reason='Want different policy type',
        )
        assert error is not None
        assert 'not mutable' in error

    def test_immutable_field_is_enabled_rejected(self, app, user, agent,
                                                   risk_policy):
        """Cannot disable a policy via governance (removes safety net)."""
        from core.governance.requests import create_request

        _, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'is_enabled',
                'requested_value': False,
            },
            reason='Disable policy',
        )
        assert error is not None
        assert 'not mutable' in error

    def test_immutable_field_workspace_id_rejected(self, app, user, agent,
                                                     risk_policy):
        """Cannot change workspace_id (would break isolation)."""
        from core.governance.requests import create_request

        _, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'workspace_id',
                'requested_value': 999,
            },
            reason='Move to different workspace',
        )
        assert error is not None
        assert 'not mutable' in error

    def test_immutable_field_agent_id_rejected(self, app, user, agent,
                                                risk_policy):
        """Cannot change agent_id via governance."""
        from core.governance.requests import create_request

        _, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'agent_id',
                'requested_value': 999,
            },
            reason='Re-scope policy',
        )
        assert error is not None
        assert 'not mutable' in error

    def test_mutable_fields_are_limited(self, app):
        """Only three fields are mutable via governance."""
        from core.governance.requests import MUTABLE_FIELDS

        assert MUTABLE_FIELDS == frozenset({
            'threshold_value', 'action_type', 'cooldown_minutes',
        })


# ---------------------------------------------------------------------------
# Safety Invariant Tests (Architecture Section 6)
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestSafetyInvariant_NoSilentMutation:
    """Invariant 6.1: Every agent-originated policy mutation goes through
    the request pipeline. Direct mutation is forbidden."""

    def test_create_request_never_mutates(self, app, user, agent, risk_policy):
        """Submitting a request must not change the policy."""
        from core.governance.requests import create_request

        original = risk_policy.to_dict()

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '99.0000',
            },
            reason='Test no mutation',
        )

        db.session.refresh(risk_policy)
        assert risk_policy.to_dict() == original

    def test_deny_never_mutates(self, app, user, agent, risk_policy,
                                 pending_request):
        """Denying a request must not change the policy."""
        from core.governance.approvals import deny_request

        original = risk_policy.to_dict()

        deny_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            reason='Denied',
        )

        db.session.refresh(risk_policy)
        assert risk_policy.to_dict() == original

    def test_governance_module_does_not_import_risk_engine_mutators(self, app):
        """Governance never imports risk engine write functions."""
        import core.governance.requests as req_mod
        import core.governance.approvals as app_mod
        import core.governance.delegation as del_mod
        import core.governance.rollback as rb_mod

        for mod in [req_mod, app_mod, del_mod, rb_mod]:
            source = open(mod.__file__).read()
            assert 'from core.risk_engine' not in source
            assert 'import core.risk_engine' not in source


@pytest.mark.governance
class TestSafetyInvariant_HumanAuthority:
    """Invariant 6.2: No policy change without explicit human approval."""

    def test_pending_request_does_not_apply(self, app, user, agent,
                                             risk_policy, pending_request):
        """A pending request does not change the policy."""
        original = risk_policy.to_dict()
        assert pending_request.status == 'pending'

        db.session.refresh(risk_policy)
        assert risk_policy.to_dict() == original

    def test_approval_requires_human_actor(self, app, user, agent,
                                            risk_policy, pending_request,
                                            other_user):
        """Non-owner, non-admin cannot approve."""
        from core.governance.approvals import approve_request

        _, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=other_user.id,
            mode='one_time',
        )
        assert error is not None
        assert 'Only the workspace owner' in error


@pytest.mark.governance
class TestSafetyInvariant_BoundaryInviolability:
    """Invariant 6.3: No policy value can exceed workspace boundaries."""

    def test_one_time_blocked_at_boundary(self, app, user, agent, risk_policy):
        """One-time approval is blocked if value exceeds tier boundary."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '10.0000',
                'requested_value': '100.0000',
            },
            reason='Exceed boundary',
        )

        _, error = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )
        assert error is not None
        assert 'Boundary violation' in error

    def test_delegation_blocked_at_boundary(self, app, user, agent,
                                             risk_policy):
        """Delegation grant creation is blocked if envelope exceeds boundary."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '10.0000',
                'requested_value': '100.0000',
            },
            reason='Exceed via delegation',
        )

        _, error = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )
        assert error is not None
        assert 'Boundary violation' in error

    def test_delegated_apply_blocked_at_boundary(self, app, user, agent,
                                                   risk_policy, active_grant):
        """Applying via grant is blocked if it would exceed workspace boundary.

        Even if the grant envelope allows it, workspace boundaries prevail.
        """
        from core.governance.delegation import apply_delegated_change
        from models import WorkspaceTier

        # Downgrade tier to free: max $50
        # Grant was created under free tier so envelope max is $15
        # This tests the workspace boundary check, not envelope check
        # We need to test with a grant whose envelope is valid but
        # workspace boundary is tighter. We manipulate the grant directly.
        active_grant.allowed_changes = {
            'policy_id': risk_policy.id,
            'fields': {
                'threshold_value': {
                    'min_value': '10',
                    'max_value': '200',
                }
            }
        }
        db.session.commit()

        # Apply $100 — within grant envelope but exceeds free tier $50 boundary
        _, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '100.0000',
            },
        )
        assert error is not None
        assert 'boundary violation' in error.lower()


@pytest.mark.governance
class TestSafetyInvariant_TimeBoundedDelegation:
    """Invariant 6.4: Every delegation grant has a finite duration."""

    def test_grant_has_finite_duration(self, app, user, agent, risk_policy,
                                        active_grant):
        assert active_grant.duration_minutes == 120
        assert active_grant.valid_to > active_grant.valid_from
        diff = active_grant.valid_to - active_grant.valid_from
        assert diff.total_seconds() == 120 * 60

    def test_grant_max_duration_enforced(self, app, user, agent, risk_policy,
                                          pending_request):
        """Cannot create a grant exceeding 24 hours."""
        from core.governance.approvals import approve_request

        _, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 9999},
        )
        assert error is not None
        assert 'cannot exceed' in error.lower()

    def test_grant_zero_duration_rejected(self, app, user, agent, risk_policy,
                                           pending_request):
        """Cannot create a grant with zero duration."""
        from core.governance.approvals import approve_request

        _, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 0},
        )
        assert error is not None
        assert 'at least 1' in error


@pytest.mark.governance
class TestSafetyInvariant_NoGrantStacking:
    """Invariant 6.5: Grants define absolute limits, not relative ones."""

    def test_two_grants_independent_bounds(self, app, user, agent, risk_policy):
        """Each grant's envelope is checked independently."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request
        from core.governance.delegation import apply_delegated_change
        from models import DelegationGrant
        import time

        # Create first request + grant (10 -> 12)
        pcr1, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '10.0000',
                'requested_value': '12.0000',
            },
            reason='First grant',
        )
        r1, _ = approve_request(
            request_id=pcr1.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )
        grant1 = DelegationGrant.query.get(r1['grant_id'])

        # Wait a moment to avoid cooldown
        time.sleep(0.01)

        # Create second request + grant (10 -> 14)
        # Need a fresh pending request — cooldown on same policy
        # Manually insert to bypass cooldown for testing
        from models import db, PolicyChangeRequest
        pcr2 = PolicyChangeRequest(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '10.0000',
                'requested_value': '14.0000',
            },
            reason='Second grant',
            status='pending',
            requested_at=datetime.utcnow() - timedelta(minutes=20),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            policy_snapshot=risk_policy.to_dict(),
        )
        db.session.add(pcr2)
        db.session.commit()

        r2, _ = approve_request(
            request_id=pcr2.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )
        grant2 = DelegationGrant.query.get(r2['grant_id'])

        # Use grant1 to set policy to 12
        apply_delegated_change(
            grant_id=grant1.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '12.0000',
            },
        )

        # Try to use grant1 to set to 13 (outside grant1's envelope [10,12])
        _, error = apply_delegated_change(
            grant_id=grant1.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '13.0000',
            },
        )
        assert error is not None
        assert 'exceeds grant maximum' in error

        # But grant2 (envelope [10,14]) allows 13
        result, error = apply_delegated_change(
            grant_id=grant2.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '13.0000',
            },
        )
        assert error is None


@pytest.mark.governance
class TestSafetyInvariant_FullAuditability:
    """Invariant 6.6: Every state transition is audited."""

    def test_request_submit_audited(self, app, user, agent, risk_policy,
                                     pending_request):
        from core.governance.governance_audit import get_governance_trail
        entries = get_governance_trail(user.id, event_type='request_submitted')
        assert len(entries) >= 1

    def test_approval_audited(self, app, user, agent, risk_policy,
                               pending_request, applied_change):
        from core.governance.governance_audit import get_governance_trail
        entries = get_governance_trail(user.id, event_type='request_approved')
        assert len(entries) >= 1

    def test_denial_audited(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request
        from core.governance.approvals import deny_request
        from core.governance.governance_audit import get_governance_trail

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='Will be denied',
        )
        deny_request(pcr.id, user.id, user.id, 'No')

        entries = get_governance_trail(user.id, event_type='request_denied')
        assert len(entries) >= 1

    def test_change_applied_audited(self, app, user, agent, risk_policy,
                                     pending_request, applied_change):
        from core.governance.governance_audit import get_governance_trail
        entries = get_governance_trail(user.id, event_type='change_applied')
        assert len(entries) >= 1
        assert 'policy_before' in entries[0].details
        assert 'policy_after' in entries[0].details

    def test_rollback_audited(self, app, user, agent, risk_policy,
                               pending_request, applied_change):
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail

        rollback_change(applied_change.id, user.id, user.id)

        entries = get_governance_trail(user.id, event_type='change_rolled_back')
        assert len(entries) == 1

    def test_boundary_violation_audited(self, app, user, agent, risk_policy):
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request
        from core.governance.governance_audit import get_governance_trail

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '100.0000',
            },
            reason='Will exceed boundary',
        )
        approve_request(pcr.id, user.id, user.id, 'one_time')

        entries = get_governance_trail(user.id, event_type='boundary_violation')
        assert len(entries) >= 1

    def test_audit_log_is_append_only(self, app, user, agent, risk_policy,
                                       pending_request):
        """Audit log entries cannot be updated or deleted via the module API."""
        from core.governance import governance_audit as gmod
        import inspect

        # The module should only have log_governance_event and
        # get_governance_trail — no update/delete functions
        public_funcs = [
            name for name, obj in inspect.getmembers(gmod, inspect.isfunction)
            if not name.startswith('_')
        ]
        assert 'log_governance_event' in public_funcs
        assert 'get_governance_trail' in public_funcs
        for name in public_funcs:
            assert 'delete' not in name.lower()
            assert 'update' not in name.lower()
            assert 'remove' not in name.lower()


@pytest.mark.governance
class TestSafetyInvariant_RollbackCapability:
    """Invariant 6.7: Any governance-applied change can be reversed."""

    def test_one_time_change_reversible(self, app, user, agent, risk_policy,
                                         pending_request, applied_change):
        from core.governance.rollback import rollback_change

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('15.0000')

        rollback_change(applied_change.id, user.id, user.id)

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

    def test_delegation_change_reversible(self, app, user, agent, risk_policy,
                                           active_grant):
        from core.governance.delegation import apply_delegated_change
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail

        apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '13.0000',
            },
        )

        entries = get_governance_trail(user.id, event_type='change_applied')
        rollback_change(entries[0].id, user.id, user.id)

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')


# ---------------------------------------------------------------------------
# Failure Simulation Tests (Architecture Section 11 — QA)
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestFailureSimulation:

    def test_crash_mid_approval_no_partial_state(self, app, user, agent,
                                                   risk_policy,
                                                   pending_request):
        """If approval raises mid-way, neither the policy nor the request
        status should change (atomic commit)."""
        from unittest.mock import patch
        from core.governance.approvals import approve_request

        original_policy = risk_policy.to_dict()
        original_status = pending_request.status

        # Simulate crash after boundary check but before commit
        with patch('models.db.session.commit',
                   side_effect=Exception('Simulated crash')):
            try:
                approve_request(
                    request_id=pending_request.id,
                    workspace_id=user.id,
                    approver_id=user.id,
                    mode='one_time',
                )
            except Exception:
                pass

        # Rollback the failed transaction
        db.session.rollback()

        db.session.refresh(risk_policy)
        db.session.refresh(pending_request)

        assert risk_policy.to_dict() == original_policy
        assert pending_request.status == original_status

    def test_expired_delegation_attempt(self, app, user, agent, risk_policy,
                                         active_grant):
        """Using an expired grant returns a clear error and does not
        mutate the policy."""
        from core.governance.delegation import apply_delegated_change

        # Force-expire the grant
        active_grant.valid_to = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()

        original = risk_policy.to_dict()

        _, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '12.0000',
            },
        )

        assert error is not None
        assert 'expired' in error.lower()

        db.session.refresh(risk_policy)
        assert risk_policy.to_dict() == original

    def test_request_exceeding_global_cap(self, app, user, agent, risk_policy):
        """Requesting a value beyond the tier's global cap is allowed at
        request time (boundary check happens at approval)."""
        from core.governance.requests import create_request

        # Free tier cap is $50 — requesting $100
        pcr, error = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '100.0000',
            },
            reason='Exceed cap request',
        )

        # Request creation succeeds (boundary check is at approval time)
        assert error is None
        assert pcr.status == 'pending'

        # But approval is blocked
        from core.governance.approvals import approve_request
        _, approval_error = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )
        assert approval_error is not None
        assert 'Boundary violation' in approval_error

    def test_revoked_grant_cannot_be_used(self, app, user, agent, risk_policy,
                                           active_grant):
        """A revoked grant cannot be used to apply changes."""
        from core.governance.delegation import revoke_grant, apply_delegated_change

        revoke_grant(active_grant.id, user.id, user.id)

        _, error = apply_delegated_change(
            grant_id=active_grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '12.0000',
            },
        )
        assert error is not None
        assert 'no longer active' in error.lower()

    def test_double_approval_rejected(self, app, user, agent, risk_policy,
                                       pending_request):
        """Cannot approve a request that's already been applied."""
        from core.governance.approvals import approve_request

        # First approval
        approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )

        # Second approval
        _, error = approve_request(
            request_id=pending_request.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )
        assert error is not None
        assert 'already' in error.lower()

    def test_expired_request_cannot_be_approved(self, app, user, agent,
                                                  risk_policy):
        """An expired request cannot be approved."""
        from core.governance.requests import create_request, expire_stale_requests
        from core.governance.approvals import approve_request
        from models import PolicyChangeRequest

        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='Will expire',
        )

        # Force expire
        pcr.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()
        expire_stale_requests()

        db.session.refresh(pcr)
        assert pcr.status == 'expired'

        _, error = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )
        assert error is not None
        assert 'already expired' in error


# ---------------------------------------------------------------------------
# End-to-End Lifecycle Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestE2ELifecycle:

    def test_full_one_time_lifecycle(self, app, user, agent, risk_policy):
        """Agent request -> human approve one_time -> policy changed ->
        risk engine sees new value -> rollback -> policy restored."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request
        from core.governance.rollback import rollback_change
        from core.governance.governance_audit import get_governance_trail

        # 1. Agent requests threshold increase
        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '10.0000',
                'requested_value': '20.0000',
            },
            reason='Campaign needs higher cap',
        )
        assert pcr.status == 'pending'

        # Policy unchanged
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

        # 2. Human approves
        result, _ = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='one_time',
        )
        assert result['status'] == 'applied'

        # Policy changed
        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('20.0000')

        # 3. Risk engine would see the new value (we verify the DB state)
        from models import RiskPolicy
        policy = RiskPolicy.query.get(risk_policy.id)
        assert policy.threshold_value == Decimal('20.0000')

        # 4. Rollback
        entries = get_governance_trail(user.id, event_type='change_applied')
        rollback_change(entries[0].id, user.id, user.id)

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('10.0000')

        # 5. Verify complete audit trail exists
        trail = get_governance_trail(user.id)
        event_types = [e.event_type for e in trail]
        assert 'request_submitted' in event_types
        assert 'request_approved' in event_types
        assert 'change_applied' in event_types
        assert 'change_rolled_back' in event_types

    def test_full_delegation_lifecycle(self, app, user, agent, risk_policy):
        """Agent request -> human delegates -> agent self-applies ->
        grant expires -> agent can no longer apply."""
        from core.governance.requests import create_request
        from core.governance.approvals import approve_request
        from core.governance.delegation import (
            apply_delegated_change, expire_grants,
        )
        from models import DelegationGrant

        # 1. Agent requests
        pcr, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'current_value': '10.0000',
                'requested_value': '20.0000',
            },
            reason='Need delegation',
        )

        # 2. Human delegates for 60 minutes
        result, _ = approve_request(
            request_id=pcr.id,
            workspace_id=user.id,
            approver_id=user.id,
            mode='delegate',
            delegation_params={'duration_minutes': 60},
        )
        grant = DelegationGrant.query.get(result['grant_id'])
        assert grant.active is True

        # 3. Agent self-applies within envelope
        apply_result, _ = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '15.0000',
            },
        )
        assert apply_result is not None

        db.session.refresh(risk_policy)
        assert risk_policy.threshold_value == Decimal('15.0000')

        # 4. Grant expires
        grant.valid_to = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

        expired_count = expire_grants()
        assert expired_count == 1

        # 5. Agent can no longer apply
        _, error = apply_delegated_change(
            grant_id=grant.id,
            workspace_id=user.id,
            agent_id=agent.id,
            requested_change={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'new_value': '18.0000',
            },
        )
        assert error is not None
        assert 'no longer active' in error.lower()


# ---------------------------------------------------------------------------
# Phase 4 Module Exports
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPhase4Exports:

    def test_module_exports_phase4(self, app):
        import core.governance as gov

        assert hasattr(gov, 'rollback_change')
        assert callable(gov.rollback_change)
        assert 'rollback_change' in gov.__all__


# ===========================================================================
# Phase 5: Minimal Approval UI Hooks
# ===========================================================================


# ---------------------------------------------------------------------------
# Pending Requests Route Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPendingRequestsRoute:

    def test_unauthenticated_rejected(self, client, app):
        resp = client.get('/api/governance/pending')
        assert resp.status_code == 401

    def test_empty_pending(self, app, user, client):
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/pending')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 0
        assert data['requests'] == []

    def test_returns_only_pending(self, app, user, agent, risk_policy, client):
        """Pending endpoint only returns status=pending requests."""
        from core.governance.requests import create_request
        from core.governance.approvals import deny_request

        # Create a pending request
        pcr1, _ = create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='Pending request',
        )

        # Create and deny another request (need different policy or wait)
        from models import PolicyChangeRequest
        pcr2 = PolicyChangeRequest(
            workspace_id=user.id,
            agent_id=agent.id,
            policy_id=risk_policy.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '20.0000',
            },
            reason='Will be denied',
            status='denied',
            requested_at=datetime.utcnow() - timedelta(minutes=30),
        )
        db.session.add(pcr2)
        db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/pending')
        data = resp.get_json()
        assert data['count'] == 1
        assert data['requests'][0]['id'] == pcr1.id
        assert data['requests'][0]['status'] == 'pending'

    def test_filter_by_agent(self, app, user, agent, risk_policy,
                              other_user, other_agent, client):
        """Pending endpoint supports agent_id filter."""
        from core.governance.requests import create_request

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='From agent 1',
        )

        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        # Filter by this agent
        resp = client.get(f'/api/governance/pending?agent_id={agent.id}')
        data = resp.get_json()
        assert data['count'] == 1

        # Filter by other agent (belongs to other workspace, so 0 results)
        resp = client.get(f'/api/governance/pending?agent_id={other_agent.id}')
        data = resp.get_json()
        assert data['count'] == 0

    def test_workspace_isolation(self, app, user, agent, risk_policy,
                                  other_user, client):
        """Pending endpoint is workspace-scoped."""
        from core.governance.requests import create_request

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='User 1 request',
        )

        # Other user sees nothing
        with client.session_transaction() as sess:
            sess['user_id'] = other_user.id

        resp = client.get('/api/governance/pending')
        data = resp.get_json()
        assert data['count'] == 0

    def test_limit_parameter(self, app, user, agent, risk_policy, client):
        """Pending endpoint respects limit parameter."""
        from core.governance.requests import create_request

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='Request 1',
        )

        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/pending?limit=1')
        data = resp.get_json()
        assert data['count'] <= 1

    def test_pending_count_for_badge(self, app, user, agent, risk_policy,
                                      client):
        """Count field is usable for badge display."""
        from core.governance.requests import create_request

        create_request(
            workspace_id=user.id,
            agent_id=agent.id,
            requested_changes={
                'policy_id': risk_policy.id,
                'field': 'threshold_value',
                'requested_value': '15.0000',
            },
            reason='For badge count',
        )

        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        resp = client.get('/api/governance/pending')
        data = resp.get_json()
        assert isinstance(data['count'], int)
        assert data['count'] > 0


# ---------------------------------------------------------------------------
# Phase 5 Completeness Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPhase5Completeness:

    def test_all_ui_endpoints_exist(self, app, user, client):
        """All governance endpoints needed by the UI exist and require auth."""
        endpoints = [
            ('GET', '/api/governance/pending'),
            ('GET', '/api/governance/requests'),
            ('GET', '/api/governance/delegations'),
            ('GET', '/api/governance/audit'),
        ]

        for method, path in endpoints:
            if method == 'GET':
                resp = client.get(path)
            else:
                resp = client.post(path)
            # Should return 401 (not 404/405) — endpoint exists
            assert resp.status_code == 401, (
                f'{method} {path} returned {resp.status_code}, expected 401'
            )

    def test_action_endpoints_exist(self, app, user, client):
        """All governance action endpoints exist."""
        with client.session_transaction() as sess:
            sess['user_id'] = user.id

        # These should return 400 (bad input) not 404
        action_endpoints = [
            ('POST', '/api/governance/approve/1'),
            ('POST', '/api/governance/deny/1'),
            ('POST', '/api/governance/rollback/1'),
            ('POST', '/api/governance/delegations/1/revoke'),
        ]

        for method, path in action_endpoints:
            resp = client.post(path)
            assert resp.status_code != 404, (
                f'{method} {path} returned 404 — endpoint missing'
            )
            assert resp.status_code != 405, (
                f'{method} {path} returned 405 — method not allowed'
            )

    def test_governance_routes_registered(self, app):
        """Governance routes are registered on the app."""
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        expected = [
            '/api/governance/request',
            '/api/governance/requests',
            '/api/governance/pending',
            '/api/governance/approve/<int:request_id>',
            '/api/governance/deny/<int:request_id>',
            '/api/governance/delegate/apply',
            '/api/governance/delegations',
            '/api/governance/rollback/<int:audit_id>',
            '/api/governance/audit',
            '/api/governance/internal/expire',
        ]
        for route in expected:
            assert route in rules, f'Route {route} not registered'

    def test_full_api_surface_matches_architecture(self, app):
        """All endpoints from the architecture doc Section 7 are present."""
        rules = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}

        # Agent-facing
        assert '/api/governance/request' in rules
        assert 'POST' in rules['/api/governance/request']
        assert '/api/governance/requests' in rules
        assert 'GET' in rules['/api/governance/requests']

        # Human-facing
        assert '/api/governance/approve/<int:request_id>' in rules
        assert '/api/governance/deny/<int:request_id>' in rules
        assert '/api/governance/pending' in rules
        assert '/api/governance/delegations' in rules
        assert '/api/governance/audit' in rules
        assert '/api/governance/rollback/<int:audit_id>' in rules

        # Internal/Cron
        assert '/api/governance/internal/expire' in rules
