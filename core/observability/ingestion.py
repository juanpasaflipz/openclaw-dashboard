"""
Event ingestion — emit_event(), emit_event_batch().

Never raises to callers. All errors are swallowed and logged.
"""
import uuid
from decimal import Decimal

from core.observability.constants import VALID_EVENT_TYPES, EVENT_STATUS_VALUES
from core.observability.cost_engine import calculate_cost

# Cache whether obs tables exist
_obs_available = None


def _check_obs_tables():
    global _obs_available
    if _obs_available is not None:
        return _obs_available
    try:
        from models import db
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        _obs_available = 'obs_events' in inspector.get_table_names()
    except Exception:
        _obs_available = False
    return _obs_available


def emit_event(user_id, event_type, status='info', agent_id=None, run_id=None,
               model=None, tokens_in=None, tokens_out=None, cost_usd=None,
               latency_ms=None, payload=None, dedupe_key=None):
    """Write a single event. Never raises — swallows errors to avoid blocking callers."""
    if not _check_obs_tables():
        return None

    from models import db, ObsEvent

    try:
        if cost_usd is None and tokens_in and model:
            provider = (payload or {}).get('provider', '')
            cost_usd = float(calculate_cost(provider, model, tokens_in, tokens_out))

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
    if not _check_obs_tables():
        return 0, [{'index': i, 'reason': 'obs tables not available'} for i in range(len(events_data))]

    from models import db, ObsEvent

    accepted = 0
    rejected = []

    for i, ev in enumerate(events_data):
        try:
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
                cost_usd = float(calculate_cost(provider, model, tokens_in, tokens_out))

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
        except Exception:
            db.session.rollback()
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
