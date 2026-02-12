"""
Observability API Routes — ingestion, metrics, alerts, API key management, health scores.
Blueprint mounted at /api/obs

All business logic is delegated to core.observability package.
Routes are thin HTTP handlers only.
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
    Tier-enforced: batch size limit, agent monitoring limit.
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

    # Tier-enforced batch size
    from core.observability.tier_enforcement import get_max_batch_size, check_agent_allowed
    max_batch = get_max_batch_size(user_id)
    if len(events_list) > max_batch:
        return jsonify({
            'error': f'Batch size {len(events_list)} exceeds tier limit ({max_batch}). Upgrade for larger batches.',
            'upgrade_required': True,
        }), 403

    from core.observability import emit_event_batch, VALID_EVENT_TYPES

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
        # Tier-enforced agent limit
        agent_id = ev.get('agent_id')
        if agent_id is not None:
            ok, msg = check_agent_allowed(user_id, agent_id)
            if not ok:
                rejected.append({'index': i, 'reason': msg})
                continue
        validated.append(ev)

    accepted = 0
    if validated:
        accepted, batch_rejected = emit_event_batch(validated, user_id)
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
    Tier-enforced: agent monitoring limit.
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

    from core.observability import verify_agent_ownership
    agent = verify_agent_ownership(agent_id, user_id)
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    # Tier-enforced agent limit
    from core.observability.tier_enforcement import check_agent_allowed
    ok, msg = check_agent_allowed(user_id, agent_id)
    if not ok:
        return jsonify({'error': msg, 'upgrade_required': True}), 403

    from core.observability import emit_event

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
    Date range is clamped to the workspace's retention window.
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

    from core.observability.tier_enforcement import clamp_date_range
    d_from, d_to = clamp_date_range(user_id, d_from, d_to)

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
    Date range and recent events are clamped to the workspace's retention window.
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

    from core.observability.tier_enforcement import clamp_date_range, get_retention_cutoff
    d_from, d_to = clamp_date_range(user_id, d_from, d_to)

    metrics = ObsAgentDailyMetrics.query.filter(
        ObsAgentDailyMetrics.user_id == user_id,
        ObsAgentDailyMetrics.agent_id == agent_id,
        ObsAgentDailyMetrics.date >= d_from,
        ObsAgentDailyMetrics.date <= d_to,
    ).order_by(ObsAgentDailyMetrics.date.asc()).all()

    retention_cutoff = get_retention_cutoff(user_id)
    recent_events = ObsEvent.query.filter(
        ObsEvent.user_id == user_id,
        ObsEvent.agent_id == agent_id,
        ObsEvent.created_at >= retention_cutoff,
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

    week_ago = today - timedelta(days=7)
    week_metrics = ObsAgentDailyMetrics.query.filter(
        ObsAgentDailyMetrics.user_id == user_id,
        ObsAgentDailyMetrics.date >= week_ago,
    ).all()

    week_cost = sum(float(m.total_cost_usd or 0) for m in week_metrics)
    week_runs = sum(m.total_runs or 0 for m in week_metrics)
    week_errors = sum(m.failed_runs or 0 for m in week_metrics)

    day_ago = datetime.utcnow() - timedelta(days=1)
    active_agents = db.session.query(ObsEvent.agent_id).filter(
        ObsEvent.user_id == user_id,
        ObsEvent.created_at >= day_ago,
        ObsEvent.agent_id.isnot(None),
    ).distinct().count()

    unack_alerts = ObsAlertEvent.query.filter(
        ObsAlertEvent.user_id == user_id,
        ObsAlertEvent.acknowledged_at.is_(None),
    ).count()

    from core.observability.tier_enforcement import get_workspace_tier
    tier = get_workspace_tier(user_id)

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
        'tier': {
            'name': tier['tier_name'],
            'retention_days': tier['retention_days'],
        },
    })


# ===================================================================
# C) EVENTS QUERY (session auth)
# ===================================================================

@obs_bp.route('/events', methods=['GET'])
def list_events():
    """
    GET /api/obs/events?agent_id=&event_type=&status=&limit=50&offset=0
    Events are filtered to the workspace's retention window.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    from core.observability.tier_enforcement import get_retention_cutoff
    retention_cutoff = get_retention_cutoff(user_id)

    q = ObsEvent.query.filter(
        ObsEvent.user_id == user_id,
        ObsEvent.created_at >= retention_cutoff,
    )

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
    Tier-enforced: alert rule count limit.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    # Tier-enforced alert rule limit
    from core.observability.tier_enforcement import check_alert_rule_limit
    ok, msg = check_alert_rule_limit(user_id)
    if not ok:
        return jsonify({'error': msg, 'upgrade_required': True}), 403

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
    """POST /api/obs/api-keys — create a new ingestion API key.
    Tier-enforced: API key count limit.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    # Tier-enforced API key limit
    from core.observability.tier_enforcement import check_api_key_limit
    ok, msg = check_api_key_limit(user_id)
    if not ok:
        return jsonify({'error': msg, 'upgrade_required': True}), 403

    data = request.get_json(silent=True) or {}
    name = data.get('name', 'default')

    api_key, raw_key = ObsApiKey.create_for_user(user_id, name=name)
    db.session.commit()

    return jsonify({
        'success': True,
        'key': raw_key,
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
    """Cron: aggregate daily metrics + health scores. Protected by CRON_SECRET."""
    if not _require_cron_auth():
        return jsonify({'error': 'Unauthorized'}), 401

    from core.observability import aggregate_daily

    utc_today = datetime.utcnow().date()
    today_count = aggregate_daily(utc_today)
    yesterday_count = aggregate_daily(utc_today - timedelta(days=1))

    # Also compute health scores after aggregation
    health_count = 0
    try:
        from core.observability import compute_all_health_scores
        from models import User
        # Process all users with recent events
        user_ids = db.session.query(ObsEvent.user_id).filter(
            ObsEvent.created_at >= datetime.utcnow() - timedelta(days=1),
        ).distinct().all()
        for (uid,) in user_ids:
            results = compute_all_health_scores(uid, utc_today)
            health_count += len(results)
    except Exception as e:
        print(f"[obs] Health score computation failed: {e}")

    return jsonify({
        'success': True,
        'aggregated': {'today': today_count, 'yesterday': yesterday_count},
        'health_scores_computed': health_count,
    })


@obs_bp.route('/internal/retention-cleanup', methods=['POST'])
def cron_retention_cleanup():
    """Cron: delete events past each workspace's retention window. Protected by CRON_SECRET."""
    if not _require_cron_auth():
        return jsonify({'error': 'Unauthorized'}), 401

    from core.observability.retention import cleanup_expired_events
    results = cleanup_expired_events()

    total_events = sum(r['events_deleted'] for r in results.values())
    total_runs = sum(r['runs_deleted'] for r in results.values())

    return jsonify({
        'success': True,
        'workspaces_processed': len(results),
        'total_events_deleted': total_events,
        'total_runs_deleted': total_runs,
        'details': {str(k): v for k, v in results.items()},
    })


@obs_bp.route('/internal/evaluate-alerts', methods=['POST'])
def cron_evaluate_alerts():
    """Cron: evaluate alert rules. Protected by CRON_SECRET."""
    if not _require_cron_auth():
        return jsonify({'error': 'Unauthorized'}), 401

    from core.observability import evaluate_alerts
    fired = evaluate_alerts()

    return jsonify({'success': True, 'alerts_fired': fired})


# ===================================================================
# G) LLM PRICING (session auth)
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


# ===================================================================
# H) HEALTH SCORE ENDPOINTS (session auth)
# ===================================================================

@obs_bp.route('/health/agent/<int:agent_id>', methods=['GET'])
def agent_health(agent_id):
    """
    GET /api/obs/health/agent/<id>?from=YYYY-MM-DD&to=YYYY-MM-DD
    Returns health score history for a specific agent.
    History depth is limited by the workspace's tier.
    Anomaly detection breakdown is hidden for non-Pro tiers.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    from models import ObsAgentHealthDaily
    from core.observability.tier_enforcement import get_health_history_cutoff, check_anomaly_detection

    date_from = request.args.get('from')
    date_to = request.args.get('to')

    try:
        d_from = date.fromisoformat(date_from) if date_from else datetime.utcnow().date() - timedelta(days=30)
        d_to = date.fromisoformat(date_to) if date_to else datetime.utcnow().date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Clamp from-date to tier's health history limit
    history_cutoff = get_health_history_cutoff(user_id)
    if d_from < history_cutoff:
        d_from = history_cutoff

    scores = ObsAgentHealthDaily.query.filter(
        ObsAgentHealthDaily.user_id == user_id,
        ObsAgentHealthDaily.agent_id == agent_id,
        ObsAgentHealthDaily.date >= d_from,
        ObsAgentHealthDaily.date <= d_to,
    ).order_by(ObsAgentHealthDaily.date.asc()).all()

    anomaly_enabled = check_anomaly_detection(user_id)
    result = []
    for s in scores:
        entry = s.to_dict()
        if not anomaly_enabled:
            entry['breakdown'].pop('cost_anomaly', None)
            entry.get('details', {}).pop('cost_anomaly', None)
        result.append(entry)

    return jsonify({
        'agent_id': agent_id,
        'scores': result,
        'anomaly_detection_enabled': anomaly_enabled,
    })


@obs_bp.route('/health/overview', methods=['GET'])
def health_overview():
    """
    GET /api/obs/health/overview
    Returns latest health score for all agents.
    Anomaly detection breakdown is hidden for non-Pro tiers.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    from models import ObsAgentHealthDaily
    from core.observability.tier_enforcement import check_anomaly_detection

    today = datetime.utcnow().date()
    scores = ObsAgentHealthDaily.query.filter(
        ObsAgentHealthDaily.user_id == user_id,
        ObsAgentHealthDaily.date == today,
    ).all()

    agents = Agent.query.filter_by(user_id=user_id, is_active=True).all()
    agent_map = {a.id: a.to_dict() for a in agents}

    anomaly_enabled = check_anomaly_detection(user_id)
    result = []
    for s in scores:
        entry = s.to_dict()
        entry['agent'] = agent_map.get(s.agent_id)
        if not anomaly_enabled:
            entry['breakdown'].pop('cost_anomaly', None)
            entry.get('details', {}).pop('cost_anomaly', None)
        result.append(entry)

    return jsonify({'health': result, 'anomaly_detection_enabled': anomaly_enabled})


# ===================================================================
# I) TIER MANAGEMENT (admin + session auth)
# ===================================================================

@obs_bp.route('/tier', methods=['GET'])
def get_tier():
    """
    GET /api/obs/tier
    Returns the current workspace tier configuration for the authenticated user.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    from core.observability.tier_enforcement import get_workspace_tier
    tier = get_workspace_tier(user_id)
    return jsonify({'tier': tier})


@obs_bp.route('/admin/tier', methods=['POST'])
def admin_update_tier():
    """
    POST /api/obs/admin/tier
    Admin-only endpoint to update a workspace's observability tier.

    Body: {
        "workspace_id": int (required),
        "tier_name": str (required — free|production|pro|agency),
        "overrides": {...} (optional — custom limit overrides)
    }

    If tier_name is valid, all limits are set from WorkspaceTier.TIER_DEFAULTS.
    If overrides are provided, they are applied on top of the defaults.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    from models import User, WorkspaceTier
    from core.observability.tier_enforcement import invalidate_tier_cache

    # Admin check
    admin = User.query.get(user_id)
    if not admin or not admin.is_admin:
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json(silent=True) or {}
    workspace_id = data.get('workspace_id')
    tier_name = data.get('tier_name', '').strip()
    overrides = data.get('overrides', {})

    if not workspace_id:
        return jsonify({'error': 'workspace_id is required'}), 400

    valid_tiers = set(WorkspaceTier.TIER_DEFAULTS.keys())
    if tier_name not in valid_tiers:
        return jsonify({'error': f'tier_name must be one of: {sorted(valid_tiers)}'}), 400

    # Verify target workspace exists
    target_user = User.query.get(workspace_id)
    if not target_user:
        return jsonify({'error': 'Workspace (user) not found'}), 404

    # Build tier config from defaults + overrides
    defaults = WorkspaceTier.TIER_DEFAULTS[tier_name].copy()

    # Apply allowed overrides
    allowed_override_keys = {
        'agent_limit', 'retention_days', 'alert_rule_limit',
        'health_history_days', 'anomaly_detection_enabled',
        'slack_notifications_enabled', 'multi_workspace_enabled',
        'priority_processing', 'max_api_keys', 'max_batch_size',
    }
    for key, value in overrides.items():
        if key in allowed_override_keys:
            defaults[key] = value

    # Upsert
    existing = WorkspaceTier.query.filter_by(workspace_id=workspace_id).first()
    if existing:
        existing.tier_name = tier_name
        for key, value in defaults.items():
            setattr(existing, key, value)
    else:
        tier = WorkspaceTier(workspace_id=workspace_id, tier_name=tier_name, **defaults)
        db.session.add(tier)

    db.session.commit()
    invalidate_tier_cache(workspace_id)

    from core.observability.tier_enforcement import get_workspace_tier
    updated = get_workspace_tier(workspace_id)

    return jsonify({'success': True, 'tier': updated})


@obs_bp.route('/admin/tier/<int:workspace_id>', methods=['GET'])
def admin_get_tier(workspace_id):
    """
    GET /api/obs/admin/tier/<workspace_id>
    Admin-only: view any workspace's tier configuration.
    """
    user_id = _require_session_auth()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    from models import User
    admin = User.query.get(user_id)
    if not admin or not admin.is_admin:
        return jsonify({'error': 'Admin access required'}), 403

    from core.observability.tier_enforcement import get_workspace_tier
    tier = get_workspace_tier(workspace_id)
    return jsonify({'tier': tier})


# ===================================================================
# J) BILLING WEBHOOK STUB (future Stripe integration)
# ===================================================================

@obs_bp.route('/webhooks/billing', methods=['POST'])
def billing_webhook():
    """
    POST /api/obs/webhooks/billing
    Webhook-ready structure for future billing integration (e.g., Stripe).

    Expected event types:
    - obs_subscription.created  → assign tier
    - obs_subscription.updated  → update tier
    - obs_subscription.deleted  → downgrade to free

    Body: {
        "event_type": str,
        "workspace_id": int,
        "tier_name": str (for created/updated),
        "subscription_id": str (optional, for tracking),
    }

    NOTE: This is a STUB. In production, this endpoint should:
    1. Verify Stripe webhook signature
    2. Parse the Stripe event object
    3. Map Stripe price IDs to tier names
    For now, it accepts direct JSON for testing and manual tier management.
    """
    # In production: verify Stripe signature here
    # stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

    # For now: accept cron auth or a shared secret
    auth = request.headers.get('Authorization', '')
    webhook_secret = os.environ.get('OBS_BILLING_WEBHOOK_SECRET', '')
    admin_pw = os.environ.get('ADMIN_PASSWORD', '')

    authorized = False
    if webhook_secret and auth == f'Bearer {webhook_secret}':
        authorized = True
    elif admin_pw:
        data_check = request.get_json(silent=True) or {}
        if data_check.get('password') == admin_pw:
            authorized = True

    if not authorized:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    event_type = data.get('event_type', '')
    workspace_id = data.get('workspace_id')

    if not workspace_id:
        return jsonify({'error': 'workspace_id is required'}), 400

    from models import User, WorkspaceTier
    from core.observability.tier_enforcement import invalidate_tier_cache

    target_user = User.query.get(workspace_id)
    if not target_user:
        return jsonify({'error': 'Workspace not found'}), 404

    # --- Event handlers ---

    if event_type in ('obs_subscription.created', 'obs_subscription.updated'):
        tier_name = data.get('tier_name', '').strip()
        valid_tiers = set(WorkspaceTier.TIER_DEFAULTS.keys())
        if tier_name not in valid_tiers:
            return jsonify({'error': f'tier_name must be one of: {sorted(valid_tiers)}'}), 400

        defaults = WorkspaceTier.TIER_DEFAULTS[tier_name]
        existing = WorkspaceTier.query.filter_by(workspace_id=workspace_id).first()
        if existing:
            existing.tier_name = tier_name
            for key, value in defaults.items():
                setattr(existing, key, value)
        else:
            tier = WorkspaceTier(workspace_id=workspace_id, tier_name=tier_name, **defaults)
            db.session.add(tier)

        db.session.commit()
        invalidate_tier_cache(workspace_id)

        return jsonify({
            'success': True,
            'event_type': event_type,
            'workspace_id': workspace_id,
            'tier_name': tier_name,
        })

    elif event_type == 'obs_subscription.deleted':
        # Downgrade to free
        free_defaults = WorkspaceTier.TIER_DEFAULTS['free']
        existing = WorkspaceTier.query.filter_by(workspace_id=workspace_id).first()
        if existing:
            existing.tier_name = 'free'
            for key, value in free_defaults.items():
                setattr(existing, key, value)
        else:
            tier = WorkspaceTier(workspace_id=workspace_id, tier_name='free', **free_defaults)
            db.session.add(tier)

        db.session.commit()
        invalidate_tier_cache(workspace_id)

        return jsonify({
            'success': True,
            'event_type': event_type,
            'workspace_id': workspace_id,
            'tier_name': 'free',
        })

    else:
        return jsonify({
            'ignored': True,
            'event_type': event_type,
            'message': f"Unhandled event type: '{event_type}'",
        })
