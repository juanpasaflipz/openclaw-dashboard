"""
Generate 24 hours of synthetic observability events (fast-forward).

Usage:
    python scripts/generate_demo_events.py [--user-id N] [--hours 24]

Requires: seed_observability.py to have been run first.
"""
import sys
import random
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
from server import app
from models import db, User, Agent, ObsEvent, ObsRun


# Simulation parameters
MODELS = [
    ('openai', 'gpt-4o', (800, 3000), (200, 1500), (300, 2000)),
    ('openai', 'gpt-4o-mini', (500, 2000), (100, 800), (80, 500)),
    ('anthropic', 'claude-sonnet-4-5-20250929', (1000, 4000), (300, 2000), (400, 3000)),
    ('groq', 'llama-3.3-70b-versatile', (600, 2500), (150, 1000), (100, 600)),
    ('google', 'gemini-2.0-flash', (400, 1800), (100, 600), (50, 300)),
]

TOOLS = [
    'send_email', 'search_web', 'read_file', 'create_task',
    'post_slack_message', 'query_database', 'summarize_url',
]

ERROR_MESSAGES = [
    'Rate limit exceeded (429)',
    'Context window exceeded',
    'Tool execution timeout after 30s',
    'API key invalid or expired',
    'Connection refused to external service',
]


def generate_events(user_id, agent_ids, hours=24):
    """Generate synthetic events spanning `hours` of activity."""
    now = datetime.utcnow()
    start = now - timedelta(hours=hours)

    total_events = 0
    total_runs = 0

    # Distribute runs across the time window
    runs_per_hour = random.randint(3, 8)
    total_planned_runs = runs_per_hour * hours

    print(f"  Generating ~{total_planned_runs} runs across {hours} hours...")

    for run_idx in range(total_planned_runs):
        # Pick a random time within the window
        offset_seconds = random.randint(0, hours * 3600)
        run_start = start + timedelta(seconds=offset_seconds)

        agent_id = random.choice(agent_ids)
        provider, model, tok_in_range, tok_out_range, latency_range = random.choice(MODELS)

        run_id = str(uuid.uuid4())
        is_error = random.random() < 0.08  # 8% error rate

        # Create run record
        run = ObsRun(
            run_id=run_id,
            user_id=user_id,
            agent_id=agent_id,
            model=model,
            status='running',
            started_at=run_start,
        )
        db.session.add(run)

        # run_started event
        db.session.add(ObsEvent(
            uid=str(uuid.uuid4()),
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            event_type='run_started',
            status='info',
            model=model,
            payload={'provider': provider},
            created_at=run_start,
        ))
        total_events += 1

        # 1-3 LLM calls per run
        llm_calls = random.randint(1, 3)
        cumulative_ms = 0
        run_tokens_in = 0
        run_tokens_out = 0
        run_cost = 0.0

        for llm_idx in range(llm_calls):
            tokens_in = random.randint(*tok_in_range)
            tokens_out = random.randint(*tok_out_range)
            latency_ms = random.randint(*latency_range)
            cumulative_ms += latency_ms

            # Simple cost estimate
            cost = round((tokens_in * 3.0 + tokens_out * 15.0) / 1_000_000, 6)
            run_tokens_in += tokens_in
            run_tokens_out += tokens_out
            run_cost += cost

            call_time = run_start + timedelta(milliseconds=cumulative_ms)

            llm_status = 'error' if (is_error and llm_idx == llm_calls - 1) else 'success'

            db.session.add(ObsEvent(
                uid=str(uuid.uuid4()),
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                event_type='llm_call',
                status=llm_status,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=Decimal(str(cost)),
                latency_ms=latency_ms,
                payload={'provider': provider, 'call_index': llm_idx},
                created_at=call_time,
            ))
            total_events += 1

        # 0-3 tool calls per run
        num_tools = random.randint(0, 3)
        for tool_idx in range(num_tools):
            tool_name = random.choice(TOOLS)
            tool_latency = random.randint(50, 5000)
            cumulative_ms += tool_latency
            tool_time = run_start + timedelta(milliseconds=cumulative_ms)
            tool_error = random.random() < 0.05  # 5% tool failure

            db.session.add(ObsEvent(
                uid=str(uuid.uuid4()),
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                event_type='tool_call',
                status='error' if tool_error else 'success',
                latency_ms=tool_latency,
                payload={
                    'tool': tool_name,
                    'error': random.choice(ERROR_MESSAGES) if tool_error else None,
                },
                created_at=tool_time,
            ))
            total_events += 1

        # run_finished event
        finish_time = run_start + timedelta(milliseconds=cumulative_ms + random.randint(10, 100))
        final_status = 'error' if is_error else 'success'

        run.status = final_status
        run.total_tokens_in = run_tokens_in
        run.total_tokens_out = run_tokens_out
        run.total_cost_usd = Decimal(str(round(run_cost, 6)))
        run.total_latency_ms = cumulative_ms
        run.tool_calls_count = num_tools
        run.finished_at = finish_time
        if is_error:
            run.error_message = random.choice(ERROR_MESSAGES)

        db.session.add(ObsEvent(
            uid=str(uuid.uuid4()),
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            event_type='run_finished',
            status=final_status,
            model=model,
            tokens_in=run_tokens_in,
            tokens_out=run_tokens_out,
            cost_usd=Decimal(str(round(run_cost, 6))),
            latency_ms=cumulative_ms,
            payload={
                'provider': provider,
                'error': run.error_message if is_error else None,
            },
            created_at=finish_time,
        ))
        total_events += 1
        total_runs += 1

        # Commit in batches to avoid memory issues
        if run_idx % 50 == 0:
            db.session.commit()

    # Sprinkle heartbeat events (every ~10 minutes per agent)
    for agent_id in agent_ids:
        heartbeat_time = start
        while heartbeat_time < now:
            db.session.add(ObsEvent(
                uid=str(uuid.uuid4()),
                user_id=user_id,
                agent_id=agent_id,
                event_type='heartbeat',
                status='info',
                payload={'agent_status': 'alive'},
                created_at=heartbeat_time,
            ))
            total_events += 1
            heartbeat_time += timedelta(minutes=random.randint(8, 12))

    db.session.commit()
    return total_runs, total_events


def main():
    parser = argparse.ArgumentParser(description='Generate demo observability events')
    parser.add_argument('--user-id', type=int, help='User ID (default: first user)')
    parser.add_argument('--hours', type=int, default=24, help='Hours of data to generate (default: 24)')
    args = parser.parse_args()

    print("=== Demo Event Generator ===\n")

    with app.app_context():
        if args.user_id:
            user = User.query.get(args.user_id)
        else:
            user = User.query.first()

        if not user:
            print("No user found. Run seed_observability.py first.")
            sys.exit(1)

        agents = Agent.query.filter_by(user_id=user.id, is_active=True).all()
        if not agents:
            print("No agents found. Run seed_observability.py first.")
            sys.exit(1)

        agent_ids = [a.id for a in agents]
        print(f"User: {user.email} (id={user.id})")
        print(f"Agents: {', '.join(f'{a.name} (id={a.id})' for a in agents)}")
        print(f"Timespan: {args.hours} hours\n")

        total_runs, total_events = generate_events(user.id, agent_ids, args.hours)

        print(f"\n  Total runs: {total_runs}")
        print(f"  Total events: {total_events}")

        # Trigger aggregation
        print("\n  Running daily aggregation...")
        from observability_service import aggregate_daily
        from datetime import date, timedelta as td
        today = date.today()
        count = 0
        for day_offset in range(args.hours // 24 + 1):
            target = today - td(days=day_offset)
            count += aggregate_daily(target)
        print(f"  Aggregated {count} agent-day rows")

        print("\n=== Done ===")
        print(f"Visit http://localhost:5000 and open the Observability tab to see the data.")


if __name__ == '__main__':
    main()
