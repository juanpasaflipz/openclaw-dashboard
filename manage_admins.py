"""
Admin management utility
Promote or demote users to/from admin role
"""
from server import app
from models import db, User
import sys

def list_admins():
    """List all admin users"""
    with app.app_context():
        admins = User.query.filter_by(is_admin=True).all()
        if not admins:
            print("No admin users found")
            return

        print("Current admin users:")
        for admin in admins:
            print(f"  - {admin.email} (ID: {admin.id})")

def promote_to_admin(email):
    """Promote a user to admin"""
    with app.app_context():
        user = User.query.filter_by(email=email.lower().strip()).first()

        if not user:
            print(f"❌ User not found: {email}")
            return False

        if user.is_admin:
            print(f"ℹ️  User {email} is already an admin")
            return True

        user.is_admin = True
        db.session.commit()
        print(f"✅ Promoted {email} to admin")
        return True

def demote_from_admin(email):
    """Remove admin privileges from a user"""
    with app.app_context():
        user = User.query.filter_by(email=email.lower().strip()).first()

        if not user:
            print(f"❌ User not found: {email}")
            return False

        if not user.is_admin:
            print(f"ℹ️  User {email} is not an admin")
            return True

        user.is_admin = False
        db.session.commit()
        print(f"✅ Removed admin privileges from {email}")
        return True

def show_usage():
    """Show usage information"""
    print("""
Green Monkey Admin Management Utility

Usage:
    python manage_admins.py list                    - List all admins
    python manage_admins.py promote <email>         - Promote user to admin
    python manage_admins.py demote <email>          - Remove admin privileges

Examples:
    python manage_admins.py list
    python manage_admins.py promote user@example.com
    python manage_admins.py demote user@example.com
    """)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == 'list':
        list_admins()
    elif command == 'promote':
        if len(sys.argv) < 3:
            print("❌ Email required")
            show_usage()
            sys.exit(1)
        promote_to_admin(sys.argv[2])
    elif command == 'demote':
        if len(sys.argv) < 3:
            print("❌ Email required")
            show_usage()
            sys.exit(1)
        demote_from_admin(sys.argv[2])
    else:
        print(f"❌ Unknown command: {command}")
        show_usage()
        sys.exit(1)
