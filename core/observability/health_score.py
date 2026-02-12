"""
Agent health score — deterministic composite score per agent.

Formula components (total 100 points):
- Success rate:   40 points — ratio of successful runs to total runs
- Latency:        25 points — p95 latency relative to thresholds
- Error bursts:   20 points — consecutive/clustered errors in short window
- Cost anomaly:   15 points — deviation from 7-day rolling average

Stored in obs_agent_health_daily table, exposed via API.
"""
import math
from datetime import datetime, date, timedelta
from decimal import Decimal

from core.observability.constants import (
    HEALTH_WEIGHT_SUCCESS_RATE,
    HEALTH_WEIGHT_LATENCY,
    HEALTH_WEIGHT_ERROR_BURST,
    HEALTH_WEIGHT_COST_ANOMALY,
    HEALTH_LATENCY_GOOD_MS,
    HEALTH_LATENCY_BAD_MS,
    HEALTH_ERROR_BURST_WINDOW_MINUTES,
    HEALTH_ERROR_BURST_THRESHOLD,
    HEALTH_COST_ANOMALY_STDDEV_MULTIPLIER,
)


def compute_agent_health(user_id, agent_id, target_date=None):
    """
    Compute and persist health score for an agent on target_date.
    Returns dict with score breakdown, or None if no data.
    """
    from models import db, ObsAgentDailyMetrics, ObsEvent, ObsAgentHealthDaily

    if target_date is None:
        target_date = datetime.utcnow().date()

    # Get today's metrics
    metrics = ObsAgentDailyMetrics.query.filter_by(
        user_id=user_id, agent_id=agent_id, date=target_date
    ).first()

    if not metrics or (metrics.total_runs or 0) == 0:
        return None

    # --- Component 1: Success Rate (40 pts) ---
    total = metrics.total_runs or 0
    success = metrics.successful_runs or 0
    success_rate = success / total if total > 0 else 0
    score_success = round(success_rate * HEALTH_WEIGHT_SUCCESS_RATE, 2)

    # --- Component 2: Latency (25 pts) ---
    p95 = metrics.latency_p95_ms
    if p95 is None:
        score_latency = float(HEALTH_WEIGHT_LATENCY)  # No data = assume good
    elif p95 <= HEALTH_LATENCY_GOOD_MS:
        score_latency = float(HEALTH_WEIGHT_LATENCY)
    elif p95 >= HEALTH_LATENCY_BAD_MS:
        score_latency = 0.0
    else:
        # Linear interpolation between good and bad
        ratio = (p95 - HEALTH_LATENCY_GOOD_MS) / (HEALTH_LATENCY_BAD_MS - HEALTH_LATENCY_GOOD_MS)
        score_latency = round(HEALTH_WEIGHT_LATENCY * (1 - ratio), 2)

    # --- Component 3: Error Bursts (20 pts) ---
    # Count errors in short window at end of day
    day_end = datetime.combine(target_date, datetime.min.time()) + timedelta(days=1)
    burst_start = day_end - timedelta(minutes=HEALTH_ERROR_BURST_WINDOW_MINUTES)

    burst_errors = ObsEvent.query.filter(
        ObsEvent.user_id == user_id,
        ObsEvent.agent_id == agent_id,
        ObsEvent.status == 'error',
        ObsEvent.created_at >= burst_start,
        ObsEvent.created_at < day_end,
    ).count()

    if burst_errors == 0:
        score_burst = float(HEALTH_WEIGHT_ERROR_BURST)
    elif burst_errors >= HEALTH_ERROR_BURST_THRESHOLD:
        score_burst = 0.0
    else:
        ratio = burst_errors / HEALTH_ERROR_BURST_THRESHOLD
        score_burst = round(HEALTH_WEIGHT_ERROR_BURST * (1 - ratio), 2)

    # --- Component 4: Cost Anomaly (15 pts) ---
    # Compare today's cost to 7-day rolling average
    week_ago = target_date - timedelta(days=7)
    history = ObsAgentDailyMetrics.query.filter(
        ObsAgentDailyMetrics.user_id == user_id,
        ObsAgentDailyMetrics.agent_id == agent_id,
        ObsAgentDailyMetrics.date >= week_ago,
        ObsAgentDailyMetrics.date < target_date,
    ).all()

    today_cost = float(metrics.total_cost_usd or 0)

    if not history or all(float(h.total_cost_usd or 0) == 0 for h in history):
        score_cost = float(HEALTH_WEIGHT_COST_ANOMALY)  # No history = assume normal
    else:
        costs = [float(h.total_cost_usd or 0) for h in history]
        avg = sum(costs) / len(costs)
        if avg == 0:
            score_cost = float(HEALTH_WEIGHT_COST_ANOMALY)
        else:
            variance = sum((c - avg) ** 2 for c in costs) / len(costs)
            stddev = math.sqrt(variance) if variance > 0 else 0
            threshold = avg + HEALTH_COST_ANOMALY_STDDEV_MULTIPLIER * max(stddev, avg * 0.1)

            if today_cost <= threshold:
                score_cost = float(HEALTH_WEIGHT_COST_ANOMALY)
            else:
                overshoot = (today_cost - threshold) / max(threshold, 0.001)
                score_cost = max(0.0, round(HEALTH_WEIGHT_COST_ANOMALY * (1 - min(overshoot, 1.0)), 2))

    # --- Total ---
    total_score = round(score_success + score_latency + score_burst + score_cost, 2)

    breakdown = {
        'success_rate': score_success,
        'latency': score_latency,
        'error_burst': score_burst,
        'cost_anomaly': score_cost,
    }

    # Persist
    existing = ObsAgentHealthDaily.query.filter_by(
        user_id=user_id, agent_id=agent_id, date=target_date
    ).first()

    if existing:
        h = existing
    else:
        h = ObsAgentHealthDaily(user_id=user_id, agent_id=agent_id, date=target_date)
        db.session.add(h)

    h.score = Decimal(str(total_score))
    h.success_rate_score = Decimal(str(score_success))
    h.latency_score = Decimal(str(score_latency))
    h.error_burst_score = Decimal(str(score_burst))
    h.cost_anomaly_score = Decimal(str(score_cost))
    h.details = breakdown

    db.session.commit()

    return {
        'score': total_score,
        'breakdown': breakdown,
        'date': target_date.isoformat(),
        'agent_id': agent_id,
    }


def compute_all_health_scores(user_id, target_date=None):
    """Compute health scores for all agents of a user. Returns list of results."""
    from models import Agent

    if target_date is None:
        target_date = datetime.utcnow().date()

    agents = Agent.query.filter_by(user_id=user_id, is_active=True).all()
    results = []
    for agent in agents:
        result = compute_agent_health(user_id, agent.id, target_date)
        if result:
            results.append(result)
    return results
