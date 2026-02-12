# 07 — Demo & Seed Scripts

## Prerequisites

```bash
pip install -r requirements.txt
cp .env.example .env.local  # Configure DATABASE_URL if needed
```

## Step 1: Run Migration

```bash
source venv/bin/activate  # if using virtualenv
cd /path/to/openclaw-dashboard

# For local SQLite (tables auto-created by Flask-SQLAlchemy):
python3 -c "from server import app; from models import db; app.app_context().__enter__(); db.create_all(); print('Done')"

# For production (Neon PostgreSQL), use Alembic:
alembic upgrade head
```

## Step 2: Seed Base Data

```bash
python3 scripts/seed_observability.py
```

This creates:
- **LLM pricing** for 25+ models across 8 providers
- **3 demo agents**: Content Writer, Research Assistant, Code Reviewer
- **1 API key** for ingestion (printed to stdout — save it!)

Example output:
```
=== Observability Seed Script ===

[1/3] Seeding LLM pricing...
  Pricing: 25 rows added (25 total models)

[2/3] Using existing user: demo@openclaw.dev (id=1)

[3/3] Seeding agents and API key...
  Agents: 3 agents ready
  API Key created: obsk_a3f1b2c4d5e6f7...

=== Done ===
Save this API key (shown only once):
  obsk_a3f1b2c4d5e6f7...
```

## Step 3: Generate Demo Events

```bash
python3 scripts/generate_demo_events.py
```

Options:
```bash
python3 scripts/generate_demo_events.py --hours 48      # 48 hours of data
python3 scripts/generate_demo_events.py --user-id 1     # Specific user
```

This generates:
- ~120-192 agent runs across 24 hours
- Each run has 1-3 LLM calls + 0-3 tool calls
- ~8% error rate, realistic latency distributions
- Heartbeat events every ~10 minutes per agent
- Automatic daily aggregation after generation

## Step 4: Start the Server

```bash
python3 server.py
```

Open http://localhost:5000, log in, and navigate to **Workbench > Observability**.

## Step 5: Test External Ingestion

Using the API key from Step 2:

```bash
# Single event
curl -X POST http://localhost:5000/api/obs/ingest/events \
  -H "Authorization: Bearer obsk_YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"heartbeat","agent_id":1}'

# Batch events
curl -X POST http://localhost:5000/api/obs/ingest/events \
  -H "Authorization: Bearer obsk_YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {"event_type":"llm_call","status":"success","agent_id":1,"model":"gpt-4o","tokens_in":1000,"tokens_out":500,"latency_ms":800},
      {"event_type":"tool_call","status":"success","agent_id":1,"latency_ms":200,"payload":{"tool":"search_web"}}
    ]
  }'
```

## Step 6: Trigger Aggregation Manually

```bash
# Aggregate daily metrics
curl -X POST http://localhost:5000/api/obs/internal/aggregate \
  -H "Content-Type: application/json" \
  -d '{"password":"YOUR_ADMIN_PASSWORD"}'

# Evaluate alert rules
curl -X POST http://localhost:5000/api/obs/internal/evaluate-alerts \
  -H "Content-Type: application/json" \
  -d '{"password":"YOUR_ADMIN_PASSWORD"}'
```

In production, these are triggered automatically by Vercel cron jobs (hourly and every 15 minutes respectively).
