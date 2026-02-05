"""
Migration script to add is_admin column to existing User table
Run this once to upgrade existing databases to support admin roles
"""
from server import app
from models import db
import os

def migrate_add_admin_column():
    """Add is_admin column to users table if it doesn't exist"""
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='users' AND column_name='is_admin'"
            )

            if result.fetchone():
                print("✅ is_admin column already exists, no migration needed")
                return

            # Add the column
            print("📝 Adding is_admin column to users table...")
            db.session.execute(
                "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"
            )

            # Create index on is_admin for faster queries
            print("📝 Creating index on is_admin column...")
            db.session.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin)"
            )

            # Make owner email admin if set
            owner_email = os.environ.get('OWNER_EMAIL', '').strip().lower()
            if owner_email:
                print(f"📝 Promoting owner email to admin: {owner_email}")
                db.session.execute(
                    "UPDATE users SET is_admin = TRUE WHERE email = :email",
                    {'email': owner_email}
                )
                updated = db.session.execute(
                    "SELECT COUNT(*) FROM users WHERE is_admin = TRUE"
                ).scalar()
                print(f"✅ {updated} user(s) promoted to admin")

            db.session.commit()
            print("✅ Migration completed successfully!")

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate_add_admin_column()
