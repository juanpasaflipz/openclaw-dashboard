"""
Tests for the observability layer: ingestion, aggregation, alerts, API keys.
"""
import pytest
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from models import (
    db, User, Agent, ObsApiKey, ObsEvent, ObsRun,
    ObsAgentDailyMetrics, ObsAlertRule, ObsAlertEvent, ObsLlmPricing,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def obs_api_key(app, user):
    """Create an observability API key for the test user."""
    api_key, raw_key = ObsApiKey.create_for_user(user.id, name='test-key')
    db.session.commit()
    return api_key, raw_key


@pytest.fixture
def obs_pricing(app):
    """Seed minimal LLM pricing data."""
    rows = [
        ObsLlmPricing(provider='openai', model='gpt-4o', input_cost_per_mtok=2.50,
                       output_cost_per_mtok=10.00, effective_from=date.today()),
        ObsLlmPricing(provider='anthropic', model='claude-sonnet-4-5-20250929',
                       input_cost_per_mtok=3.00, output_cost_per_mtok=15.00,
                       effective_from=date.today()),
    ]
    for r in rows:
        db.session.add(r)
    db.session.commit()
    return rows


# ---------------------------------------------------------------------------
# API Key Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestObsApiKey:

    def test_create_api_key(self, app, user):
        api_key, raw_key = ObsApiKey.create_for_user(user.id, name='my-key')
        db.session.commit()

        assert raw_key.startswith('obsk_')
        assert len(raw_key) > 20
        assert api_key.key_prefix == raw_key[:12]
        assert api_key.is_active is True
        assert api_key.name == 'my-key'

    def test_lookup_api_key(self, app, user):
        _, raw_key = ObsApiKey.create_for_user(user.id)
        db.session.commit()

        found = ObsApiKey.lookup(raw_key)
        assert found is not None
        assert found.user_id == user.id

    def test_lookup_revoked_key_fails(self, app, user):
        api_key, raw_key = ObsApiKey.create_for_user(user.id)
        api_key.is_active = False
        db.session.commit()

        assert ObsApiKey.lookup(raw_key) is None

    def test_lookup_invalid_key_fails(self, app):
        assert ObsApiKey.lookup('obsk_does_not_exist') is None


# ---------------------------------------------------------------------------
# Ingestion API Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestIngestionAPI:

    def test_ingest_single_event(self, client, user, agent, obs_api_key):
        _, raw_key = obs_api_key

        resp = client.post('/api/obs/ingest/events',
            headers={'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'},
            json={'event_type': 'heartbeat', 'agent_id': agent.id})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['accepted'] == 1
        assert data['rejected'] == []

    def test_ingest_batch_events(self, client, user, agent, obs_api_key):
        _, raw_key = obs_api_key

        events = [
            {'event_type': 'llm_call', 'status': 'success', 'agent_id': agent.id,
             'model': 'gpt-4o', 'tokens_in': 100, 'tokens_out': 50, 'latency_ms': 500},
            {'event_type': 'tool_call', 'status': 'success', 'agent_id': agent.id,
             'latency_ms': 200, 'payload': {'tool': 'search_web'}},
            {'event_type': 'heartbeat', 'agent_id': agent.id},
        ]

        resp = client.post('/api/obs/ingest/events',
            headers={'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'},
            json={'events': events})

        data = resp.get_json()
        assert data['accepted'] == 3
        assert data['total_submitted'] == 3

    def test_ingest_invalid_event_type_rejected(self, client, user, obs_api_key):
        _, raw_key = obs_api_key

        resp = client.post('/api/obs/ingest/events',
            headers={'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'},
            json={'event_type': 'not_a_valid_type'})

        data = resp.get_json()
        assert data['accepted'] == 0
        assert len(data['rejected']) == 1
        assert 'invalid event_type' in data['rejected'][0]['reason']

    def test_ingest_without_auth_fails(self, client):
        resp = client.post('/api/obs/ingest/events',
            json={'event_type': 'heartbeat'})

        assert resp.status_code == 401

    def test_ingest_with_invalid_key_fails(self, client):
        resp = client.post('/api/obs/ingest/events',
            headers={'Authorization': 'Bearer obsk_fake_key_that_does_not_exist'},
            json={'event_type': 'heartbeat'})

        assert resp.status_code == 401

    def test_ingest_max_batch_limit(self, client, user, obs_api_key):
        _, raw_key = obs_api_key

        events = [{'event_type': 'metric'} for _ in range(1001)]
        resp = client.post('/api/obs/ingest/events',
            headers={'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'},
            json={'events': events})

        assert resp.status_code == 400
        assert 'Max 1000' in resp.get_json()['error']

    def test_ingest_dedupe_key(self, client, user, agent, obs_api_key):
        _, raw_key = obs_api_key
        headers = {'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'}
        body = {'event_type': 'metric', 'agent_id': agent.id, 'dedupe_key': 'unique-123'}

        # First call succeeds
        resp1 = client.post('/api/obs/ingest/events', headers=headers, json=body)
        assert resp1.get_json()['accepted'] == 1

        # Second call with same dedupe_key should be rejected (dedupe conflict)
        resp2 = client.post('/api/obs/ingest/events', headers=headers, json=body)
        data2 = resp2.get_json()
        # It's handled gracefully (either accepted=0 or in rejected)
        assert data2['accepted'] == 0 or len(data2['rejected']) > 0


# ---------------------------------------------------------------------------
# Heartbeat Endpoint Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestHeartbeatAPI:

    def test_heartbeat(self, client, user, agent, obs_api_key):
        _, raw_key = obs_api_key

        resp = client.post('/api/obs/ingest/heartbeat',
            headers={'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'},
            json={'agent_id': agent.id, 'status': 'alive'})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['agent_id'] == agent.id

    def test_heartbeat_missing_agent_id(self, client, user, obs_api_key):
        _, raw_key = obs_api_key

        resp = client.post('/api/obs/ingest/heartbeat',
            headers={'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'},
            json={'status': 'alive'})

        assert resp.status_code == 400

    def test_heartbeat_wrong_user_agent(self, client, app, user, obs_api_key):
        """Test that heartbeat rejects agents belonging to other users."""
        _, raw_key = obs_api_key

        other_user = User(email='other@example.com', credit_balance=0)
        db.session.add(other_user)
        db.session.flush()
        other_agent = Agent(user_id=other_user.id, name='OtherAgent')
        db.session.add(other_agent)
        db.session.commit()

        resp = client.post('/api/obs/ingest/heartbeat',
            headers={'Authorization': f'Bearer {raw_key}', 'Content-Type': 'application/json'},
            json={'agent_id': other_agent.id})

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Metrics / Overview API Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestMetricsAPI:

    def test_overview_requires_auth(self, client):
        resp = client.get('/api/obs/metrics/overview')
        assert resp.status_code == 401

    def test_overview_returns_structure(self, authenticated_client):
        resp = authenticated_client.get('/api/obs/metrics/overview')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'today' in data
        assert 'week' in data
        assert 'active_agents_24h' in data
        assert 'unacknowledged_alerts' in data

    def test_agents_metrics(self, authenticated_client):
        resp = authenticated_client.get('/api/obs/metrics/agents')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'metrics' in data
        assert isinstance(data['metrics'], list)

    def test_agent_detail_metrics(self, authenticated_client, agent):
        resp = authenticated_client.get(f'/api/obs/metrics/agent/{agent.id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'agent' in data
        assert 'metrics' in data
        assert 'recent_events' in data


# ---------------------------------------------------------------------------
# Events Query Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestEventsQuery:

    def test_list_events_requires_auth(self, client):
        resp = client.get('/api/obs/events')
        assert resp.status_code == 401

    def test_list_events_empty(self, authenticated_client):
        resp = authenticated_client.get('/api/obs/events')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['events'] == []
        assert data['total'] == 0

    def test_list_events_with_filters(self, authenticated_client, user, agent, app):
        """Insert events and query with filters."""
        from observability_service import emit_event

        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id, model='gpt-4o')
        emit_event(user.id, 'tool_call', status='error', agent_id=agent.id)
        emit_event(user.id, 'heartbeat', agent_id=agent.id)

        # All events
        resp = authenticated_client.get('/api/obs/events')
        assert resp.get_json()['total'] == 3

        # Filter by type
        resp = authenticated_client.get('/api/obs/events?event_type=llm_call')
        assert resp.get_json()['total'] == 1

        # Filter by status
        resp = authenticated_client.get('/api/obs/events?status=error')
        assert resp.get_json()['total'] == 1


# ---------------------------------------------------------------------------
# Alert Rules Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestAlertRules:

    def test_create_alert_rule(self, authenticated_client, agent):
        resp = authenticated_client.post('/api/obs/alerts/rules', json={
            'name': 'High Cost Alert',
            'rule_type': 'cost_per_day',
            'threshold': 5.0,
            'agent_id': agent.id,
        })

        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['rule']['name'] == 'High Cost Alert'
        assert data['rule']['rule_type'] == 'cost_per_day'

    def test_create_alert_invalid_type(self, authenticated_client):
        resp = authenticated_client.post('/api/obs/alerts/rules', json={
            'name': 'Bad Rule',
            'rule_type': 'invalid_type',
            'threshold': 1.0,
        })
        assert resp.status_code == 400

    def test_list_alert_rules(self, authenticated_client, user, app):
        rule = ObsAlertRule(
            user_id=user.id, name='Test Rule', rule_type='error_rate', threshold=50.0)
        db.session.add(rule)
        db.session.commit()

        resp = authenticated_client.get('/api/obs/alerts/rules')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['rules']) == 1

    def test_toggle_alert_rule(self, authenticated_client, user, app):
        rule = ObsAlertRule(
            user_id=user.id, name='Toggle Rule', rule_type='cost_per_day', threshold=10.0)
        db.session.add(rule)
        db.session.commit()

        # Disable
        resp = authenticated_client.post(f'/api/obs/alerts/rules/{rule.id}', json={
            'is_enabled': False})
        assert resp.status_code == 200
        assert resp.get_json()['rule']['is_enabled'] is False

    def test_delete_alert_rule(self, authenticated_client, user, app):
        rule = ObsAlertRule(
            user_id=user.id, name='Delete Me', rule_type='no_heartbeat', threshold=30)
        db.session.add(rule)
        db.session.commit()
        rule_id = rule.id

        resp = authenticated_client.post(f'/api/obs/alerts/rules/{rule_id}', json={
            'delete': True})
        assert resp.status_code == 200
        assert resp.get_json()['deleted'] is True
        assert ObsAlertRule.query.get(rule_id) is None


# ---------------------------------------------------------------------------
# API Key Management Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestApiKeyManagement:

    def test_create_api_key_via_api(self, authenticated_client):
        resp = authenticated_client.post('/api/obs/api-keys', json={'name': 'prod-key'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['key'].startswith('obsk_')
        assert data['key_info']['name'] == 'prod-key'

    def test_list_api_keys(self, authenticated_client, user, app):
        ObsApiKey.create_for_user(user.id, name='key-1')
        ObsApiKey.create_for_user(user.id, name='key-2')
        db.session.commit()

        resp = authenticated_client.get('/api/obs/api-keys')
        assert resp.status_code == 200
        assert len(resp.get_json()['keys']) == 2

    def test_revoke_api_key(self, authenticated_client, user, app):
        api_key, raw_key = ObsApiKey.create_for_user(user.id)
        db.session.commit()

        resp = authenticated_client.post(f'/api/obs/api-keys/{api_key.id}/revoke')
        assert resp.status_code == 200

        # Key should no longer work for lookup
        assert ObsApiKey.lookup(raw_key) is None


# ---------------------------------------------------------------------------
# Aggregation Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestAggregation:

    def test_aggregate_daily(self, app, user, agent):
        """Test that daily aggregation produces correct metrics."""
        from observability_service import emit_event, aggregate_daily

        today = datetime.utcnow().date()
        # Simulate events
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   model='gpt-4o', tokens_in=1000, tokens_out=500, latency_ms=800)
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   model='gpt-4o', tokens_in=2000, tokens_out=1000, latency_ms=1200)
        emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)
        emit_event(user.id, 'run_finished', status='error', agent_id=agent.id)
        emit_event(user.id, 'tool_call', status='success', agent_id=agent.id, latency_ms=300)
        emit_event(user.id, 'tool_call', status='error', agent_id=agent.id, latency_ms=100)

        count = aggregate_daily(today)
        assert count >= 1

        m = ObsAgentDailyMetrics.query.filter_by(
            user_id=user.id, agent_id=agent.id, date=today).first()
        assert m is not None
        assert m.total_runs == 2
        assert m.successful_runs == 1
        assert m.failed_runs == 1
        assert m.total_tokens_in == 3000
        assert m.total_tokens_out == 1500
        assert m.total_tool_calls == 2
        assert m.tool_errors == 1
        assert m.latency_p50_ms is not None
        assert m.latency_p95_ms is not None

    def test_aggregate_idempotent(self, app, user, agent):
        """Running aggregation twice should not double-count."""
        from observability_service import emit_event, aggregate_daily

        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   tokens_in=500, tokens_out=200, latency_ms=400)

        today = datetime.utcnow().date()
        aggregate_daily(today)
        aggregate_daily(today)  # Run again

        metrics = ObsAgentDailyMetrics.query.filter_by(
            user_id=user.id, agent_id=agent.id, date=today).all()
        assert len(metrics) == 1  # Should not create duplicate rows


# ---------------------------------------------------------------------------
# Alert Evaluation Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestAlertEvaluation:

    def test_cost_alert_fires(self, app, user, agent):
        """Test cost_per_day alert fires when threshold exceeded."""
        from observability_service import emit_event, evaluate_alerts

        # Create a low threshold rule
        rule = ObsAlertRule(
            user_id=user.id, agent_id=agent.id, name='Cost Alert',
            rule_type='cost_per_day', threshold=0.001)
        db.session.add(rule)
        db.session.commit()

        # Emit expensive event
        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   cost_usd=0.05, model='gpt-4o')

        fired = evaluate_alerts()
        assert fired >= 1

        alerts = ObsAlertEvent.query.filter_by(rule_id=rule.id).all()
        assert len(alerts) == 1
        assert 'cost' in alerts[0].message.lower()

    def test_error_rate_alert_fires(self, app, user, agent):
        """Test error_rate alert fires when threshold exceeded."""
        from observability_service import emit_event, evaluate_alerts

        rule = ObsAlertRule(
            user_id=user.id, agent_id=agent.id, name='Error Rate',
            rule_type='error_rate', threshold=20.0, window_minutes=60)
        db.session.add(rule)
        db.session.commit()

        # 3 out of 4 runs fail = 75% error rate
        emit_event(user.id, 'run_finished', status='error', agent_id=agent.id)
        emit_event(user.id, 'run_finished', status='error', agent_id=agent.id)
        emit_event(user.id, 'run_finished', status='error', agent_id=agent.id)
        emit_event(user.id, 'run_finished', status='success', agent_id=agent.id)

        fired = evaluate_alerts()
        assert fired >= 1

    def test_no_heartbeat_alert_fires(self, app, user, agent):
        """Test no_heartbeat alert fires when agent goes silent."""
        from observability_service import evaluate_alerts

        rule = ObsAlertRule(
            user_id=user.id, agent_id=agent.id, name='Heartbeat',
            rule_type='no_heartbeat', threshold=5)  # 5 minutes
        db.session.add(rule)
        db.session.commit()

        # No heartbeat events exist — should fire
        fired = evaluate_alerts()
        assert fired >= 1

    def test_cooldown_prevents_double_fire(self, app, user, agent):
        """Test that cooldown prevents repeated alert firing."""
        from observability_service import emit_event, evaluate_alerts

        rule = ObsAlertRule(
            user_id=user.id, agent_id=agent.id, name='Cost',
            rule_type='cost_per_day', threshold=0.001, cooldown_minutes=360)
        db.session.add(rule)
        db.session.commit()

        emit_event(user.id, 'llm_call', status='success', agent_id=agent.id,
                   cost_usd=0.05, model='gpt-4o')

        fired1 = evaluate_alerts()
        assert fired1 >= 1

        fired2 = evaluate_alerts()
        assert fired2 == 0  # Cooldown should prevent re-fire

    def test_acknowledge_alert(self, authenticated_client, user, agent, app):
        rule = ObsAlertRule(
            user_id=user.id, name='AckTest', rule_type='cost_per_day', threshold=0.0)
        db.session.add(rule)
        db.session.flush()

        ae = ObsAlertEvent(
            rule_id=rule.id, user_id=user.id, agent_id=agent.id,
            metric_value=1.0, threshold_value=0.0,
            rule_type='cost_per_day', message='test alert')
        db.session.add(ae)
        db.session.commit()

        resp = authenticated_client.post(f'/api/obs/alerts/events/{ae.id}/acknowledge')
        assert resp.status_code == 200

        refreshed = ObsAlertEvent.query.get(ae.id)
        assert refreshed.acknowledged_at is not None


# ---------------------------------------------------------------------------
# Cost Calculation Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestCostCalculation:

    def test_calculate_cost_with_pricing(self, app, obs_pricing):
        from observability_service import calculate_cost, _pricing_cache, _pricing_cache_ts
        # Force cache reload
        import observability_service
        observability_service._pricing_cache = {}
        observability_service._pricing_cache_ts = 0

        cost = calculate_cost('openai', 'gpt-4o', 1000, 500)
        # Expected: (1000 * 2.50 + 500 * 10.00) / 1_000_000 = 0.0075
        assert abs(cost - 0.0075) < 0.0001

    def test_calculate_cost_unknown_model(self, app):
        from observability_service import calculate_cost
        cost = calculate_cost('unknown_provider', 'unknown_model', 1000, 500)
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Pricing Endpoint Tests
# ---------------------------------------------------------------------------

@pytest.mark.observability
class TestPricingEndpoint:

    def test_list_pricing(self, client, app, obs_pricing):
        resp = client.get('/api/obs/pricing')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['pricing']) >= 2
