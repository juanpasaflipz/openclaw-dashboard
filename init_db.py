"""
Initialize the database with tables and seed data
"""
from server import app
from models import db, CreditPackage


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
                    credits=50,
                    price_cents=500,  # $5.00
                    stripe_price_id="price_starter_50"  # Will be updated with real Stripe ID
                ),
                CreditPackage(
                    name="Growth Pack",
                    credits=150,
                    price_cents=1200,  # $12.00 (20% discount)
                    stripe_price_id="price_growth_150"
                ),
                CreditPackage(
                    name="Pro Pack",
                    credits=500,
                    price_cents=3500,  # $35.00 (30% discount)
                    stripe_price_id="price_pro_500"
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


if __name__ == '__main__':
    init_database()
