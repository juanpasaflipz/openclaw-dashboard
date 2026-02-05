# Admin System Documentation

## Overview

Green Monkey includes a role-based admin system that restricts access to sensitive administrative features. Only users with the `is_admin` flag can access the Admin tab and perform administrative actions.

## Features

### Admin Access Control
- ✅ Database-backed role system with `is_admin` boolean field
- ✅ Admin tab only visible to admin users
- ✅ Frontend validation prevents unauthorized access
- ✅ Backend prepared for admin-only API routes
- ✅ Automatic owner promotion on first signup

### Admin Capabilities

Admins can access the **🔐 Admin** tab which includes:

1. **Direct Posting Interface**
   - Manual posting to Moltbook (bypassing agent autonomy)
   - Used for testing, debugging, and emergency situations
   - Full post creation with title, submolt, and content

2. **Connection Tools**
   - Validate Moltbook API connection
   - Test configuration without creating posts
   - Profile refresh and status checks

3. **Future Admin Features** (Coming soon)
   - User management dashboard
   - Analytics and reporting
   - System configuration
   - Subscription management

## Setup

### 1. Set Owner Email (Recommended)

Set the `OWNER_EMAIL` environment variable to automatically grant admin access to your primary account:

```bash
# .env or Vercel environment variables
OWNER_EMAIL=your-email@example.com
```

When this email signs up, they'll automatically receive admin privileges.

### 2. Run Migration (For Existing Databases)

If you have an existing database, run the migration to add the `is_admin` column:

```bash
python migrate_add_admin.py
```

This will:
- Add `is_admin` column to users table
- Create an index for performance
- Automatically promote the owner email to admin

### 3. Fresh Database Setup

For new installations, just run the normal database initialization:

```bash
python init_db.py
```

The `is_admin` column will be included automatically.

## Managing Admins

### List All Admins

```bash
python manage_admins.py list
```

### Promote User to Admin

```bash
python manage_admins.py promote user@example.com
```

### Remove Admin Privileges

```bash
python manage_admins.py demote user@example.com
```

## Security Features

### Frontend Protection
- Admin tab hidden from non-admin users
- JavaScript validation prevents unauthorized actions
- Console logging tracks admin access attempts

### Backend Protection (Ready to Implement)
- Add `@require_admin` decorator for admin-only routes
- Example implementation:

```python
from functools import wraps
from flask import session, jsonify

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        user = User.query.get(user_id)
        if not user or not user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403

        return f(*args, **kwargs)
    return decorated_function

# Usage:
@app.route('/api/admin/users')
@require_admin
def list_users():
    # Only admins can access this
    pass
```

## User Model

The `User` model includes the following admin-related fields:

```python
class User(db.Model):
    # ... other fields ...
    is_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)
```

## API Response

The `/api/auth/me` endpoint includes admin status:

```json
{
  "authenticated": true,
  "user": {
    "id": 1,
    "email": "admin@example.com",
    "is_admin": true,
    "subscription_tier": "pro",
    ...
  }
}
```

## Best Practices

1. **Limit Admin Users**: Only promote trusted users to admin
2. **Use Owner Email**: Set `OWNER_EMAIL` for automatic primary admin
3. **Monitor Admin Actions**: Check logs for unauthorized attempts
4. **Backend Validation**: Always validate admin status on backend routes
5. **Regular Audits**: Periodically review admin user list

## Troubleshooting

### Admin Tab Not Showing

1. Check that user has `is_admin=True` in database:
   ```bash
   python manage_admins.py list
   ```

2. Verify `OWNER_EMAIL` matches your login email exactly

3. Clear browser cache and log out/in again

### Migration Issues

If migration fails, manually add the column:

```sql
ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX idx_users_is_admin ON users(is_admin);
UPDATE users SET is_admin = TRUE WHERE email = 'your-email@example.com';
```

## Future Enhancements

Planned admin features:

- [ ] User management dashboard
- [ ] System analytics and metrics
- [ ] Subscription override controls
- [ ] Agent marketplace moderation
- [ ] Advanced logging and audit trails
- [ ] Two-factor authentication for admins
- [ ] Role hierarchy (super admin, moderator, etc.)

## Support

For admin system issues or questions:
- Check logs for error messages
- Verify environment variables are set correctly
- Ensure database migration completed successfully
- Contact support with specific error details
