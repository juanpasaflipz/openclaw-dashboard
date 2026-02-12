"""
Phase 1 tests: WorkspaceTier model, tier enforcement middleware, limit checks.

Verifies:
- Missing tier row defaults to free
- Tier lookup and caching
- Agent limit enforcement
- Alert rule limit enforcement
- API key limit enforcement
- Retention cutoff calculation
- Health history cutoff calculation
- Feature flag checks (anomaly, slack)
- Batch size per tier
- Tier seed data correctness
- Tier update dynamically changes limits
"""
import pytest
from datetime import datetime, date, timedelta
from models import (
    db, User, Agent, WorkspaceTier, ObsEvent, ObsAlertRule, ObsApiKey,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def free_user(app):
    """User with no WorkspaceTier row (defaults to free)."""
    u = User(email='free@test.com', created_at=datetime.utcnow())
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def production_user(app):
    """User with production tier."""
    u = User(email='prod@test.com', created_at=datetime.utcnow())
    db.session.add(u)
    db.session.flush()
    tier = WorkspaceTier(workspace_id=u.id, tier_name='production',
                         **WorkspaceTier.TIER_DEFAULTS['production'])
    db.session.add(tier)
    db.session.commit()
    return u


@pytest.fixture
def pro_user(app):
    """User with pro tier."""
    u = User(email='pro@test.com', created_at=datetime.utcnow())
    db.session.add(u)
    db.session.flush()
    tier = WorkspaceTier(workspace_id=u.id, tier_name='pro',
                         **WorkspaceTier.TIER_DEFAULTS['pro'])
    db.session.add(tier)
    db.session.commit()
    return u


@pytest.fixture
def agency_user(app):
    """User with agency tier."""
    u = User(email='agency@test.com', created_at=datetime.utcnow())
    db.session.add(u)
    db.session.flush()
    tier = WorkspaceTier(workspace_id=u.id, tier_name='agency',
                         **WorkspaceTier.TIER_DEFAULTS['agency'])
    db.session.add(tier)
    db.session.commit()
    return u


@pytest.fixture(autouse=True)
def clear_tier_cache():
    """Clear tier cache before each test."""
    from core.observability.tier_enforcement import invalidate_tier_cache
    invalidate_tier_cache()
    yield
    invalidate_tier_cache()


# ---------------------------------------------------------------------------
# TIER MODEL TESTS
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestWorkspaceTierModel:
    """Verify WorkspaceTier model and TIER_DEFAULTS."""

    def test_tier_defaults_has_all_tiers(self, app):
        assert set(WorkspaceTier.TIER_DEFAULTS.keys()) == {
            'free', 'production', 'pro', 'agency'
        }

    def test_free_defaults(self, app):
        d = WorkspaceTier.TIER_DEFAULTS['free']
        assert d['agent_limit'] == 2
        assert d['retention_days'] == 7
        assert d['alert_rule_limit'] == 0
        assert d['health_history_days'] == 0
        assert d['anomaly_detection_enabled'] is False
        assert d['slack_notifications_enabled'] is False
        assert d['max_batch_size'] == 100

    def test_production_defaults(self, app):
        d = WorkspaceTier.TIER_DEFAULTS['production']
        assert d['agent_limit'] == 10
        assert d['retention_days'] == 30
        assert d['alert_rule_limit'] == 3
        assert d['health_history_days'] == 7
        assert d['slack_notifications_enabled'] is True

    def test_pro_defaults(self, app):
        d = WorkspaceTier.TIER_DEFAULTS['pro']
        assert d['agent_limit'] == 50
        assert d['retention_days'] == 90
        assert d['alert_rule_limit'] == 9999
        assert d['anomaly_detection_enabled'] is True

    def test_agency_defaults(self, app):
        d = WorkspaceTier.TIER_DEFAULTS['agency']
        assert d['agent_limit'] == 9999
        assert d['retention_days'] == 180
        assert d['multi_workspace_enabled'] is True
        assert d['priority_processing'] is True

    def test_tier_persisted_and_readable(self, app, production_user):
        row = WorkspaceTier.query.filter_by(workspace_id=production_user.id).first()
        assert row is not None
        assert row.tier_name == 'production'
        assert row.agent_limit == 10
        d = row.to_dict()
        assert d['tier_name'] == 'production'
        assert d['workspace_id'] == production_user.id

    def test_user_backref(self, app, production_user):
        """WorkspaceTier is accessible via user.workspace_tier."""
        u = User.query.get(production_user.id)
        assert u.workspace_tier is not None
        assert u.workspace_tier.tier_name == 'production'


# ---------------------------------------------------------------------------
# TIER LOOKUP & CACHING
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestTierLookup:
    """Verify get_workspace_tier with and without DB rows."""

    def test_missing_row_returns_free(self, app, free_user):
        from core.observability.tier_enforcement import get_workspace_tier
        tier = get_workspace_tier(free_user.id)
        assert tier['tier_name'] == 'free'
        assert tier['agent_limit'] == 2
        assert tier['retention_days'] == 7

    def test_existing_row_returned(self, app, pro_user):
        from core.observability.tier_enforcement import get_workspace_tier
        tier = get_workspace_tier(pro_user.id)
        assert tier['tier_name'] == 'pro'
        assert tier['agent_limit'] == 50

    def test_cache_returns_same_object(self, app, production_user):
        from core.observability.tier_enforcement import get_workspace_tier
        t1 = get_workspace_tier(production_user.id)
        t2 = get_workspace_tier(production_user.id)
        assert t1 is t2  # Same dict instance from cache

    def test_cache_invalidation(self, app, production_user):
        from core.observability.tier_enforcement import (
            get_workspace_tier, invalidate_tier_cache,
        )
        t1 = get_workspace_tier(production_user.id)
        assert t1['tier_name'] == 'production'

        # Upgrade in DB
        row = WorkspaceTier.query.filter_by(workspace_id=production_user.id).first()
        row.tier_name = 'pro'
        row.agent_limit = 50
        db.session.commit()

        # Cache still returns old value
        t2 = get_workspace_tier(production_user.id)
        assert t2['tier_name'] == 'production'

        # After invalidation, returns new value
        invalidate_tier_cache(production_user.id)
        t3 = get_workspace_tier(production_user.id)
        assert t3['tier_name'] == 'pro'
        assert t3['agent_limit'] == 50


# ---------------------------------------------------------------------------
# AGENT LIMIT ENFORCEMENT
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestAgentLimitEnforcement:
    """Verify agent monitoring limits per tier."""

    def _add_agent_event(self, user_id, agent_id):
        evt = ObsEvent(
            uid=f'evt-{user_id}-{agent_id}',
            user_id=user_id,
            agent_id=agent_id,
            event_type='heartbeat',
            status='info',
            created_at=datetime.utcnow(),
        )
        db.session.add(evt)
        db.session.commit()

    def test_free_allows_two_agents(self, app, free_user, agent):
        from core.observability.tier_enforcement import check_agent_limit
        # 0 agents monitored
        ok, msg = check_agent_limit(free_user.id)
        assert ok is True

    def test_free_blocks_third_agent(self, app, free_user):
        from core.observability.tier_enforcement import check_agent_limit
        # Create 2 agents and events
        a1 = Agent(user_id=free_user.id, name='A1', is_active=True, created_at=datetime.utcnow())
        a2 = Agent(user_id=free_user.id, name='A2', is_active=True, created_at=datetime.utcnow())
        db.session.add_all([a1, a2])
        db.session.flush()
        self._add_agent_event(free_user.id, a1.id)
        self._add_agent_event(free_user.id, a2.id)

        ok, msg = check_agent_limit(free_user.id)
        assert ok is False
        assert 'limit reached' in msg.lower()
        assert 'free' in msg.lower()

    def test_production_allows_ten_agents(self, app, production_user):
        from core.observability.tier_enforcement import check_agent_limit
        # Create 9 agents with events
        for i in range(9):
            a = Agent(user_id=production_user.id, name=f'A{i}', is_active=True,
                      created_at=datetime.utcnow())
            db.session.add(a)
            db.session.flush()
            self._add_agent_event(production_user.id, a.id)

        ok, msg = check_agent_limit(production_user.id)
        assert ok is True  # 9 < 10

    def test_check_agent_allowed_existing(self, app, free_user):
        """An agent that already has events is always allowed."""
        from core.observability.tier_enforcement import check_agent_allowed
        a1 = Agent(user_id=free_user.id, name='A1', is_active=True, created_at=datetime.utcnow())
        a2 = Agent(user_id=free_user.id, name='A2', is_active=True, created_at=datetime.utcnow())
        db.session.add_all([a1, a2])
        db.session.flush()
        self._add_agent_event(free_user.id, a1.id)
        self._add_agent_event(free_user.id, a2.id)

        # Both already known — allowed even though limit is 2
        ok, _ = check_agent_allowed(free_user.id, a1.id)
        assert ok is True
        ok, _ = check_agent_allowed(free_user.id, a2.id)
        assert ok is True

    def test_check_agent_allowed_new_blocked(self, app, free_user):
        """A new agent is blocked when at limit."""
        from core.observability.tier_enforcement import check_agent_allowed
        a1 = Agent(user_id=free_user.id, name='A1', is_active=True, created_at=datetime.utcnow())
        a2 = Agent(user_id=free_user.id, name='A2', is_active=True, created_at=datetime.utcnow())
        a3 = Agent(user_id=free_user.id, name='A3', is_active=True, created_at=datetime.utcnow())
        db.session.add_all([a1, a2, a3])
        db.session.flush()
        self._add_agent_event(free_user.id, a1.id)
        self._add_agent_event(free_user.id, a2.id)

        # a3 is new and limit is 2
        ok, msg = check_agent_allowed(free_user.id, a3.id)
        assert ok is False


# ---------------------------------------------------------------------------
# ALERT RULE LIMIT ENFORCEMENT
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestAlertRuleLimitEnforcement:
    """Verify alert rule limits per tier."""

    def test_free_cannot_create_rules(self, app, free_user):
        from core.observability.tier_enforcement import check_alert_rule_limit
        ok, msg = check_alert_rule_limit(free_user.id)
        assert ok is False
        assert 'not available' in msg.lower()
        assert 'free' in msg.lower()

    def test_production_allows_three_rules(self, app, production_user):
        from core.observability.tier_enforcement import check_alert_rule_limit
        # Create 2 rules
        for i in range(2):
            rule = ObsAlertRule(
                user_id=production_user.id, name=f'Rule {i}',
                rule_type='cost_per_day', threshold=10.0,
            )
            db.session.add(rule)
        db.session.commit()

        ok, _ = check_alert_rule_limit(production_user.id)
        assert ok is True  # 2 < 3

    def test_production_blocks_fourth_rule(self, app, production_user):
        from core.observability.tier_enforcement import check_alert_rule_limit
        for i in range(3):
            rule = ObsAlertRule(
                user_id=production_user.id, name=f'Rule {i}',
                rule_type='cost_per_day', threshold=10.0,
            )
            db.session.add(rule)
        db.session.commit()

        ok, msg = check_alert_rule_limit(production_user.id)
        assert ok is False
        assert 'limit reached' in msg.lower()

    def test_pro_unlimited_rules(self, app, pro_user):
        from core.observability.tier_enforcement import check_alert_rule_limit
        # Create 100 rules
        for i in range(100):
            rule = ObsAlertRule(
                user_id=pro_user.id, name=f'Rule {i}',
                rule_type='error_rate', threshold=50.0,
            )
            db.session.add(rule)
        db.session.commit()

        ok, _ = check_alert_rule_limit(pro_user.id)
        assert ok is True  # 100 < 9999


# ---------------------------------------------------------------------------
# RETENTION & DATE CLAMPING
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestRetentionEnforcement:
    """Verify retention cutoff and date range clamping."""

    def test_free_retention_7_days(self, app, free_user):
        from core.observability.tier_enforcement import get_retention_cutoff
        cutoff = get_retention_cutoff(free_user.id)
        expected = datetime.utcnow() - timedelta(days=7)
        # Within 1 second tolerance
        assert abs((cutoff - expected).total_seconds()) < 1

    def test_production_retention_30_days(self, app, production_user):
        from core.observability.tier_enforcement import get_retention_cutoff
        cutoff = get_retention_cutoff(production_user.id)
        expected = datetime.utcnow() - timedelta(days=30)
        assert abs((cutoff - expected).total_seconds()) < 1

    def test_clamp_date_range_free(self, app, free_user):
        from core.observability.tier_enforcement import clamp_date_range
        # Request 30 days of data on free tier
        from_date = date.today() - timedelta(days=30)
        to_date = date.today()
        clamped_from, clamped_to = clamp_date_range(free_user.id, from_date, to_date)
        # Should be clamped to 7 days
        cutoff = (datetime.utcnow() - timedelta(days=7)).date()
        assert clamped_from == cutoff
        assert clamped_to == to_date

    def test_clamp_date_range_within_window(self, app, production_user):
        from core.observability.tier_enforcement import clamp_date_range
        # Request 5 days on production tier (30d window) — no clamping
        from_date = date.today() - timedelta(days=5)
        to_date = date.today()
        clamped_from, clamped_to = clamp_date_range(production_user.id, from_date, to_date)
        assert clamped_from == from_date
        assert clamped_to == to_date

    def test_clamp_date_range_none_defaults(self, app, free_user):
        from core.observability.tier_enforcement import clamp_date_range
        clamped_from, clamped_to = clamp_date_range(free_user.id, None, None)
        today_utc = datetime.utcnow().date()
        cutoff = (datetime.utcnow() - timedelta(days=7)).date()
        assert clamped_from == cutoff
        assert clamped_to == today_utc


# ---------------------------------------------------------------------------
# HEALTH HISTORY CUTOFF
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestHealthHistoryCutoff:
    """Verify health history depth limits per tier."""

    def test_free_today_only(self, app, free_user):
        from core.observability.tier_enforcement import get_health_history_cutoff
        cutoff = get_health_history_cutoff(free_user.id)
        today_utc = datetime.utcnow().date()
        assert cutoff == today_utc

    def test_production_7_days(self, app, production_user):
        from core.observability.tier_enforcement import get_health_history_cutoff
        cutoff = get_health_history_cutoff(production_user.id)
        expected = (datetime.utcnow() - timedelta(days=7)).date()
        assert cutoff == expected

    def test_pro_30_days(self, app, pro_user):
        from core.observability.tier_enforcement import get_health_history_cutoff
        cutoff = get_health_history_cutoff(pro_user.id)
        expected = (datetime.utcnow() - timedelta(days=30)).date()
        assert cutoff == expected


# ---------------------------------------------------------------------------
# FEATURE FLAG CHECKS
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestFeatureFlags:
    """Verify boolean feature gates."""

    def test_anomaly_detection_free_disabled(self, app, free_user):
        from core.observability.tier_enforcement import check_anomaly_detection
        assert check_anomaly_detection(free_user.id) is False

    def test_anomaly_detection_pro_enabled(self, app, pro_user):
        from core.observability.tier_enforcement import check_anomaly_detection
        assert check_anomaly_detection(pro_user.id) is True

    def test_slack_free_disabled(self, app, free_user):
        from core.observability.tier_enforcement import check_slack_notifications
        assert check_slack_notifications(free_user.id) is False

    def test_slack_production_enabled(self, app, production_user):
        from core.observability.tier_enforcement import check_slack_notifications
        assert check_slack_notifications(production_user.id) is True

    def test_batch_size_free(self, app, free_user):
        from core.observability.tier_enforcement import get_max_batch_size
        assert get_max_batch_size(free_user.id) == 100

    def test_batch_size_pro(self, app, pro_user):
        from core.observability.tier_enforcement import get_max_batch_size
        assert get_max_batch_size(pro_user.id) == 1000


# ---------------------------------------------------------------------------
# API KEY LIMIT
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestApiKeyLimit:
    """Verify API key creation limits per tier."""

    def test_free_allows_one_key(self, app, free_user):
        from core.observability.tier_enforcement import check_api_key_limit
        ok, _ = check_api_key_limit(free_user.id)
        assert ok is True

    def test_free_blocks_second_key(self, app, free_user):
        from core.observability.tier_enforcement import check_api_key_limit
        ObsApiKey.create_for_user(free_user.id, name='key1')
        db.session.commit()

        ok, msg = check_api_key_limit(free_user.id)
        assert ok is False
        assert 'limit reached' in msg.lower()

    def test_production_allows_three_keys(self, app, production_user):
        from core.observability.tier_enforcement import check_api_key_limit
        for i in range(2):
            ObsApiKey.create_for_user(production_user.id, name=f'key{i}')
        db.session.commit()

        ok, _ = check_api_key_limit(production_user.id)
        assert ok is True  # 2 < 3


# ---------------------------------------------------------------------------
# VERIFY_WORKSPACE_LIMITS (composite check)
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestVerifyWorkspaceLimits:
    """Verify the composite limit checker."""

    def test_all_checks_pass_for_pro(self, app, pro_user):
        from core.observability.tier_enforcement import verify_workspace_limits
        ok, msg = verify_workspace_limits(pro_user.id, check='all')
        assert ok is True
        assert msg is None

    def test_specific_check_agent(self, app, free_user):
        from core.observability.tier_enforcement import verify_workspace_limits
        ok, msg = verify_workspace_limits(free_user.id, check='agent')
        assert ok is True  # No agents monitored yet

    def test_specific_check_alert_rule_free(self, app, free_user):
        from core.observability.tier_enforcement import verify_workspace_limits
        ok, msg = verify_workspace_limits(free_user.id, check='alert_rule')
        assert ok is False  # Free tier: 0 alert rules allowed

    def test_agent_id_int_check(self, app, free_user):
        """Passing an int as check treats it as agent_id."""
        from core.observability.tier_enforcement import verify_workspace_limits
        a = Agent(user_id=free_user.id, name='A1', is_active=True,
                  created_at=datetime.utcnow())
        db.session.add(a)
        db.session.flush()

        # New agent, under limit (0 monitored, limit 2)
        ok, _ = verify_workspace_limits(free_user.id, check=a.id)
        assert ok is True


# ---------------------------------------------------------------------------
# TIER UPGRADE DYNAMICS
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestTierUpgrade:
    """Verify that tier changes dynamically affect limits."""

    def test_upgrade_free_to_production(self, app, free_user):
        from core.observability.tier_enforcement import (
            get_workspace_tier, check_alert_rule_limit, invalidate_tier_cache,
        )

        # Free tier: no alerts
        ok, _ = check_alert_rule_limit(free_user.id)
        assert ok is False

        # Upgrade
        tier = WorkspaceTier(workspace_id=free_user.id, tier_name='production',
                             **WorkspaceTier.TIER_DEFAULTS['production'])
        db.session.add(tier)
        db.session.commit()
        invalidate_tier_cache(free_user.id)

        # Now alerts allowed
        ok, _ = check_alert_rule_limit(free_user.id)
        assert ok is True

        t = get_workspace_tier(free_user.id)
        assert t['tier_name'] == 'production'
        assert t['alert_rule_limit'] == 3


# ---------------------------------------------------------------------------
# RETENTION CLEANUP
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestRetentionCleanup:
    """Verify the background retention cleanup job."""

    def _create_event(self, user_id, agent_id, created_at, uid_suffix):
        evt = ObsEvent(
            uid=f'evt-{user_id}-{uid_suffix}',
            user_id=user_id,
            agent_id=agent_id,
            event_type='llm_call',
            status='success',
            created_at=created_at,
        )
        db.session.add(evt)
        return evt

    def test_cleanup_deletes_expired_events(self, app, free_user):
        """Free tier (7d retention + 24h grace). Events older than 8 days are deleted."""
        from core.observability.retention import cleanup_expired_events
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        now = datetime.utcnow()
        # Create events: 1 within window, 1 outside
        self._create_event(free_user.id, None, now - timedelta(days=3), 'recent')
        self._create_event(free_user.id, None, now - timedelta(days=10), 'old')
        db.session.commit()

        assert ObsEvent.query.filter_by(user_id=free_user.id).count() == 2

        results = cleanup_expired_events()

        remaining = ObsEvent.query.filter_by(user_id=free_user.id).all()
        assert len(remaining) == 1
        assert remaining[0].uid.endswith('recent')

        assert free_user.id in results
        assert results[free_user.id]['events_deleted'] == 1

    def test_cleanup_preserves_events_within_window(self, app, production_user):
        """Production tier (30d). Events within 30d + 24h are preserved."""
        from core.observability.retention import cleanup_expired_events
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        now = datetime.utcnow()
        self._create_event(production_user.id, None, now - timedelta(days=5), 'day5')
        self._create_event(production_user.id, None, now - timedelta(days=25), 'day25')
        self._create_event(production_user.id, None, now - timedelta(days=29), 'day29')
        db.session.commit()

        results = cleanup_expired_events()

        remaining = ObsEvent.query.filter_by(user_id=production_user.id).count()
        # All within 30d + 24h grace = 31d cutoff
        assert remaining == 3
        assert production_user.id not in results  # Nothing deleted

    def test_cleanup_respects_per_workspace_retention(self, app, free_user, pro_user):
        """Different workspaces have different retention windows."""
        from core.observability.retention import cleanup_expired_events
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        now = datetime.utcnow()
        # Free user: 15-day-old event (past 7d + 24h = 8d cutoff)
        self._create_event(free_user.id, None, now - timedelta(days=15), 'free-old')
        # Pro user: 15-day-old event (within 90d + 24h cutoff)
        self._create_event(pro_user.id, None, now - timedelta(days=15), 'pro-ok')
        db.session.commit()

        cleanup_expired_events()

        free_count = ObsEvent.query.filter_by(user_id=free_user.id).count()
        pro_count = ObsEvent.query.filter_by(user_id=pro_user.id).count()
        assert free_count == 0  # Deleted (past 8d cutoff)
        assert pro_count == 1   # Preserved (within 91d cutoff)

    def test_cleanup_also_deletes_runs(self, app, free_user):
        """Cleanup should also delete expired ObsRun records."""
        from core.observability.retention import cleanup_expired_events
        from core.observability.tier_enforcement import invalidate_tier_cache
        from models import ObsRun
        invalidate_tier_cache()

        now = datetime.utcnow()
        self._create_event(free_user.id, None, now - timedelta(days=10), 'old-evt')
        run = ObsRun(
            run_id='run-old-001',
            user_id=free_user.id,
            status='success',
            started_at=now - timedelta(days=10),
        )
        db.session.add(run)
        db.session.commit()

        results = cleanup_expired_events()

        assert ObsRun.query.filter_by(user_id=free_user.id).count() == 0
        assert results[free_user.id]['runs_deleted'] == 1

    def test_retention_stats(self, app, free_user):
        """get_retention_stats returns correct info."""
        from core.observability.retention import get_retention_stats
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        now = datetime.utcnow()
        self._create_event(free_user.id, None, now - timedelta(days=1), 'r1')
        self._create_event(free_user.id, None, now - timedelta(days=10), 'r2')
        db.session.commit()

        stats = get_retention_stats(free_user.id)
        assert stats['tier_name'] == 'free'
        assert stats['retention_days'] == 7
        assert stats['total_events'] == 2
        assert stats['expired_events'] == 1  # 10-day-old event past 8d cutoff


# ---------------------------------------------------------------------------
# RETENTION FILTER IN ROUTES (integration)
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestRetentionFilterRoutes:
    """Verify that route endpoints respect retention windows."""

    def _create_event(self, user_id, agent_id, created_at, uid_suffix):
        evt = ObsEvent(
            uid=f'evt-route-{user_id}-{uid_suffix}',
            user_id=user_id,
            agent_id=agent_id,
            event_type='llm_call',
            status='success',
            created_at=created_at,
        )
        db.session.add(evt)
        return evt

    def test_events_endpoint_filters_by_retention(self, app, free_user):
        """GET /api/obs/events only returns events within retention window."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        now = datetime.utcnow()
        self._create_event(free_user.id, None, now - timedelta(days=2), 'recent')
        self._create_event(free_user.id, None, now - timedelta(days=10), 'old')
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = free_user.id

        resp = client.get('/api/obs/events')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['total'] == 1
        assert data['events'][0]['id'].endswith('recent')

    def test_overview_includes_tier_info(self, app, free_user):
        """GET /api/obs/metrics/overview returns tier metadata."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = free_user.id

        resp = client.get('/api/obs/metrics/overview')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier']['name'] == 'free'
        assert data['tier']['retention_days'] == 7

    def test_cron_retention_cleanup_endpoint(self, app, free_user):
        """POST /api/obs/internal/retention-cleanup works with cron auth."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        now = datetime.utcnow()
        self._create_event(free_user.id, None, now - timedelta(days=10), 'cron-old')
        db.session.commit()

        client = app.test_client()
        resp = client.post('/api/obs/internal/retention-cleanup',
                           json={'password': 'test'},
                           headers={'Authorization': 'Bearer test'})
        # Without valid cron secret, should be 401
        assert resp.status_code == 401

        # Set env and retry
        import os
        os.environ['ADMIN_PASSWORD'] = 'test-admin-pw'
        resp = client.post('/api/obs/internal/retention-cleanup',
                           json={'password': 'test-admin-pw'})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['total_events_deleted'] == 1
        os.environ.pop('ADMIN_PASSWORD', None)


# ===========================================================================
# PHASE 3: FEATURE GATING — Route-level enforcement tests
# ===========================================================================

@pytest.mark.observability
class TestAlertRuleGating:
    """Verify alert rule creation is gated by tier via the API."""

    def test_free_tier_cannot_create_alert_rule(self, app, free_user):
        """Free tier: 0 alert rules allowed. POST should return 403."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = free_user.id

        resp = client.post('/api/obs/alerts/rules', json={
            'name': 'Cost Alert',
            'rule_type': 'cost_per_day',
            'threshold': 10.0,
        })
        assert resp.status_code == 403
        data = resp.get_json()
        assert data['upgrade_required'] is True
        assert 'not available' in data['error'].lower()

    def test_production_tier_allows_three_rules(self, app, production_user):
        """Production tier: create 3 rules, block 4th."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = production_user.id

        for i in range(3):
            resp = client.post('/api/obs/alerts/rules', json={
                'name': f'Rule {i}',
                'rule_type': 'cost_per_day',
                'threshold': 10.0,
            })
            assert resp.status_code == 201

        # 4th rule should be blocked
        resp = client.post('/api/obs/alerts/rules', json={
            'name': 'Rule 3',
            'rule_type': 'cost_per_day',
            'threshold': 10.0,
        })
        assert resp.status_code == 403
        assert resp.get_json()['upgrade_required'] is True

    def test_pro_tier_unlimited_rules(self, app, pro_user):
        """Pro tier: should allow many rules."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = pro_user.id

        for i in range(5):
            resp = client.post('/api/obs/alerts/rules', json={
                'name': f'Rule {i}',
                'rule_type': 'error_rate',
                'threshold': 50.0,
            })
            assert resp.status_code == 201


@pytest.mark.observability
class TestApiKeyGating:
    """Verify API key creation is gated by tier via the API."""

    def test_free_tier_blocks_second_key(self, app, free_user):
        """Free tier: 1 API key. Second creation should return 403."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = free_user.id

        # First key OK
        resp = client.post('/api/obs/api-keys', json={'name': 'key1'})
        assert resp.status_code == 201

        # Second key blocked
        resp = client.post('/api/obs/api-keys', json={'name': 'key2'})
        assert resp.status_code == 403
        assert resp.get_json()['upgrade_required'] is True

    def test_production_tier_allows_three_keys(self, app, production_user):
        """Production tier: 3 API keys allowed."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = production_user.id

        for i in range(3):
            resp = client.post('/api/obs/api-keys', json={'name': f'key{i}'})
            assert resp.status_code == 201

        # 4th key blocked
        resp = client.post('/api/obs/api-keys', json={'name': 'key3'})
        assert resp.status_code == 403


@pytest.mark.observability
class TestIngestionGating:
    """Verify ingestion endpoints enforce agent and batch limits."""

    def test_batch_size_enforced(self, app, free_user):
        """Free tier: max 100 events per batch."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        # Create an API key
        api_key, raw_key = ObsApiKey.create_for_user(free_user.id, name='test')
        db.session.commit()

        client = app.test_client()
        events = [{'event_type': 'llm_call'} for _ in range(101)]
        resp = client.post('/api/obs/ingest/events',
                           json={'events': events},
                           headers={'Authorization': f'Bearer {raw_key}'})
        assert resp.status_code == 403
        assert 'batch size' in resp.get_json()['error'].lower()

    def test_agent_limit_on_ingestion(self, app, free_user):
        """Free tier: 2 monitored agents. 3rd agent's events rejected."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        # Create 3 agents
        agents = []
        for i in range(3):
            a = Agent(user_id=free_user.id, name=f'Agent{i}', is_active=True,
                      created_at=datetime.utcnow())
            db.session.add(a)
            agents.append(a)
        db.session.flush()

        # Create API key
        api_key, raw_key = ObsApiKey.create_for_user(free_user.id, name='test')
        db.session.commit()

        client = app.test_client()
        headers = {'Authorization': f'Bearer {raw_key}'}

        # Ingest for agent 0 and 1 — should succeed
        for a in agents[:2]:
            resp = client.post('/api/obs/ingest/events', json={
                'event_type': 'heartbeat',
                'agent_id': a.id,
            }, headers=headers)
            assert resp.status_code == 200
            assert resp.get_json()['accepted'] == 1

        # Ingest for agent 2 — should be rejected (in the rejected list)
        resp = client.post('/api/obs/ingest/events', json={
            'event_type': 'heartbeat',
            'agent_id': agents[2].id,
        }, headers=headers)
        data = resp.get_json()
        assert data['accepted'] == 0
        assert len(data['rejected']) == 1
        assert 'limit' in data['rejected'][0]['reason'].lower()

    def test_heartbeat_agent_limit(self, app, free_user):
        """Free tier: heartbeat for 3rd agent blocked with 403."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        agents = []
        for i in range(3):
            a = Agent(user_id=free_user.id, name=f'HB{i}', is_active=True,
                      created_at=datetime.utcnow())
            db.session.add(a)
            agents.append(a)
        db.session.flush()

        api_key, raw_key = ObsApiKey.create_for_user(free_user.id, name='test')
        db.session.commit()

        client = app.test_client()
        headers = {'Authorization': f'Bearer {raw_key}'}

        # Heartbeats for first 2 agents
        for a in agents[:2]:
            resp = client.post('/api/obs/ingest/heartbeat',
                               json={'agent_id': a.id},
                               headers=headers)
            assert resp.status_code == 200

        # 3rd agent heartbeat blocked
        resp = client.post('/api/obs/ingest/heartbeat',
                           json={'agent_id': agents[2].id},
                           headers=headers)
        assert resp.status_code == 403
        assert resp.get_json()['upgrade_required'] is True


@pytest.mark.observability
class TestAnomalyDetectionGating:
    """Verify anomaly detection is hidden for non-Pro tiers."""

    def test_health_overview_hides_anomaly_for_free(self, app, free_user):
        """Free tier: health overview should not include cost_anomaly in breakdown."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        from models import ObsAgentHealthDaily
        invalidate_tier_cache()

        a = Agent(user_id=free_user.id, name='HA1', is_active=True,
                  created_at=datetime.utcnow())
        db.session.add(a)
        db.session.flush()

        today = datetime.utcnow().date()
        health = ObsAgentHealthDaily(
            user_id=free_user.id, agent_id=a.id, date=today,
            score=85.0, success_rate_score=38.0, latency_score=22.0,
            error_burst_score=18.0, cost_anomaly_score=7.0,
            details={},
        )
        db.session.add(health)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = free_user.id

        resp = client.get('/api/obs/health/overview')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['anomaly_detection_enabled'] is False
        assert len(data['health']) == 1
        assert 'cost_anomaly' not in data['health'][0]['breakdown']

    def test_health_overview_shows_anomaly_for_pro(self, app, pro_user):
        """Pro tier: health overview should include cost_anomaly."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        from models import ObsAgentHealthDaily
        invalidate_tier_cache()

        a = Agent(user_id=pro_user.id, name='HA2', is_active=True,
                  created_at=datetime.utcnow())
        db.session.add(a)
        db.session.flush()

        today = datetime.utcnow().date()
        health = ObsAgentHealthDaily(
            user_id=pro_user.id, agent_id=a.id, date=today,
            score=85.0, success_rate_score=38.0, latency_score=22.0,
            error_burst_score=18.0, cost_anomaly_score=7.0,
            details={},
        )
        db.session.add(health)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = pro_user.id

        resp = client.get('/api/obs/health/overview')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['anomaly_detection_enabled'] is True
        assert 'cost_anomaly' in data['health'][0]['breakdown']

    def test_agent_health_hides_anomaly_for_free(self, app, free_user):
        """Free tier: agent health endpoint hides anomaly breakdown."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        from models import ObsAgentHealthDaily
        invalidate_tier_cache()

        a = Agent(user_id=free_user.id, name='HA3', is_active=True,
                  created_at=datetime.utcnow())
        db.session.add(a)
        db.session.flush()

        today = datetime.utcnow().date()
        health = ObsAgentHealthDaily(
            user_id=free_user.id, agent_id=a.id, date=today,
            score=85.0, success_rate_score=38.0, latency_score=22.0,
            error_burst_score=18.0, cost_anomaly_score=7.0,
            details={},
        )
        db.session.add(health)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = free_user.id

        resp = client.get(f'/api/obs/health/agent/{a.id}')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['anomaly_detection_enabled'] is False
        assert len(data['scores']) == 1
        assert 'cost_anomaly' not in data['scores'][0]['breakdown']


@pytest.mark.observability
class TestSlackNotificationGating:
    """Verify Slack notifications are gated by tier."""

    def test_slack_not_dispatched_for_free_tier(self, app, free_user):
        """Free tier: alert fires but Slack is not called."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        from core.observability.alert_engine import _fire_alert
        from models import ObsAlertEvent
        from unittest.mock import patch
        invalidate_tier_cache()

        rule = ObsAlertRule(
            user_id=free_user.id, name='Test', rule_type='cost_per_day',
            threshold=5.0,
        )
        db.session.add(rule)
        db.session.commit()

        with patch('core.observability.alert_engine.dispatch_alert_notification') as mock_dispatch:
            _fire_alert(rule, 10.0, 5.0, datetime.utcnow())
            mock_dispatch.assert_not_called()

        # Alert event should still be created
        ae = ObsAlertEvent.query.filter_by(user_id=free_user.id).first()
        assert ae is not None
        assert ae.notified_slack is False

    def test_slack_dispatched_for_production_tier(self, app, production_user):
        """Production tier: alert fires and Slack IS called."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        from core.observability.alert_engine import _fire_alert
        from unittest.mock import patch
        invalidate_tier_cache()

        rule = ObsAlertRule(
            user_id=production_user.id, name='Test', rule_type='cost_per_day',
            threshold=5.0,
        )
        db.session.add(rule)
        db.session.commit()

        with patch('core.observability.alert_engine.dispatch_alert_notification') as mock_dispatch:
            mock_dispatch.return_value = {'slack': True}
            _fire_alert(rule, 10.0, 5.0, datetime.utcnow())
            mock_dispatch.assert_called_once()


# ===========================================================================
# PHASE 4: BILLING READINESS — Admin tier management + webhook stub
# ===========================================================================

@pytest.fixture
def admin_user_ph4(app):
    """Admin user for Phase 4 tests (separate from conftest admin to avoid conflicts)."""
    u = User(email='admin-ph4@test.com', created_at=datetime.utcnow(), is_admin=True)
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def target_user(app):
    """Non-admin user to be managed by admin."""
    u = User(email='target@test.com', created_at=datetime.utcnow())
    db.session.add(u)
    db.session.commit()
    return u


@pytest.mark.observability
class TestGetTierEndpoint:
    """Verify GET /api/obs/tier returns current tier for authenticated user."""

    def test_returns_free_when_no_tier_row(self, app, free_user):
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = free_user.id

        resp = client.get('/api/obs/tier')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier']['tier_name'] == 'free'
        assert data['tier']['retention_days'] == 7

    def test_returns_production_tier(self, app, production_user):
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = production_user.id

        resp = client.get('/api/obs/tier')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier']['tier_name'] == 'production'

    def test_requires_auth(self, app):
        client = app.test_client()
        resp = client.get('/api/obs/tier')
        assert resp.status_code == 401


@pytest.mark.observability
class TestAdminTierUpdate:
    """Verify POST /api/obs/admin/tier for admin tier management."""

    def test_non_admin_rejected(self, app, free_user, target_user):
        """Non-admin users get 403."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = free_user.id

        resp = client.post('/api/obs/admin/tier', json={
            'workspace_id': target_user.id,
            'tier_name': 'pro',
        })
        assert resp.status_code == 403

    def test_admin_can_set_tier(self, app, admin_user_ph4, target_user):
        """Admin can assign a tier to any workspace."""
        from core.observability.tier_enforcement import invalidate_tier_cache, get_workspace_tier
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user_ph4.id

        resp = client.post('/api/obs/admin/tier', json={
            'workspace_id': target_user.id,
            'tier_name': 'pro',
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['tier']['tier_name'] == 'pro'
        assert data['tier']['agent_limit'] == 50
        assert data['tier']['anomaly_detection_enabled'] is True

    def test_admin_can_upgrade_existing_tier(self, app, admin_user_ph4, production_user):
        """Admin can upgrade an existing production tier to pro."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user_ph4.id

        resp = client.post('/api/obs/admin/tier', json={
            'workspace_id': production_user.id,
            'tier_name': 'agency',
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier']['tier_name'] == 'agency'
        assert data['tier']['multi_workspace_enabled'] is True
        assert data['tier']['retention_days'] == 180

    def test_admin_with_custom_overrides(self, app, admin_user_ph4, target_user):
        """Admin can apply custom overrides on top of tier defaults."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user_ph4.id

        resp = client.post('/api/obs/admin/tier', json={
            'workspace_id': target_user.id,
            'tier_name': 'production',
            'overrides': {
                'agent_limit': 25,       # Custom: 25 instead of default 10
                'retention_days': 60,    # Custom: 60 instead of default 30
            },
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier']['tier_name'] == 'production'
        assert data['tier']['agent_limit'] == 25
        assert data['tier']['retention_days'] == 60
        # Non-overridden fields should still be production defaults
        assert data['tier']['alert_rule_limit'] == 3

    def test_invalid_tier_name_rejected(self, app, admin_user_ph4, target_user):
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user_ph4.id

        resp = client.post('/api/obs/admin/tier', json={
            'workspace_id': target_user.id,
            'tier_name': 'enterprise',
        })
        assert resp.status_code == 400
        assert 'tier_name' in resp.get_json()['error']

    def test_admin_get_tier(self, app, admin_user_ph4, production_user):
        """Admin can view any workspace's tier via GET endpoint."""
        from core.observability.tier_enforcement import invalidate_tier_cache
        invalidate_tier_cache()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user_ph4.id

        resp = client.get(f'/api/obs/admin/tier/{production_user.id}')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier']['tier_name'] == 'production'

    def test_tier_change_dynamically_affects_limits(self, app, admin_user_ph4, free_user):
        """After admin upgrades a workspace, limits change immediately."""
        from core.observability.tier_enforcement import invalidate_tier_cache, check_alert_rule_limit
        invalidate_tier_cache()

        # Free user cannot create alerts
        ok, _ = check_alert_rule_limit(free_user.id)
        assert ok is False

        # Admin upgrades to production
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user_ph4.id

        resp = client.post('/api/obs/admin/tier', json={
            'workspace_id': free_user.id,
            'tier_name': 'production',
        })
        assert resp.status_code == 200

        # Now free_user (now production) can create alerts
        ok, _ = check_alert_rule_limit(free_user.id)
        assert ok is True


@pytest.mark.observability
class TestBillingWebhookStub:
    """Verify the billing webhook stub endpoint."""

    def test_unauthorized_rejected(self, app, target_user):
        client = app.test_client()
        resp = client.post('/api/obs/webhooks/billing', json={
            'event_type': 'obs_subscription.created',
            'workspace_id': target_user.id,
            'tier_name': 'pro',
        })
        assert resp.status_code == 401

    def test_subscription_created(self, app, target_user):
        """obs_subscription.created assigns the tier."""
        import os
        from core.observability.tier_enforcement import invalidate_tier_cache, get_workspace_tier
        invalidate_tier_cache()

        os.environ['ADMIN_PASSWORD'] = 'test-billing-pw'

        client = app.test_client()
        resp = client.post('/api/obs/webhooks/billing', json={
            'password': 'test-billing-pw',
            'event_type': 'obs_subscription.created',
            'workspace_id': target_user.id,
            'tier_name': 'pro',
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['tier_name'] == 'pro'

        # Verify tier was actually set
        tier = get_workspace_tier(target_user.id)
        assert tier['tier_name'] == 'pro'
        assert tier['anomaly_detection_enabled'] is True

        os.environ.pop('ADMIN_PASSWORD', None)

    def test_subscription_updated(self, app, production_user):
        """obs_subscription.updated changes the tier."""
        import os
        from core.observability.tier_enforcement import invalidate_tier_cache, get_workspace_tier
        invalidate_tier_cache()

        os.environ['ADMIN_PASSWORD'] = 'test-billing-pw'

        client = app.test_client()
        resp = client.post('/api/obs/webhooks/billing', json={
            'password': 'test-billing-pw',
            'event_type': 'obs_subscription.updated',
            'workspace_id': production_user.id,
            'tier_name': 'agency',
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier_name'] == 'agency'

        tier = get_workspace_tier(production_user.id)
        assert tier['tier_name'] == 'agency'
        assert tier['priority_processing'] is True

        os.environ.pop('ADMIN_PASSWORD', None)

    def test_subscription_deleted_downgrades_to_free(self, app, pro_user):
        """obs_subscription.deleted downgrades to free tier."""
        import os
        from core.observability.tier_enforcement import invalidate_tier_cache, get_workspace_tier
        invalidate_tier_cache()

        os.environ['ADMIN_PASSWORD'] = 'test-billing-pw'

        client = app.test_client()
        resp = client.post('/api/obs/webhooks/billing', json={
            'password': 'test-billing-pw',
            'event_type': 'obs_subscription.deleted',
            'workspace_id': pro_user.id,
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['tier_name'] == 'free'

        tier = get_workspace_tier(pro_user.id)
        assert tier['tier_name'] == 'free'
        assert tier['agent_limit'] == 2

        os.environ.pop('ADMIN_PASSWORD', None)

    def test_unknown_event_type_ignored(self, app, target_user):
        """Unknown event types return ignored response."""
        import os
        os.environ['ADMIN_PASSWORD'] = 'test-billing-pw'

        client = app.test_client()
        resp = client.post('/api/obs/webhooks/billing', json={
            'password': 'test-billing-pw',
            'event_type': 'charge.succeeded',
            'workspace_id': target_user.id,
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['ignored'] is True

        os.environ.pop('ADMIN_PASSWORD', None)

    def test_webhook_with_bearer_auth(self, app, target_user):
        """Webhook authenticates via OBS_BILLING_WEBHOOK_SECRET Bearer token."""
        import os
        from core.observability.tier_enforcement import invalidate_tier_cache, get_workspace_tier
        invalidate_tier_cache()

        os.environ['OBS_BILLING_WEBHOOK_SECRET'] = 'whsec_test_123'

        client = app.test_client()
        resp = client.post('/api/obs/webhooks/billing',
                           json={
                               'event_type': 'obs_subscription.created',
                               'workspace_id': target_user.id,
                               'tier_name': 'production',
                           },
                           headers={'Authorization': 'Bearer whsec_test_123'})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True

        tier = get_workspace_tier(target_user.id)
        assert tier['tier_name'] == 'production'

        os.environ.pop('OBS_BILLING_WEBHOOK_SECRET', None)
