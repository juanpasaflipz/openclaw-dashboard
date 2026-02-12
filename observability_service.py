"""
Observability service — event emission, cost calculation, aggregation.

Public API:
    emit_event(user_id, event_type, ...) → ObsEvent | None
    calculate_cost(provider, model, tokens_in, tokens_out) → float
    start_run(user_id, agent_id) → run_id
    finish_run(run_id, status, error) → None
    aggregate_daily(target_date) → int  (rows upserted)
    evaluate_alerts() → int  (alerts fired)
"""
import time
import uuid
import os
import requests as http_requests
from datetime import datetime, date, timedelta
from decimal import Decimal
from models import db, ObsEvent, ObsRun, ObsAgentDailyMetrics, ObsAlertRule, ObsAlertEvent, ObsLlmPricing, Agent


# ---------------------------------------------------------------------------
# Event types (stable contract)
# ---------------------------------------------------------------------------
VALID_EVENT_TYPES = {
    'run_started', 'run_finished',
    'action_started', 'action_finished',
    'tool_call', 'tool_result',
    'llm_call',
    'error', 'metric', 'heartbeat',
}

EVENT_STATUS_VALUES = {'success', 'error', 'info'}


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------
_pricing_cache = {}
_pricing_cache_ts = 0
PRICING_CACHE_TTL = 300  # 5 minutes


def _load_pricing():
    global _pricing_cache, _pricing_cache_ts
    now = time.time()
    if _pricing_cache and (now - _pricing_cache_ts) < PRICING_CACHE_TTL:
        return _pricing_cache

    today = date.today()
    rows = ObsLlmPricing.query.filter(
        ObsLlmPricing.effective_from <= today,
        db.or_(ObsLlmPricing.effective_to.is_(None), ObsLlmPricing.effective_to >= today),
    ).all()

    cache = {}
    for r in rows:
        cache[(r.provider, r.model)] = (float(r.input_cost_per_mtok), float(r.output_cost_per_mtok))

    _pricing_cache = cache
    _pricing_cache_ts = now
    return cache


def calculate_cost(provider, model, tokens_in, tokens_out):
    """Return estimated cost in USD (float). Returns 0 if pricing not found."""
    pricing = _load_pricing()
    key = (provider, model)
    if key not in pricing:
        # Try prefix match (e.g. "gpt-4o-mini" matches "gpt-4o-mini")
        for (p, m), costs in pricing.items():
            if p == provider and model and model.startswith(m):
                key = (p, m)
                break
        else:
            return 0.0

    input_cost_per_mtok, output_cost_per_mtok = pricing[key]
    cost = ((tokens_in or 0) * input_cost_per_mtok + (tokens_out or 0) * output_cost_per_mtok) / 1_000_000
    return round(cost, 8)


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

def emit_event(user_id, event_type, status='info', agent_id=None, run_id=None,
               model=None, tokens_in=None, tokens_out=None, cost_usd=None,
               latency_ms=None, payload=None, dedupe_key=None):
    """Write a single event. Never raises — swallows errors to avoid blocking callers."""
    try:
        if cost_usd is None and tokens_in and model:
            # Try to auto-calculate cost from payload provider or model
            provider = (payload or {}).get('provider', '')
            cost_usd = calculate_cost(provider, model, tokens_in, tokens_out)

        event = ObsEvent(
            uid=str(uuid.uuid4()),
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            event_type=event_type,
            status=status,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=Decimal(str(cost_usd)) if cost_usd else None,
            latency_ms=latency_ms,
            payload=payload or {},
            dedupe_key=dedupe_key,
        )
        db.session.add(event)
        db.session.commit()
        return event
    except Exception as e:
        db.session.rollback()
        print(f"[obs] Failed to emit {event_type}: {e}")
        return None


def emit_event_batch(events_data, user_id):
    """Write a batch of events. Returns (accepted_count, rejected list)."""
    accepted = 0
    rejected = []

    for i, ev in enumerate(events_data):
        try:
            # Validate required fields
            etype = ev.get('event_type', '')
            if etype not in VALID_EVENT_TYPES:
                rejected.append({'index': i, 'reason': f'invalid event_type: {etype}'})
                continue

            estatus = ev.get('status', 'info')
            if estatus not in EVENT_STATUS_VALUES:
                estatus = 'info'

            tokens_in = ev.get('tokens_in')
            tokens_out = ev.get('tokens_out')
            model = ev.get('model')
            cost_usd = ev.get('cost_usd')
            provider = ev.get('payload', {}).get('provider', '')

            if cost_usd is None and tokens_in and model and provider:
                cost_usd = calculate_cost(provider, model, tokens_in, tokens_out)

            event = ObsEvent(
                uid=ev.get('id') or str(uuid.uuid4()),
                user_id=user_id,
                agent_id=ev.get('agent_id'),
                run_id=ev.get('run_id'),
                event_type=etype,
                status=estatus,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=Decimal(str(cost_usd)) if cost_usd else None,
                latency_ms=ev.get('latency_ms'),
                payload=ev.get('payload', {}),
                dedupe_key=ev.get('dedupe_key'),
            )
            db.session.add(event)
            accepted += 1

        except Exception as e:
            rejected.append({'index': i, 'reason': str(e)})

    if accepted > 0:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # On bulk commit failure, likely a dedupe conflict — fall back to one-by-one
            return _commit_one_by_one(events_data, user_id)

    return accepted, rejected


def _commit_one_by_one(events_data, user_id):
    """Fallback: insert events individually to isolate dedupe conflicts."""
    accepted = 0
    rejected = []
    for i, ev in enumerate(events_data):
        try:
            result = emit_event(
                user_id=user_id,
                event_type=ev.get('event_type', 'metric'),
                status=ev.get('status', 'info'),
                agent_id=ev.get('agent_id'),
                run_id=ev.get('run_id'),
                model=ev.get('model'),
                tokens_in=ev.get('tokens_in'),
                tokens_out=ev.get('tokens_out'),
                cost_usd=ev.get('cost_usd'),
                latency_ms=ev.get('latency_ms'),
                payload=ev.get('payload'),
                dedupe_key=ev.get('dedupe_key'),
            )
            if result:
                accepted += 1
            else:
                rejected.append({'index': i, 'reason': 'write failed (possible dedupe conflict)'})
        except Exception as e:
            rejected.append({'index': i, 'reason': str(e)})
    return accepted, rejected


# ---------------------------------------------------------------------------
# Run tracking
# ---------------------------------------------------------------------------

def start_run(user_id, agent_id=None, model=None, metadata=None):
    """Create a new run, emit run_started event. Returns run_id."""
    rid = str(uuid.uuid4())
    try:
        run = ObsRun(
            run_id=rid,
            user_id=user_id,
            agent_id=agent_id,
            model=model,
            metadata_json=metadata or {},
        )
        db.session.add(run)
        db.session.commit()

        emit_event(user_id, 'run_started', status='info', agent_id=agent_id,
                   run_id=rid, model=model, payload={'metadata': metadata or {}})
    except Exception as e:
        db.session.rollback()
        print(f"[obs] start_run failed: {e}")
    return rid


def finish_run(run_id, status='success', error_message=None,
               tokens_in=0, tokens_out=0, cost_usd=0, latency_ms=0, tool_calls=0):
    """Finalize a run, emit run_finished event."""
    try:
        run = ObsRun.query.filter_by(run_id=run_id).first()
        if not run:
            return
        run.status = status
        run.error_message = error_message
        run.total_tokens_in = (run.total_tokens_in or 0) + tokens_in
        run.total_tokens_out = (run.total_tokens_out or 0) + tokens_out
        run.total_cost_usd = Decimal(str(float(run.total_cost_usd or 0) + float(cost_usd or 0)))
        run.total_latency_ms = (run.total_latency_ms or 0) + latency_ms
        run.tool_calls_count = (run.tool_calls_count or 0) + tool_calls
        run.finished_at = datetime.utcnow()
        db.session.commit()

        emit_event(run.user_id, 'run_finished', status=status,
                   agent_id=run.agent_id, run_id=run_id,
                   model=run.model,
                   tokens_in=run.total_tokens_in,
                   tokens_out=run.total_tokens_out,
                   cost_usd=float(run.total_cost_usd),
                   latency_ms=run.total_latency_ms,
                   payload={'error': error_message} if error_message else {})
    except Exception as e:
        db.session.rollback()
        print(f"[obs] finish_run failed: {e}")


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_daily(target_date=None):
    """Aggregate obs_events for target_date into obs_agent_daily_metrics. Returns rows upserted."""
    if target_date is None:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    # Get distinct (user_id, agent_id) pairs for the day
    pairs = db.session.query(
        ObsEvent.user_id, ObsEvent.agent_id
    ).filter(
        ObsEvent.created_at >= day_start,
        ObsEvent.created_at < day_end,
    ).distinct().all()

    count = 0
    for user_id, agent_id in pairs:
        try:
            _aggregate_one(user_id, agent_id, target_date, day_start, day_end)
            count += 1
        except Exception as e:
            db.session.rollback()
            print(f"[obs] aggregate failed for user={user_id} agent={agent_id}: {e}")

    return count


def _aggregate_one(user_id, agent_id, target_date, day_start, day_end):
    """Aggregate for a single (user, agent, day) tuple."""
    base_q = ObsEvent.query.filter(
        ObsEvent.user_id == user_id,
        ObsEvent.created_at >= day_start,
        ObsEvent.created_at < day_end,
    )
    if agent_id is not None:
        base_q = base_q.filter(ObsEvent.agent_id == agent_id)
    else:
        base_q = base_q.filter(ObsEvent.agent_id.is_(None))

    events = base_q.all()
    if not events:
        return

    run_events = [e for e in events if e.event_type == 'run_finished']
    llm_events = [e for e in events if e.event_type == 'llm_call']
    tool_events = [e for e in events if e.event_type in ('tool_call', 'tool_result')]
    heartbeat_events = [e for e in events if e.event_type == 'heartbeat']

    total_runs = len(run_events)
    successful_runs = len([e for e in run_events if e.status == 'success'])
    failed_runs = len([e for e in run_events if e.status == 'error'])

    total_tokens_in = sum(e.tokens_in or 0 for e in events)
    total_tokens_out = sum(e.tokens_out or 0 for e in events)
    total_cost = sum(float(e.cost_usd or 0) for e in events)

    total_tool_calls = len([e for e in tool_events if e.event_type == 'tool_call'])
    tool_errors = len([e for e in tool_events if e.status == 'error'])

    # Latency percentiles from LLM call events
    latencies = sorted([e.latency_ms for e in llm_events if e.latency_ms])
    latency_p50 = _percentile(latencies, 50) if latencies else None
    latency_p95 = _percentile(latencies, 95) if latencies else None
    latency_avg = int(sum(latencies) / len(latencies)) if latencies else None

    # Models used
    models = {}
    for e in llm_events:
        if e.model:
            models[e.model] = models.get(e.model, 0) + 1

    last_hb = max((e.created_at for e in heartbeat_events), default=None)

    # Upsert
    existing = ObsAgentDailyMetrics.query.filter_by(
        user_id=user_id, agent_id=agent_id, date=target_date
    ).first()

    if existing:
        m = existing
    else:
        m = ObsAgentDailyMetrics(user_id=user_id, agent_id=agent_id, date=target_date)
        db.session.add(m)

    m.total_runs = total_runs
    m.successful_runs = successful_runs
    m.failed_runs = failed_runs
    m.total_events = len(events)
    m.total_tokens_in = total_tokens_in
    m.total_tokens_out = total_tokens_out
    m.total_cost_usd = Decimal(str(round(total_cost, 8)))
    m.total_tool_calls = total_tool_calls
    m.tool_errors = tool_errors
    m.latency_p50_ms = latency_p50
    m.latency_p95_ms = latency_p95
    m.latency_avg_ms = latency_avg
    m.models_used = models
    m.last_heartbeat_at = last_hb

    db.session.commit()


def _percentile(sorted_list, pct):
    if not sorted_list:
        return None
    idx = int(len(sorted_list) * pct / 100)
    idx = min(idx, len(sorted_list) - 1)
    return sorted_list[idx]


# ---------------------------------------------------------------------------
# Alert evaluation
# ---------------------------------------------------------------------------

def evaluate_alerts():
    """Check all enabled alert rules. Returns count of alerts fired."""
    rules = ObsAlertRule.query.filter_by(is_enabled=True).all()
    fired = 0
    now = datetime.utcnow()

    for rule in rules:
        try:
            # Cooldown check
            if rule.last_triggered_at:
                cooldown_end = rule.last_triggered_at + timedelta(minutes=rule.cooldown_minutes)
                if now < cooldown_end:
                    continue

            metric_value = _evaluate_rule_metric(rule, now)
            if metric_value is None:
                continue

            threshold = float(rule.threshold)

            if metric_value > threshold:
                _fire_alert(rule, metric_value, threshold, now)
                fired += 1

        except Exception as e:
            print(f"[obs] alert eval failed rule={rule.id}: {e}")

    return fired


def _evaluate_rule_metric(rule, now):
    """Compute current metric value for a rule. Returns float or None."""
    if rule.rule_type == 'cost_per_day':
        today = now.date()
        q = db.session.query(db.func.sum(ObsEvent.cost_usd)).filter(
            ObsEvent.user_id == rule.user_id,
            ObsEvent.created_at >= datetime.combine(today, datetime.min.time()),
        )
        if rule.agent_id:
            q = q.filter(ObsEvent.agent_id == rule.agent_id)
        result = q.scalar()
        return float(result) if result else 0.0

    elif rule.rule_type == 'error_rate':
        window_start = now - timedelta(minutes=rule.window_minutes)
        q = ObsEvent.query.filter(
            ObsEvent.user_id == rule.user_id,
            ObsEvent.created_at >= window_start,
            ObsEvent.event_type == 'run_finished',
        )
        if rule.agent_id:
            q = q.filter(ObsEvent.agent_id == rule.agent_id)
        runs = q.all()
        if not runs:
            return None  # No data — don't alert
        errors = len([r for r in runs if r.status == 'error'])
        return (errors / len(runs)) * 100  # percentage

    elif rule.rule_type == 'no_heartbeat':
        q = ObsEvent.query.filter(
            ObsEvent.user_id == rule.user_id,
            ObsEvent.event_type == 'heartbeat',
        )
        if rule.agent_id:
            q = q.filter(ObsEvent.agent_id == rule.agent_id)
        last = q.order_by(ObsEvent.created_at.desc()).first()
        if not last:
            return float(rule.threshold) + 1  # No heartbeat ever → trigger
        minutes_since = (now - last.created_at).total_seconds() / 60
        return minutes_since

    return None


def _fire_alert(rule, metric_value, threshold, now):
    """Record alert event and send notifications."""
    message = _build_alert_message(rule, metric_value, threshold)

    alert_event = ObsAlertEvent(
        rule_id=rule.id,
        user_id=rule.user_id,
        agent_id=rule.agent_id,
        metric_value=Decimal(str(round(metric_value, 4))),
        threshold_value=Decimal(str(threshold)),
        rule_type=rule.rule_type,
        message=message,
    )
    db.session.add(alert_event)
    rule.last_triggered_at = now
    db.session.commit()

    print(f"[obs] ALERT FIRED: {message}")

    # Slack notification
    slack_url = os.environ.get('SLACK_WEBHOOK_URL')
    if slack_url:
        try:
            http_requests.post(slack_url, json={'text': message}, timeout=5)
            alert_event.notified_slack = True
            db.session.commit()
        except Exception as e:
            print(f"[obs] Slack notification failed: {e}")


def _build_alert_message(rule, metric_value, threshold):
    agent_label = f"agent #{rule.agent_id}" if rule.agent_id else "workspace"
    if rule.rule_type == 'cost_per_day':
        return f"Alert '{rule.name}': {agent_label} daily cost ${metric_value:.4f} exceeds ${threshold:.4f} threshold"
    elif rule.rule_type == 'error_rate':
        return f"Alert '{rule.name}': {agent_label} error rate {metric_value:.1f}% exceeds {threshold:.1f}% threshold"
    elif rule.rule_type == 'no_heartbeat':
        return f"Alert '{rule.name}': {agent_label} no heartbeat for {metric_value:.0f} minutes (threshold: {threshold:.0f}m)"
    return f"Alert '{rule.name}': metric {metric_value} > threshold {threshold}"
