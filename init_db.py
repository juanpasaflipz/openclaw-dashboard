"""
Initialize the database with tables and seed data
"""
from server import app
from models import db, CreditPackage, SubscriptionPlan


def init_database():
    """Create all database tables"""
    with app.app_context():
        # Create tables
        db.create_all()
        print("✅ Database tables created successfully!")

        # Check if credit packages already exist
        if CreditPackage.query.first() is None:
            # Seed default credit packages
            packages = [
                CreditPackage(
                    name="Starter Pack",
                    credits=10,
                    price_cents=500,  # $5.00 ($0.50 per post)
                    stripe_price_id="price_starter_10"  # Will be updated with real Stripe ID
                ),
                CreditPackage(
                    name="Growth Pack",
                    credits=20,
                    price_cents=800,  # $8.00 ($0.40 per post - 20% savings)
                    stripe_price_id="price_growth_20"
                ),
                CreditPackage(
                    name="Pro Pack",
                    credits=35,
                    price_cents=1000,  # $10.00 ($0.29 per post - 40% savings)
                    stripe_price_id="price_pro_35"
                ),
            ]

            for package in packages:
                db.session.add(package)

            db.session.commit()
            print("✅ Seeded default credit packages:")
            for package in packages:
                print(f"   - {package.name}: {package.credits} credits for ${package.price_dollars:.2f}")
        else:
            print("ℹ️  Credit packages already exist, skipping seed.")

        # Seed subscription plans
        if SubscriptionPlan.query.first() is None:
            plans = [
                SubscriptionPlan(
                    tier='starter',
                    name='Starter Plan',
                    price_monthly_cents=900,  # $9/month
                    stripe_price_id='price_starter_monthly',
                    unlimited_posts=False,
                    max_agents=3,
                    scheduled_posting=True,
                    analytics=True,
                    api_access=False,
                    team_members=1,
                    priority_support=False
                ),
                SubscriptionPlan(
                    tier='pro',
                    name='Pro Plan',
                    price_monthly_cents=2900,  # $29/month
                    stripe_price_id='price_pro_monthly',
                    unlimited_posts=True,  # NO RATE LIMIT!
                    max_agents=5,
                    scheduled_posting=True,
                    analytics=True,
                    api_access=True,
                    team_members=1,
                    priority_support=True
                ),
                SubscriptionPlan(
                    tier='team',
                    name='Team Plan',
                    price_monthly_cents=7900,  # $79/month
                    stripe_price_id='price_team_monthly',
                    unlimited_posts=True,
                    max_agents=999,  # Unlimited
                    scheduled_posting=True,
                    analytics=True,
                    api_access=True,
                    team_members=5,
                    priority_support=True
                ),
            ]

            for plan in plans:
                db.session.add(plan)

            db.session.commit()
            print("✅ Seeded subscription plans:")
            for plan in plans:
                print(f"   - {plan.name}: ${plan.price_monthly_dollars:.2f}/month")
                print(f"     • Unlimited posts: {plan.unlimited_posts}")
                print(f"     • Max agents: {plan.max_agents}")
        else:
            print("ℹ️  Subscription plans already exist, skipping seed.")


if __name__ == '__main__':
    init_database()
