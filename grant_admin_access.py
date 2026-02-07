#!/usr/bin/env python3
"""
Script to grant admin access to d.chosen.juan.1@gmail.com

Run this after the database migration is complete:
    python3 grant_admin_access.py
"""
import os
from models import db, User
from server import app

def grant_admin():
    """Grant admin access and team tier to specified user"""
    with app.app_context():
        # Target email
        email = 'd.chosen.juan.1@gmail.com'

        # Find user
        user = User.query.filter_by(email=email).first()

        if user:
            # Grant admin access
            user.is_admin = True
            user.subscription_tier = 'team'
            db.session.commit()

            print(f"✅ Admin access granted!")
            print(f"   Email: {user.email}")
            print(f"   Admin: {user.is_admin}")
            print(f"   Tier: {user.subscription_tier}")
        else:
            print(f"❌ User not found: {email}")
            print(f"   The user needs to login at least once first.")
            print(f"   Go to https://www.greenmonkey.dev and request a magic link.")

if __name__ == '__main__':
    # Check if DATABASE_URL is set
    if not os.environ.get('DATABASE_URL'):
        print("❌ DATABASE_URL environment variable not set!")
        print("\nSet it first:")
        print('export DATABASE_URL="postgresql://neondb_owner:...@...neon.tech/neondb?sslmode=require"')
        exit(1)

    grant_admin()
