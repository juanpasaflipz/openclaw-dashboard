"""
Retention cleanup — delete events and runs past each workspace's retention window.

Hard-deletes ObsEvent and ObsRun rows older than (retention_days + grace_period).
The grace period (default 24 hours) ensures events aren't deleted before aggregation
has a chance to run.

Designed to be called from a cron endpoint or background job.
"""
from datetime import datetime, timedelta

GRACE_PERIOD_HOURS = 24


def cleanup_expired_events(max_seconds=50, batch_size=500):
    """Delete events and runs past each workspace's retention window.

    Processes workspaces one at a time. Stops early if max_seconds is reached
    (to stay within Vercel's 60s timeout).

    Returns dict with counts per workspace: {workspace_id: {events_deleted, runs_deleted}}.
    """
    import time
    from models import db, ObsEvent, ObsRun
    from sqlalchemy import func

    start = time.time()
    results = {}

    # Get all workspaces with events (distinct user_ids)
    workspace_ids = (
        db.session.query(ObsEvent.user_id)
        .distinct()
        .all()
    )

    for (workspace_id,) in workspace_ids:
        if time.time() - start > max_seconds:
            break

        cutoff = _get_cleanup_cutoff(workspace_id)
        if cutoff is None:
            continue

        events_deleted = 0
        runs_deleted = 0

        # Delete events in batches using subquery (SQLAlchemy doesn't allow .delete() with .limit())
        while True:
            if time.time() - start > max_seconds:
                break

            batch_ids = (
                db.session.query(ObsEvent.id)
                .filter(
                    ObsEvent.user_id == workspace_id,
                    ObsEvent.created_at < cutoff,
                )
                .limit(batch_size)
                .all()
            )
            if not batch_ids:
                break

            ids = [r[0] for r in batch_ids]
            deleted = (
                ObsEvent.query
                .filter(ObsEvent.id.in_(ids))
                .delete(synchronize_session=False)
            )
            db.session.commit()
            events_deleted += deleted

        # Delete expired runs in batches
        while True:
            if time.time() - start > max_seconds:
                break

            batch_ids = (
                db.session.query(ObsRun.id)
                .filter(
                    ObsRun.user_id == workspace_id,
                    ObsRun.started_at < cutoff,
                )
                .limit(batch_size)
                .all()
            )
            if not batch_ids:
                break

            ids = [r[0] for r in batch_ids]
            deleted = (
                ObsRun.query
                .filter(ObsRun.id.in_(ids))
                .delete(synchronize_session=False)
            )
            db.session.commit()
            runs_deleted += deleted

        if events_deleted > 0 or runs_deleted > 0:
            results[workspace_id] = {
                'events_deleted': events_deleted,
                'runs_deleted': runs_deleted,
            }

    return results


def _get_cleanup_cutoff(workspace_id):
    """Return the cutoff datetime for cleanup (retention + grace period).

    Returns None if no cleanup is needed (e.g., no tier config issue).
    """
    from core.observability.tier_enforcement import get_workspace_tier

    tier = get_workspace_tier(workspace_id)
    retention_days = tier['retention_days']

    # cutoff = now - retention_days - grace_period
    cutoff = datetime.utcnow() - timedelta(days=retention_days, hours=GRACE_PERIOD_HOURS)
    return cutoff


def get_retention_stats(workspace_id):
    """Return retention statistics for a workspace. Useful for dashboards.

    Returns dict with event_count, oldest_event, retention_days, cutoff.
    """
    from models import db, ObsEvent
    from core.observability.tier_enforcement import get_workspace_tier
    from sqlalchemy import func

    tier = get_workspace_tier(workspace_id)

    oldest = (
        db.session.query(func.min(ObsEvent.created_at))
        .filter(ObsEvent.user_id == workspace_id)
        .scalar()
    )

    total = ObsEvent.query.filter(ObsEvent.user_id == workspace_id).count()

    cutoff = _get_cleanup_cutoff(workspace_id)
    expired = ObsEvent.query.filter(
        ObsEvent.user_id == workspace_id,
        ObsEvent.created_at < cutoff,
    ).count() if cutoff else 0

    return {
        'workspace_id': workspace_id,
        'tier_name': tier['tier_name'],
        'retention_days': tier['retention_days'],
        'total_events': total,
        'expired_events': expired,
        'oldest_event': oldest.isoformat() if oldest else None,
        'cleanup_cutoff': cutoff.isoformat() if cutoff else None,
    }
