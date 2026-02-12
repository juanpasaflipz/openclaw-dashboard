"""
Enforcement worker — orchestrates periodic evaluation and execution.

Never runs inside HTTP request cycles. Triggered by cron endpoint or manual call.
Runs evaluator first (detect breaches), then executor (apply interventions).
Each step is independent and can be called separately for testing.
"""
import time


# Maximum seconds per enforcement cycle (Vercel has 60s timeout).
MAX_CYCLE_SECONDS = 45


def run_enforcement_cycle(max_seconds=MAX_CYCLE_SECONDS):
    """Run one full evaluate-then-execute cycle.

    Args:
        max_seconds: Time budget for the full cycle.

    Returns:
        dict with summary: events_created, events_executed, elapsed_seconds.
    """
    start = time.monotonic()

    events_created = run_evaluation_only()

    elapsed = time.monotonic() - start
    remaining = max_seconds - elapsed
    if remaining < 2:
        return {
            'events_created': events_created,
            'events_executed': 0,
            'elapsed_seconds': round(time.monotonic() - start, 2),
            'truncated': True,
        }

    events_executed = run_execution_only()

    return {
        'events_created': events_created,
        'events_executed': events_executed,
        'elapsed_seconds': round(time.monotonic() - start, 2),
        'truncated': False,
    }


def run_evaluation_only():
    """Run evaluator only. Creates pending risk_events for breached policies.

    Returns:
        int: Count of new risk_events created.
    """
    from core.risk_engine.evaluator import evaluate_policies

    try:
        return evaluate_policies()
    except Exception as e:
        print(f"[risk] evaluation cycle failed: {e}")
        return 0


def run_execution_only():
    """Run executor only. Processes pending risk_events.

    Returns:
        int: Count of events executed.
    """
    from core.risk_engine.interventions import execute_pending_events

    try:
        return execute_pending_events()
    except Exception as e:
        print(f"[risk] execution cycle failed: {e}")
        return 0
