"""
Observability API Routes — ingestion, metrics, alerts, API key management.
Blueprint mounted at /api/obs
"""
import os
from flask import Blueprint, jsonify, request, session
from datetime import datetime, date, timedelta
from models import db, Agent, ObsApiKey, ObsEvent, ObsRun, ObsAgentDailyMetrics, ObsAlertRule, ObsAlertEvent

obs_bp = Blueprint('observability', __name__, url_prefix='/api/obs')


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_api_key_user():
    """Authenticate via Bearer API key. Returns (user_id, api_key_row) or (None, None)."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None, None
    raw_key = auth[7:]
    ak = ObsApiKey.lookup(raw_key)
    if not ak:
        return None, None
    ak.last_used_at = datetime.utcnow()
    db.session.commit()
    return ak.user_id, ak


def _require_session_auth():
    """Returns user_id from session or None."""
    return session.get('user_id')


def _require_cron_auth():
    """Verify Vercel cron secret or admin password."""
    auth = request.headers.get('Authorization', '')
    cron_secret = os.environ.get('CRON_SECRET', '')
    admin_pw = os.environ.get('ADMIN_PASSWORD', '')

    if cron_secret and auth == f'Bearer {cron_secret}':
        return True
    # Fallback: JSON body password for manual trigger
    data = request.get_json(silent=True) or {}
    if admin_pw and data.get('password') == admin_pw:
        return True
    return False


# ===================================================================
# A) INGESTION ENDPOINTS (API key auth)
# ===================================================================

@obs_bp.route('/ingest/events', methods=['POST'])
def ingest_events():
    """
    POST /api/obs/ingest/events
    Auth: Bearer API key
    Body: single event object OR {"events": [...]}
    Returns: {"accepted": N, "rejected": [...]}
    """
    user_id, api_key = _get_api_key_user()
    if not user_id:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    # Accept single event or array
    if 'events' in data:
        events_list = data['events']
    elif 'event_type' in data:
        events_list = [data]
    else:
        return jsonify({'error': 'Provide event_type (single) or events array'}), 400

    if not isinstance(events_list, list):
        return jsonify({'error': 'events must be an array'}), 400

    if len(events_list) > 1000:
        return jsonify({'error': 'Max 1000 events per request'}), 400

    from observability_service import emit_event_batch, VALID_EVENT_TYPES

    # Validate before writing
    validated = []
    rejected = []
    for i, ev in enumerate(events_list):
        if not isinstance(ev, dict):
            rejected.append({'index': i, 'reason': 'event must be an object'})
            continue
        etype = ev.get('event_type', '')
        if etype not in VALID_EVENT_TYPES:
            rejected.append({'index': i, 'reason': f"invalid event_type '{etype}'. Valid: {sorted(VALID_EVENT_TYPES)}"})
            continue
        validated.append(ev)

    accepted = 0
    if validated:
        accepted, batch_rejected = emit_event_batch(validated, user_id)
        # Re-index batch_rejected to match original positions
        for r in batch_rejected:
            rejected.append(r)

    return jsonify({
        'accepted': accepted,
        'rejected': rejected,
        'total_submitted': len(events_list),
    })


@obs_bp.route('/ingest/heartbeat', methods=['POST'])
def ingest_heartbeat():
    """
    POST /api/obs/ingest/heartbeat
    Auth: Bearer API key
    Body: {"agent_id": int, "status": str, "metadata": {...}}
    """
    user_id, api_key = _get_api_key_user()
    if not user_id:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    data = request.get_json(silent=True) or {}
    agent_id = data.get('agent_id')
    agent_status = data.get('status', 'alive')
    metadata = data.get('metadata', {})

    if not agent_id:
        return jsonify({'error': 'agent_id required'}), 400

    # Verify agent belongs to user
    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    from observability_service import emit_event

    emit_event(
        user_id=user_id,
        event_type='heartbeat',
        status='info',
        agent_id=agent_id,
        payload={'agent_status': agent_status, **metadata},
    )

    return jsonify({'success': True, 'agent_id': agent_id, 'ts': datetime.utcnow().isoformat()})


# ===================================================================
# B) METRICS ENDPOINTS (session auth)
# ===================================================================

@obs_bp.route('/metrics/agents', methods=['GET'])
def metrics_agents():
    """
    GET /api/obs/metrics/agents?from=YYYY-MM-DD&to=YYYY-MM-DD
    Returns aggregated daily metrics for all agents of the current user.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    date_from = request.args.get('from')
    date_to = request.args.get('to')

    try:
        d_from = date.fromisoformat(date_from) if date_from else date.today() - timedelta(days=7)
        d_to = date.fromisoformat(date_to) if date_to else date.today()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    metrics = ObsAgentDailyMetrics.query.filter(
        ObsAgentDailyMetrics.user_id == user_id,
        ObsAgentDailyMetrics.date >= d_from,
        ObsAgentDailyMetrics.date <= d_to,
    ).order_by(ObsAgentDailyMetrics.date.desc()).all()

    return jsonify({'metrics': [m.to_dict() for m in metrics]})


@obs_bp.route('/metrics/agent/<int:agent_id>', methods=['GET'])
def metrics_agent_detail(agent_id):
    """
    GET /api/obs/metrics/agent/<id>?from=...&to=...
    Returns daily metrics for a specific agent.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    date_from = request.args.get('from')
    date_to = request.args.get('to')

    try:
        d_from = date.fromisoformat(date_from) if date_from else date.today() - timedelta(days=30)
        d_to = date.fromisoformat(date_to) if date_to else date.today()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    metrics = ObsAgentDailyMetrics.query.filter(
        ObsAgentDailyMetrics.user_id == user_id,
        ObsAgentDailyMetrics.agent_id == agent_id,
        ObsAgentDailyMetrics.date >= d_from,
        ObsAgentDailyMetrics.date <= d_to,
    ).order_by(ObsAgentDailyMetrics.date.asc()).all()

    # Also get recent events for the detail view
    recent_events = ObsEvent.query.filter(
        ObsEvent.user_id == user_id,
        ObsEvent.agent_id == agent_id,
    ).order_by(ObsEvent.created_at.desc()).limit(50).all()

    return jsonify({
        'agent': agent.to_dict(),
        'metrics': [m.to_dict() for m in metrics],
        'recent_events': [e.to_dict() for e in recent_events],
    })


@obs_bp.route('/metrics/overview', methods=['GET'])
def metrics_overview():
    """
    GET /api/obs/metrics/overview
    Returns summary stats for dashboard KPI cards.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())

    # Today's totals from raw events (real-time)
    today_q = ObsEvent.query.filter(
        ObsEvent.user_id == user_id,
        ObsEvent.created_at >= today_start,
    )

    today_cost = db.session.query(db.func.sum(ObsEvent.cost_usd)).filter(
        ObsEvent.user_id == user_id,
        ObsEvent.created_at >= today_start,
    ).scalar()

    today_llm_calls = today_q.filter(ObsEvent.event_type == 'llm_call').count()
    today_errors = today_q.filter(ObsEvent.status == 'error').count()
    today_total = today_q.count()

    # 7-day totals from aggregated metrics
    week_ago = today - timedelta(days=7)
    week_metrics = ObsAgentDailyMetrics.query.filter(
        ObsAgentDailyMetrics.user_id == user_id,
        ObsAgentDailyMetrics.date >= week_ago,
    ).all()

    week_cost = sum(float(m.total_cost_usd or 0) for m in week_metrics)
    week_runs = sum(m.total_runs or 0 for m in week_metrics)
    week_errors = sum(m.failed_runs or 0 for m in week_metrics)

    # Active agents (have events in last 24h)
    day_ago = datetime.utcnow() - timedelta(days=1)
    active_agents = db.session.query(ObsEvent.agent_id).filter(
        ObsEvent.user_id == user_id,
        ObsEvent.created_at >= day_ago,
        ObsEvent.agent_id.isnot(None),
    ).distinct().count()

    # Unacknowledged alerts
    unack_alerts = ObsAlertEvent.query.filter(
        ObsAlertEvent.user_id == user_id,
        ObsAlertEvent.acknowledged_at.is_(None),
    ).count()

    return jsonify({
        'today': {
            'cost_usd': float(today_cost) if today_cost else 0,
            'llm_calls': today_llm_calls,
            'errors': today_errors,
            'total_events': today_total,
        },
        'week': {
            'cost_usd': round(week_cost, 4),
            'total_runs': week_runs,
            'errors': week_errors,
        },
        'active_agents_24h': active_agents,
        'unacknowledged_alerts': unack_alerts,
    })


# ===================================================================
# C) EVENTS QUERY (session auth)
# ===================================================================

@obs_bp.route('/events', methods=['GET'])
def list_events():
    """
    GET /api/obs/events?agent_id=&event_type=&status=&limit=50&offset=0
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    q = ObsEvent.query.filter(ObsEvent.user_id == user_id)

    agent_id = request.args.get('agent_id', type=int)
    event_type = request.args.get('event_type')
    status = request.args.get('status')
    run_id = request.args.get('run_id')

    if agent_id:
        q = q.filter(ObsEvent.agent_id == agent_id)
    if event_type:
        q = q.filter(ObsEvent.event_type == event_type)
    if status:
        q = q.filter(ObsEvent.status == status)
    if run_id:
        q = q.filter(ObsEvent.run_id == run_id)

    limit = min(request.args.get('limit', 50, type=int), 200)
    offset = request.args.get('offset', 0, type=int)

    total = q.count()
    events = q.order_by(ObsEvent.created_at.desc()).offset(offset).limit(limit).all()

    return jsonify({
        'events': [e.to_dict() for e in events],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


# ===================================================================
# D) ALERT ENDPOINTS (session auth)
# ===================================================================

@obs_bp.route('/alerts/rules', methods=['GET'])
def list_alert_rules():
    """GET /api/obs/alerts/rules — list user's alert rules."""
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    rules = ObsAlertRule.query.filter_by(user_id=user_id).order_by(ObsAlertRule.created_at.desc()).all()
    return jsonify({'rules': [r.to_dict() for r in rules]})


@obs_bp.route('/alerts/rules', methods=['POST'])
def create_alert_rule():
    """
    POST /api/obs/alerts/rules
    Body: {"name", "rule_type", "threshold", "agent_id"?, "window_minutes"?, "cooldown_minutes"?}
    rule_type: cost_per_day | error_rate | no_heartbeat
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}

    name = data.get('name', '').strip()
    rule_type = data.get('rule_type', '').strip()
    threshold = data.get('threshold')

    if not name or not rule_type or threshold is None:
        return jsonify({'error': 'name, rule_type, and threshold are required'}), 400

    valid_types = {'cost_per_day', 'error_rate', 'no_heartbeat'}
    if rule_type not in valid_types:
        return jsonify({'error': f'rule_type must be one of: {sorted(valid_types)}'}), 400

    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return jsonify({'error': 'threshold must be a number'}), 400

    agent_id = data.get('agent_id')
    if agent_id:
        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

    rule = ObsAlertRule(
        user_id=user_id,
        agent_id=agent_id,
        name=name,
        rule_type=rule_type,
        threshold=threshold,
        window_minutes=data.get('window_minutes', 60),
        cooldown_minutes=data.get('cooldown_minutes', 360),
    )
    db.session.add(rule)
    db.session.commit()

    return jsonify({'success': True, 'rule': rule.to_dict()}), 201


@obs_bp.route('/alerts/rules/<int:rule_id>', methods=['POST'])
def update_alert_rule(rule_id):
    """POST /api/obs/alerts/rules/<id> — update or delete an alert rule."""
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    rule = ObsAlertRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404

    data = request.get_json(silent=True) or {}

    if data.get('delete'):
        db.session.delete(rule)
        db.session.commit()
        return jsonify({'success': True, 'deleted': True})

    if 'name' in data:
        rule.name = data['name']
    if 'threshold' in data:
        rule.threshold = float(data['threshold'])
    if 'is_enabled' in data:
        rule.is_enabled = bool(data['is_enabled'])
    if 'window_minutes' in data:
        rule.window_minutes = int(data['window_minutes'])
    if 'cooldown_minutes' in data:
        rule.cooldown_minutes = int(data['cooldown_minutes'])

    db.session.commit()
    return jsonify({'success': True, 'rule': rule.to_dict()})


@obs_bp.route('/alerts/events', methods=['GET'])
def list_alert_events():
    """GET /api/obs/alerts/events — list fired alerts."""
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    limit = min(request.args.get('limit', 50, type=int), 200)
    events = ObsAlertEvent.query.filter_by(user_id=user_id)\
        .order_by(ObsAlertEvent.triggered_at.desc()).limit(limit).all()
    return jsonify({'events': [e.to_dict() for e in events]})


@obs_bp.route('/alerts/events/<int:event_id>/acknowledge', methods=['POST'])
def acknowledge_alert(event_id):
    """POST /api/obs/alerts/events/<id>/acknowledge"""
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    ae = ObsAlertEvent.query.filter_by(id=event_id, user_id=user_id).first()
    if not ae:
        return jsonify({'error': 'Alert event not found'}), 404

    ae.acknowledged_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})


# ===================================================================
# E) API KEY MANAGEMENT (session auth)
# ===================================================================

@obs_bp.route('/api-keys', methods=['GET'])
def list_api_keys():
    """GET /api/obs/api-keys"""
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    keys = ObsApiKey.query.filter_by(user_id=user_id).order_by(ObsApiKey.created_at.desc()).all()
    return jsonify({'keys': [k.to_dict() for k in keys]})


@obs_bp.route('/api-keys', methods=['POST'])
def create_api_key():
    """POST /api/obs/api-keys — create a new ingestion API key."""
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    name = data.get('name', 'default')

    api_key, raw_key = ObsApiKey.create_for_user(user_id, name=name)
    db.session.commit()

    return jsonify({
        'success': True,
        'key': raw_key,  # Only shown once
        'key_info': api_key.to_dict(),
    }), 201


@obs_bp.route('/api-keys/<int:key_id>/revoke', methods=['POST'])
def revoke_api_key(key_id):
    """POST /api/obs/api-keys/<id>/revoke"""
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    ak = ObsApiKey.query.filter_by(id=key_id, user_id=user_id).first()
    if not ak:
        return jsonify({'error': 'API key not found'}), 404

    ak.is_active = False
    db.session.commit()
    return jsonify({'success': True})


# ===================================================================
# F) CRON / INTERNAL ENDPOINTS
# ===================================================================

@obs_bp.route('/internal/aggregate', methods=['POST'])
def cron_aggregate():
    """Cron: aggregate daily metrics. Protected by CRON_SECRET."""
    if not _require_cron_auth():
        return jsonify({'error': 'Unauthorized'}), 401

    from observability_service import aggregate_daily
    from datetime import date

    # Aggregate today and yesterday (in case yesterday was missed)
    today_count = aggregate_daily(date.today())
    yesterday_count = aggregate_daily(date.today() - timedelta(days=1))

    return jsonify({
        'success': True,
        'aggregated': {'today': today_count, 'yesterday': yesterday_count},
    })


@obs_bp.route('/internal/evaluate-alerts', methods=['POST'])
def cron_evaluate_alerts():
    """Cron: evaluate alert rules. Protected by CRON_SECRET."""
    if not _require_cron_auth():
        return jsonify({'error': 'Unauthorized'}), 401

    from observability_service import evaluate_alerts
    fired = evaluate_alerts()

    return jsonify({'success': True, 'alerts_fired': fired})


# ===================================================================
# G) LLM PRICING (session auth, admin-only for writes)
# ===================================================================

@obs_bp.route('/pricing', methods=['GET'])
def list_pricing():
    """GET /api/obs/pricing — list current LLM pricing."""
    from models import ObsLlmPricing
    today = date.today()
    rows = ObsLlmPricing.query.filter(
        ObsLlmPricing.effective_from <= today,
        db.or_(ObsLlmPricing.effective_to.is_(None), ObsLlmPricing.effective_to >= today),
    ).order_by(ObsLlmPricing.provider, ObsLlmPricing.model).all()
    return jsonify({'pricing': [r.to_dict() for r in rows]})
