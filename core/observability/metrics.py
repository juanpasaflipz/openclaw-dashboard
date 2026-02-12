"""
Daily aggregation — aggregate_daily(), percentile computation.
"""
from datetime import datetime, date, timedelta
from decimal import Decimal


def aggregate_daily(target_date=None):
    """Aggregate obs_events for target_date into obs_agent_daily_metrics. Returns rows upserted."""
    from models import db, ObsEvent, ObsAgentDailyMetrics

    if target_date is None:
        from datetime import datetime as _dt
        target_date = _dt.utcnow().date()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

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
            from models import db as _db
            _db.session.rollback()
            print(f"[obs] aggregate failed for user={user_id} agent={agent_id}: {e}")

    return count


def _aggregate_one(user_id, agent_id, target_date, day_start, day_end):
    """Aggregate for a single (user, agent, day) tuple."""
    from models import db, ObsEvent, ObsAgentDailyMetrics

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
    total_cost = sum(Decimal(str(e.cost_usd or 0)) for e in events)

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
    m.total_cost_usd = total_cost.quantize(Decimal('0.00000001'))
    m.total_tool_calls = total_tool_calls
    m.tool_errors = tool_errors
    m.latency_p50_ms = latency_p50
    m.latency_p95_ms = latency_p95
    m.latency_avg_ms = latency_avg
    m.models_used = models
    m.last_heartbeat_at = last_hb

    db.session.commit()


def _percentile(sorted_list, pct):
    """Compute the pct-th percentile from a pre-sorted list."""
    if not sorted_list:
        return None
    idx = int(len(sorted_list) * pct / 100)
    idx = min(idx, len(sorted_list) - 1)
    return sorted_list[idx]
