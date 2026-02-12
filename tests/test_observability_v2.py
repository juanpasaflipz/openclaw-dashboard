"""
Phase 2-6 tests: cost engine precision, health scores, workspace isolation,
alert engine hardening, and end-to-end integration flow.
"""
import pytest
import math
from datetime import datetime, date, timedelta
from decimal import Decimal
from models import (
    db, User, Agent, ObsApiKey, ObsEvent, ObsRun,
    ObsAgentDailyMetrics, ObsAlertRule, ObsAlertEvent, ObsLlmPricing,
    ObsAgentHealthDaily, WorkspaceTier,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _ensure_production_tier(app, user):
    """Give the default test user a 'production' workspace tier so existing
    tests keep working after tier gating was introduced (Phase 3).
    Production tier enables alerts, Slack, 30d retention — matching prior behavior.
    """
    from core.observability.tier_enforcement import invalidate_tier_cache
    invalidate_tier_cache()
    tier = WorkspaceTier(workspace_id=user.id, tier_name='production',
                         **WorkspaceTier.TIER_DEFAULTS['production'])
    db.session.add(tier)
    db.session.commit()
    invalidate_tier_cache()
    yield
    invalidate_tier_cache()


@pytest.fixture
def obs_api_key(app, user):
    api_key, raw_key = ObsApiKey.create_for_user(user.id, name='test-key')
    db.session.commit()
    return api_key, raw_key


@pytest.fixture
def obs_pricing(app):
    rows = [
        ObsLlmPricing(provider='openai', model='gpt-4o', input_cost_per_mtok=2.50,
                       output_cost_per_mtok=10.00, effective_from=date.today()),
        ObsLlmPricing(provider='openai', model='gpt-4o-mini', input_cost_per_mtok=0.15,
                       output_cost_per_mtok=0.60, effective_from=date.today()),
        ObsLlmPricing(provider='anthropic', model='claude-sonnet-4-5-20250929',
                       input_cost_per_mtok=3.00, output_cost_per_mtok=15.00,
                       effective_from=date.today()),
    ]
    for r in rows:
        db.session.add(r)
    db.session.commit()
    return rows


# ---------------------------------------------------------------------------
# PHASE 2: Cost Engine Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestCostEngineDecimal:
    """Verify Decimal-only arithmetic in the new cost engine."""

    def test_calculate_cost_returns_decimal(self, app, obs_pricing):
        from core.observability.cost_engine import calculate_cost, invalidate_pricing_cache
        invalidate_pricing_cache()

        cost = calculate_cost('openai', 'gpt-4o', 1000, 500)
        assert isinstance(cost, Decimal)
        # (1000 * 2.50 + 500 * 10.00) / 1_000_000 = 0.0075
        assert cost == Decimal('0.00750000')

    def test_no_float_drift_accumulation(self, app, obs_pricing):
        """Verify that summing many small costs doesn't introduce float drift."""
        from core.observability.cost_engine import calculate_cost, invalidate_pricing_cache
        invalidate_pricing_cache()

        total = Decimal('0')
        for _ in range(1000):
            total += calculate_cost('openai', 'gpt-4o', 100, 50)

        # Single calculation: (100*2.50 + 50*10.00)/1M = 0.00075
        expected = Decimal('0.00075000') * 1000
        assert total == expected

    def test_longest_prefix_match(self, app, obs_pricing):
        """gpt-4o-mini-2024-07-18 should match gpt-4o-mini, not gpt-4o."""
        from core.observability.cost_engine import calculate_cost, invalidate_pricing_cache
        invalidate_pricing_cache()

        # gpt-4o-mini costs: 0.15 input, 0.60 output
        cost = calculate_cost('openai', 'gpt-4o-mini-2024-07-18', 1000, 500)
        # (1000 * 0.15 + 500 * 0.60) / 1_000_000 = 0.00045
        expected = Decimal('0.00045000')
        assert cost == expected

    def test_exact_match_preferred_over_prefix(self, app, obs_pricing):
        """Exact match for gpt-4o should not pick gpt-4o-mini."""
        from core.observability.cost_engine import calculate_cost, invalidate_pricing_cache
        invalidate_pricing_cache()

        cost = calculate_cost('openai', 'gpt-4o', 1000, 500)
        expected = Decimal('0.00750000')
        assert cost == expected

    def test_unknown_provider_returns_zero(self, app, obs_pricing):
        from core.observability.cost_engine import calculate_cost, invalidate_pricing_cache
        invalidate_pricing_cache()

        cost = calculate_cost('unknown', 'unknown-model', 1000, 500)
        assert cost == Decimal('0')

    def test_cache_invalidation(self, app, obs_pricing):
        from core.observability.cost_engine import calculate_cost, invalidate_pricing_cache
        invalidate_pricing_cache()

        cost1 = calculate_cost('openai', 'gpt-4o', 1000, 500)
        assert cost1 > 0

        invalidate_pricing_cache()
        cost2 = calculate_cost('openai', 'gpt-4o', 1000, 500)
        assert cost1 == cost2

    def test_backward_compat_float_wrapper(self, app, obs_pricing):
        """observability_service.calculate_cost still returns float."""
        from observability_service import calculate_cost
        import observability_service
        # Clear old cache
        observability_service._pricing_cache = {}
        observability_service._pricing_cache_ts = 0

        from core.observability.cost_engine import invalidate_pricing_cache
        invalidate_pricing_cache()

        cost = calculate_cost('openai', 'gpt-4o', 1000, 500)
        assert isinstance(cost, float)
        assert abs(cost - 0.0075) < 0.0001


# ---------------------------------------------------------------------------
# PHASE 3: Alert Engine Hardening Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestAlertEngineHardening:

    def test_time_guard_stops_evaluation(self, app, user, agent):
        """Alert evaluation respects max_seconds limit."""
        from core.observability.alert_engine import evaluate_alerts

        # Create many rules
        for i in range(20):
            rule = ObsAlertRule(
                user_id=user.id, agent_id=agent.id,
                name=f'Rule {i}', rule_type='cost_per_day', threshold=9999.0,
            )
            db.session.add(rule)
        db.session.commit()

        # Even with max_seconds=0, should not crash
        fired = evaluate_alerts(max_seconds=0)
        assert fired == 0  # Time guard kicks in immediately

    def test_notification_dispatch(self, app, user, agent, monkeypatch):
        """Alert fires and dispatches Slack notification when configured."""
        from core.observability import emit_event, evaluate_alerts
        from core.observability import notifications

        slack_calls = []
        monkeypatch.setenv('SLACK_WEBHOOK_URL', 'https://hooks.slack.com/fake')

        def mock_post(url, json=None, timeout=None):
            slack_calls.append(json)
            class FakeResp:
                status_code = 200
            return FakeResp()

        monkeypatch.setattr(notifications.http_requests, 'post', mock_post)

        rule = ObsAlertRule(
            user_id=user.id, agent_id=agent.id, name='SlackTest',
            rule_type='cost_per_day', threshold=0.001)
        db.session.add(rule)
        db.session.commit()

        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   cost_usd=0.05, model='gpt-4o')

        fired = evaluate_alerts()
        assert fired >= 1
        assert len(slack_calls) == 1
        assert 'cost' in slack_calls[0]['text'].lower()


# ---------------------------------------------------------------------------
# PHASE 4: Health Score Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestHealthScore:

    def test_health_score_perfect(self, app, user, agent):
        """Agent with all successes, good latency, no bursts = ~100."""
        from core.observability import emit_event, aggregate_daily, compute_agent_health

        today = datetime.utcnow().date()

        # 10 successful runs, good latency
        for _ in range(10):
            emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)
            emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                       latency_ms=500, model='gpt-4o', tokens_in=100, tokens_out=50)

        aggregate_daily(today)
        result = compute_agent_health(user.id, agent.id, today)

        assert result is not None
        assert result['score'] >= 90  # Near perfect
        assert result['breakdown']['success_rate'] == 40.0

    def test_health_score_degraded(self, app, user, agent):
        """Agent with 50% errors should have significantly lower score."""
        from core.observability import emit_event, aggregate_daily, compute_agent_health

        today = datetime.utcnow().date()

        for _ in range(5):
            emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)
        for _ in range(5):
            emit_event(user.id, 'run_finished', status='error', agent_id=agent.id)

        for _ in range(10):
            emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                       latency_ms=500, model='gpt-4o')

        aggregate_daily(today)
        result = compute_agent_health(user.id, agent.id, today)

        assert result is not None
        assert result['score'] <= 80  # 50% success rate loses 20 from the 40-pt bucket
        assert result['breakdown']['success_rate'] == 20.0  # 50% of 40

    def test_health_score_persisted(self, app, user, agent):
        """Health score is persisted to obs_agent_health_daily."""
        from core.observability import emit_event, aggregate_daily, compute_agent_health

        today = datetime.utcnow().date()
        emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   latency_ms=500, model='gpt-4o')

        aggregate_daily(today)
        compute_agent_health(user.id, agent.id, today)

        stored = ObsAgentHealthDaily.query.filter_by(
            user_id=user.id, agent_id=agent.id, date=today
        ).first()
        assert stored is not None
        assert float(stored.score) > 0

    def test_health_score_idempotent(self, app, user, agent):
        """Running compute twice doesn't create duplicate rows."""
        from core.observability import emit_event, aggregate_daily, compute_agent_health

        today = datetime.utcnow().date()
        emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   latency_ms=500, model='gpt-4o')

        aggregate_daily(today)
        compute_agent_health(user.id, agent.id, today)
        compute_agent_health(user.id, agent.id, today)

        count = ObsAgentHealthDaily.query.filter_by(
            user_id=user.id, agent_id=agent.id, date=today
        ).count()
        assert count == 1

    def test_health_score_no_data_returns_none(self, app, user, agent):
        """No metrics for the day returns None."""
        from core.observability import compute_agent_health
        result = compute_agent_health(user.id, agent.id, date.today())
        assert result is None

    def test_health_api_endpoint(self, authenticated_client, user, agent, app):
        """GET /api/obs/health/agent/<id> returns scores."""
        from core.observability import emit_event, aggregate_daily, compute_agent_health

        today = datetime.utcnow().date()
        emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   latency_ms=500, model='gpt-4o')
        aggregate_daily(today)
        compute_agent_health(user.id, agent.id, today)

        resp = authenticated_client.get(f'/api/obs/health/agent/{agent.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['scores']) == 1
        assert data['scores'][0]['score'] > 0

    def test_health_overview_endpoint(self, authenticated_client, user, agent, app):
        """GET /api/obs/health/overview returns today's scores."""
        from core.observability import emit_event, aggregate_daily, compute_agent_health

        today = datetime.utcnow().date()
        emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   latency_ms=500, model='gpt-4o')
        aggregate_daily(today)
        compute_agent_health(user.id, agent.id, today)

        resp = authenticated_client.get('/api/obs/health/overview')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['health']) == 1


# ---------------------------------------------------------------------------
# PHASE 5: Workspace Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestWorkspaceIsolation:

    def test_events_scoped_to_user(self, app, user, agent):
        """User A cannot see User B's events via API."""
        from core.observability import emit_event

        # Create second user + agent
        user_b = User(email='userb@example.com', credit_balance=0)
        db.session.add(user_b)
        db.session.flush()
        agent_b = Agent(user_id=user_b.id, name='AgentB')
        db.session.add(agent_b)
        db.session.commit()

        # Emit events for both users
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id)
        emit_event(user_b.id, 'llm_call', status='success', agent_id=agent_b.id)

        # User A sees only their event
        events_a = ObsEvent.query.filter_by(user_id=user.id).all()
        events_b = ObsEvent.query.filter_by(user_id=user_b.id).all()
        assert len(events_a) == 1
        assert len(events_b) == 1
        assert events_a[0].agent_id == agent.id
        assert events_b[0].agent_id == agent_b.id

    def test_api_key_scoped_to_user(self, client, app, user, agent):
        """API key for User A cannot ingest events visible to User B."""
        _, raw_key_a = ObsApiKey.create_for_user(user.id, name='a-key')
        db.session.commit()

        user_b = User(email='userb@test.com', credit_balance=0)
        db.session.add(user_b)
        db.session.commit()

        # Ingest as User A
        resp = client.post('/api/obs/ingest/events',
            headers={'Authorization': f'Bearer {raw_key_a}', 'Content-Type': 'application/json'},
            json={'event_type': 'heartbeat'})
        assert resp.get_json()['accepted'] == 1

        # User B has no events
        events_b = ObsEvent.query.filter_by(user_id=user_b.id).all()
        assert len(events_b) == 0

    def test_metrics_scoped_to_user(self, authenticated_client, app, user, agent):
        """Metrics overview only shows current user's data."""
        from core.observability import emit_event

        user_b = User(email='userb2@test.com', credit_balance=0)
        db.session.add(user_b)
        db.session.flush()
        agent_b = Agent(user_id=user_b.id, name='AgentB2')
        db.session.add(agent_b)
        db.session.commit()

        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id, cost_usd=1.0)
        emit_event(user_b.id, 'llm_call', status='success', agent_id=agent_b.id, cost_usd=99.0)

        resp = authenticated_client.get('/api/obs/metrics/overview')
        data = resp.get_json()
        # User A (authenticated) should only see $1 today cost
        assert data['today']['cost_usd'] == 1.0

    def test_alert_rules_scoped_to_user(self, authenticated_client, app, user, agent):
        """User can only see their own alert rules."""
        user_b = User(email='userb3@test.com', credit_balance=0)
        db.session.add(user_b)
        db.session.commit()

        rule_a = ObsAlertRule(user_id=user.id, name='Mine', rule_type='cost_per_day', threshold=1.0)
        rule_b = ObsAlertRule(user_id=user_b.id, name='NotMine', rule_type='cost_per_day', threshold=1.0)
        db.session.add_all([rule_a, rule_b])
        db.session.commit()

        resp = authenticated_client.get('/api/obs/alerts/rules')
        rules = resp.get_json()['rules']
        assert len(rules) == 1
        assert rules[0]['name'] == 'Mine'

    def test_verify_agent_ownership_helper(self, app, user, agent):
        """Workspace helper correctly validates agent ownership."""
        from core.observability.workspace import verify_agent_ownership

        # Own agent
        assert verify_agent_ownership(agent.id, user.id) is not None

        # Other user's agent
        user_b = User(email='userb4@test.com', credit_balance=0)
        db.session.add(user_b)
        db.session.flush()
        agent_b = Agent(user_id=user_b.id, name='AgentB4')
        db.session.add(agent_b)
        db.session.commit()

        assert verify_agent_ownership(agent_b.id, user.id) is None


# ---------------------------------------------------------------------------
# PHASE 6: Integration Flow Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestIntegrationFlow:
    """End-to-end: seed -> ingest -> aggregate -> alert -> health."""

    def test_full_lifecycle(self, client, app, user, agent, obs_pricing):
        """Complete lifecycle test: create key, ingest, aggregate, alert, health."""
        from core.observability.cost_engine import invalidate_pricing_cache
        invalidate_pricing_cache()

        # 1. Create API key
        _, raw_key = ObsApiKey.create_for_user(user.id, name='integration-key')
        db.session.commit()
        headers = {'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'}

        # 2. Ingest events
        events = [
            {'event_type': 'run_started', 'agent_id': agent.id},
            {'event_type': 'llm_call', 'status': 'success', 'agent_id': agent.id,
             'model': 'gpt-4o', 'tokens_in': 1000, 'tokens_out': 500, 'latency_ms': 800,
             'payload': {'provider': 'openai'}},
            {'event_type': 'tool_call', 'status': 'success', 'agent_id': agent.id,
             'latency_ms': 200, 'payload': {'tool': 'search_web'}},
            {'event_type': 'run_finished', 'status': 'success', 'agent_id': agent.id,
             'model': 'gpt-4o', 'tokens_in': 1000, 'tokens_out': 500},
        ]

        resp = client.post('/api/obs/ingest/events', headers=headers, json={'events': events})
        data = resp.get_json()
        assert data['accepted'] == 4
        assert data['total_submitted'] == 4

        # 3. Verify events are stored
        stored_events = ObsEvent.query.filter_by(user_id=user.id).all()
        assert len(stored_events) == 4

        # Verify cost was auto-calculated on the LLM call event
        llm_event = [e for e in stored_events if e.event_type == 'llm_call'][0]
        assert llm_event.cost_usd is not None
        assert float(llm_event.cost_usd) > 0

        # 4. Run aggregation
        from core.observability import aggregate_daily
        today = datetime.utcnow().date()
        count = aggregate_daily(today)
        assert count >= 1

        metrics = ObsAgentDailyMetrics.query.filter_by(
            user_id=user.id, agent_id=agent.id, date=today
        ).first()
        assert metrics is not None
        assert metrics.total_runs == 1
        assert metrics.successful_runs == 1
        assert float(metrics.total_cost_usd) > 0
        assert metrics.latency_p50_ms is not None

        # 5. Create alert rule and evaluate
        rule = ObsAlertRule(
            user_id=user.id, agent_id=agent.id,
            name='Integration Cost Alert',
            rule_type='cost_per_day', threshold=0.0001,
        )
        db.session.add(rule)
        db.session.commit()

        from core.observability import evaluate_alerts
        fired = evaluate_alerts()
        assert fired >= 1

        alert_events = ObsAlertEvent.query.filter_by(rule_id=rule.id).all()
        assert len(alert_events) == 1

        # 6. Compute health score
        from core.observability import compute_agent_health
        health = compute_agent_health(user.id, agent.id, today)
        assert health is not None
        assert health['score'] > 0
        assert 'breakdown' in health

        # Verify persisted
        stored_health = ObsAgentHealthDaily.query.filter_by(
            user_id=user.id, agent_id=agent.id, date=today
        ).first()
        assert stored_health is not None
        assert float(stored_health.score) == health['score']

    def test_cron_aggregate_endpoint(self, client, app, user, agent, monkeypatch):
        """Cron aggregate endpoint works with auth."""
        from core.observability import emit_event

        monkeypatch.setenv('CRON_SECRET', 'test-cron-secret')

        emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   latency_ms=500, model='gpt-4o')

        resp = client.post('/api/obs/internal/aggregate',
            headers={'Authorization': 'Bearer test-cron-secret'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'health_scores_computed' in data

    def test_cron_evaluate_alerts_endpoint(self, client, app, monkeypatch):
        """Cron evaluate-alerts endpoint works with auth."""
        monkeypatch.setenv('CRON_SECRET', 'test-cron-secret')

        resp = client.post('/api/obs/internal/evaluate-alerts',
            headers={'Authorization': 'Bearer test-cron-secret'})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
