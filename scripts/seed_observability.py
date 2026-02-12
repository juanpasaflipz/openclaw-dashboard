"""
Seed observability data: LLM pricing table, sample API key, and test agents.

Usage:
    python scripts/seed_observability.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date
from server import app
from models import db, User, Agent, ObsApiKey, ObsLlmPricing


# Current LLM pricing as of 2025 (USD per 1M tokens)
LLM_PRICING = [
    # OpenAI
    ('openai', 'gpt-4o', 2.50, 10.00),
    ('openai', 'gpt-4o-mini', 0.15, 0.60),
    ('openai', 'gpt-4-turbo', 10.00, 30.00),
    ('openai', 'gpt-4', 30.00, 60.00),
    ('openai', 'gpt-3.5-turbo', 0.50, 1.50),
    # Anthropic
    ('anthropic', 'claude-sonnet-4-5-20250929', 3.00, 15.00),
    ('anthropic', 'claude-3-5-sonnet-20241022', 3.00, 15.00),
    ('anthropic', 'claude-3-5-haiku-20241022', 0.80, 4.00),
    ('anthropic', 'claude-3-opus-20240229', 15.00, 75.00),
    # Google
    ('google', 'gemini-2.0-flash', 0.10, 0.40),
    ('google', 'gemini-1.5-pro', 1.25, 5.00),
    ('google', 'gemini-1.5-flash', 0.075, 0.30),
    # Groq
    ('groq', 'llama-3.3-70b-versatile', 0.59, 0.79),
    ('groq', 'llama-3.1-8b-instant', 0.05, 0.08),
    ('groq', 'mixtral-8x7b-32768', 0.24, 0.24),
    ('groq', 'gemma2-9b-it', 0.20, 0.20),
    # Mistral
    ('mistral', 'mistral-large-latest', 2.00, 6.00),
    ('mistral', 'mistral-medium-latest', 2.70, 8.10),
    ('mistral', 'mistral-small-latest', 0.20, 0.60),
    # Together
    ('together', 'meta-llama/Llama-3.3-70B-Instruct-Turbo', 0.88, 0.88),
    ('together', 'mistralai/Mixtral-8x7B-Instruct-v0.1', 0.60, 0.60),
    # xAI
    ('xai', 'grok-3-fast', 5.00, 25.00),
    ('xai', 'grok-3-mini-fast', 0.30, 0.50),
    ('xai', 'grok-2-latest', 2.00, 10.00),
    # Cohere
    ('cohere', 'command-r-plus', 2.50, 10.00),
    ('cohere', 'command-r', 0.15, 0.60),
]


def seed_pricing():
    """Seed LLM pricing table."""
    today = date.today()
    added = 0
    for provider, model, input_cost, output_cost in LLM_PRICING:
        existing = ObsLlmPricing.query.filter_by(
            provider=provider, model=model, effective_from=today
        ).first()
        if existing:
            continue
        row = ObsLlmPricing(
            provider=provider,
            model=model,
            input_cost_per_mtok=input_cost,
            output_cost_per_mtok=output_cost,
            effective_from=today,
        )
        db.session.add(row)
        added += 1

    db.session.commit()
    print(f"  Pricing: {added} rows added ({len(LLM_PRICING)} total models)")


def seed_agents_and_key(user_id):
    """Seed 3 demo agents and an API key for the given user."""
    agents_data = [
        ('Content Writer', 'Writes blog posts and social media content', True),
        ('Research Assistant', 'Searches the web and summarizes findings', True),
        ('Code Reviewer', 'Reviews pull requests and suggests improvements', True),
    ]

    created_agents = []
    for name, desc, active in agents_data:
        existing = Agent.query.filter_by(user_id=user_id, name=name).first()
        if existing:
            created_agents.append(existing)
            continue
        agent = Agent(
            user_id=user_id,
            name=name,
            description=desc,
            is_active=active,
        )
        db.session.add(agent)
        db.session.flush()
        created_agents.append(agent)

    db.session.commit()
    print(f"  Agents: {len(created_agents)} agents ready")

    # Create API key
    existing_keys = ObsApiKey.query.filter_by(user_id=user_id, is_active=True).count()
    if existing_keys == 0:
        api_key, raw_key = ObsApiKey.create_for_user(user_id, name='demo-key')
        db.session.commit()
        print(f"  API Key created: {raw_key}")
        print(f"           prefix: {api_key.key_prefix}")
    else:
        print(f"  API Key: {existing_keys} active key(s) already exist")
        raw_key = None

    return created_agents, raw_key


def main():
    print("=== Observability Seed Script ===\n")

    with app.app_context():
        # 1. Seed pricing
        print("[1/3] Seeding LLM pricing...")
        seed_pricing()

        # 2. Find or create a user
        user = User.query.first()
        if not user:
            user = User(email='demo@openclaw.dev', credit_balance=100, subscription_tier='pro')
            db.session.add(user)
            db.session.commit()
            print(f"\n[2/3] Created demo user: {user.email} (id={user.id})")
        else:
            print(f"\n[2/3] Using existing user: {user.email} (id={user.id})")

        # 3. Seed agents + API key
        print("\n[3/3] Seeding agents and API key...")
        agents, raw_key = seed_agents_and_key(user.id)

        print(f"\n=== Done ===")
        print(f"User ID:    {user.id}")
        print(f"Agents:     {', '.join(a.name for a in agents)}")
        if raw_key:
            print(f"\nSave this API key (shown only once):")
            print(f"  {raw_key}")
            print(f"\nTest with:")
            print(f'  curl -X POST http://localhost:5000/api/obs/ingest/events \\')
            print(f'    -H "Authorization: Bearer {raw_key}" \\')
            print(f'    -H "Content-Type: application/json" \\')
            print(f'    -d \'{{"event_type":"heartbeat","agent_id":{agents[0].id}}}\'')


if __name__ == '__main__':
    main()
