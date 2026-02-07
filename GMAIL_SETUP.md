# Gmail Integration Setup Guide

## ✅ What's Been Implemented

### Backend:
- ✅ `Superpower` database model for tracking connected services
- ✅ `oauth_routes.py` - Google OAuth flow (Gmail, Calendar, Drive)
- ✅ `gmail_routes.py` - Gmail API integration (read, send, labels)
- ✅ Database migration for Superpowers table
- ✅ Google API dependencies added to requirements.txt

### Frontend:
- ✅ **Connect tab** in dashboard with beautiful service cards
- ✅ Gmail connection flow with OAuth popup
- ✅ Connected services display
- ✅ Disconnect functionality
- ✅ Service status indicators

### API Endpoints Created:
- `GET  /api/oauth/google/start/<service>` - Start OAuth flow
- `GET  /api/oauth/google/callback` - OAuth callback handler
- `GET  /api/superpowers/list` - List connected services
- `POST /api/superpowers/<id>/disconnect` - Disconnect service
- `GET  /api/gmail/recent` - Get recent emails
- `GET  /api/gmail/email/<id>` - Get email details
- `POST /api/gmail/send` - Send email
- `GET  /api/gmail/labels` - Get Gmail labels

---

## 🔧 Setup Instructions

### 1. Install Dependencies
```bash
cd /Users/juanmac/Public/clawd
pip install -r requirements.txt --break-system-packages
```

### 2. Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Enable these APIs:
   - Gmail API
   - Google Calendar API (for future)
   - Google Drive API (for future)
4. Go to **APIs & Services** → **Credentials**
5. Click **Create Credentials** → **OAuth 2.0 Client ID**
6. Configure OAuth consent screen:
   - User Type: External
   - App name: GreenMonkey
   - User support email: your email
   - Developer contact: your email
   - Scopes: Add Gmail (readonly, send, labels)
7. Create OAuth Client ID:
   - Application type: Web application
   - Name: GreenMonkey Dashboard
   - Authorized redirect URIs:
     ```
     http://localhost:5000/api/oauth/google/callback
     https://www.greenmonkey.dev/api/oauth/google/callback
     ```
8. Copy the **Client ID** and **Client Secret**

### 3. Set Environment Variables

Add these to your Vercel environment variables:

```bash
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=https://www.greenmonkey.dev/api/oauth/google/callback
```

For local development, add to `.env`:
```bash
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:5000/api/oauth/google/callback
```

### 4. Run Database Migration

```bash
cd /Users/juanmac/Public/clawd
alembic upgrade head
```

### 5. Test Locally

```bash
python3 server.py
```

Then:
1. Go to http://localhost:5000
2. Login with your email
3. Click **Connect** tab
4. Click **Connect Gmail**
5. Authorize in popup
6. You should see "Connection Successful!"

---

## 🎯 What You Can Do Now

### Read Emails:
```bash
curl http://localhost:5000/api/gmail/recent \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"
```

### Send Email:
```bash
curl -X POST http://localhost:5000/api/gmail/send \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{
    "to": "someone@example.com",
    "subject": "Test from GreenMonkey",
    "body": "This email was sent by my AI agent!"
  }'
```

### Get Labels:
```bash
curl http://localhost:5000/api/gmail/labels \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"
```

---

## 🔐 Security Notes

**IMPORTANT:** The current implementation stores OAuth tokens **unencrypted** in the database. This is fine for MVP/testing but needs to be fixed before production with real users.

### To Add Encryption (Phase 2):
1. Implement the `CredentialVault` class from the plan
2. Set `ENCRYPTION_MASTER_KEY` environment variable
3. Update `oauth_routes.py` to encrypt tokens before storing
4. Update `gmail_routes.py` to decrypt tokens when using

---

## 🚀 Next Steps

1. **Test Gmail Integration** - Connect your Gmail and send a test email
2. **Add Calendar & Drive** - Follow same pattern as Gmail
3. **Build Agent Actions** - Let your agent read emails and draft replies
4. **Add Approval Queue** - Review actions before agent sends emails
5. **Implement Security Layer** - Encrypt tokens, add CSRF protection, audit logging

---

## 📝 Notes for Admin Access

To grant admin access to `d.chosen.juan.1@gmail.com`:

```python
# Run in Python shell or create a script
from models import db, User
from server import app

with app.app_context():
    user = User.query.filter_by(email='d.chosen.juan.1@gmail.com').first()
    if user:
        user.is_admin = True
        user.subscription_tier = 'team'
        db.session.commit()
        print(f"✅ Admin access granted to {user.email}")
    else:
        print("❌ User not found - needs to login first")
```

---

## 🎉 You're Ready!

Your dashboard now has **Gmail superpowers**! This is just the beginning. Next you can add:
- Google Calendar integration
- Google Drive integration
- Notion, Slack, GitHub, and more
- Automation workflows
- Agent templates
- Marketplace

**The foundation is built. Time to show the world!** 🚀
