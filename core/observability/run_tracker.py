"""
Run lifecycle tracking — start_run(), finish_run().
"""
import uuid
from datetime import datetime
from decimal import Decimal

from core.observability.ingestion import emit_event


def start_run(user_id, agent_id=None, model=None, metadata=None):
    """Create a new run, emit run_started event. Returns run_id."""
    from models import db, ObsRun

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
    from models import db, ObsRun

    try:
        run = ObsRun.query.filter_by(run_id=run_id).first()
        if not run:
            return
        run.status = status
        run.error_message = error_message

        # Accumulate with Decimal to avoid float drift
        run.total_tokens_in = (run.total_tokens_in or 0) + tokens_in
        run.total_tokens_out = (run.total_tokens_out or 0) + tokens_out
        run.total_cost_usd = Decimal(str(run.total_cost_usd or 0)) + Decimal(str(cost_usd or 0))
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
