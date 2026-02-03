# OpenClaw Dashboard - Deployment Guide

## 🚀 Quick Deployment to Vercel

### Prerequisites
1. **Stripe Account**: Sign up at [stripe.com](https://stripe.com)
2. **Email Service**: Choose SendGrid, Mailgun, or AWS SES
3. **Database**: Vercel Postgres, Supabase, or any PostgreSQL host
4. **GitHub Account**: For deployment via Vercel

### Step 1: Stripe Setup

1. **Create Stripe Account** at [dashboard.stripe.com](https://dashboard.stripe.com)

2. **Get API Keys**:
   - Go to Developers → API keys
   - Copy your `Secret key` (starts with `sk_test_` for test mode)
   - Copy your `Publishable key` (starts with `pk_test_`)

3. **Create Products** (Optional - or use dynamic pricing):
   ```bash
   # Run this to create products in Stripe
   stripe products create --name="Starter Pack - 50 Credits" --description="50 post credits"
   stripe prices create --product=prod_xxx --unit-amount=500 --currency=usd
   ```

4. **Setup Webhook**:
   - Go to Developers → Webhooks → Add endpoint
   - URL: `https://your-domain.vercel.app/api/stripe/webhook`
   - Events to listen for: `checkout.session.completed`
   - Copy the webhook signing secret (starts with `whsec_`)

### Step 2: Email Service Setup

#### Option A: SendGrid (Recommended - Free tier: 100 emails/day)

1. Sign up at [sendgrid.com](https://sendgrid.com)
2. Create an API key in Settings → API Keys
3. Verify your sender email/domain
4. Set `SENDGRID_API_KEY` in environment variables

#### Option B: Mailgun

1. Sign up at [mailgun.com](https://mailgun.com)
2. Get API key from Settings → API Security
3. Set `MAILGUN_API_KEY` and `MAILGUN_DOMAIN`

#### Option C: AWS SES

1. Set up AWS SES and verify domain
2. Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`

### Step 3: Database Setup

#### Option A: Vercel Postgres (Recommended)

1. Go to Vercel Dashboard → Storage → Create Database → Postgres
2. Copy the `POSTGRES_URL` connection string
3. Vercel will automatically set this as `DATABASE_URL`

#### Option B: Supabase

1. Create project at [supabase.com](https://supabase.com)
2. Go to Project Settings → Database
3. Copy connection string and set as `DATABASE_URL`

#### Option C: Railway/Render

1. Create PostgreSQL database on Railway or Render
2. Copy connection string
3. Set as `DATABASE_URL` environment variable

### Step 4: Deploy to Vercel

#### Via Vercel CLI:

```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy
cd openclaw-dashboard
vercel

# Follow prompts and set environment variables
```

#### Via GitHub:

1. Push code to GitHub
2. Go to [vercel.com](https://vercel.com)
3. Click "Import Project"
4. Select your GitHub repository
5. Set environment variables (see below)
6. Click "Deploy"

### Step 5: Environment Variables

Set these in Vercel Dashboard → Settings → Environment Variables:

```
SECRET_KEY=<generate-random-64-char-string>
BASE_URL=https://your-domain.vercel.app
DATABASE_URL=<your-postgres-connection-string>
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
SENDGRID_API_KEY=SG....
```

To generate SECRET_KEY:
```python
import secrets
print(secrets.token_hex(32))
```

### Step 6: Initialize Database

After first deployment:

```bash
# SSH into Vercel (or run locally against production DB)
vercel dev

# In another terminal:
python init_db.py
```

Or use Vercel's serverless function to initialize:
```bash
curl https://your-domain.vercel.app/api/admin/init-db
```

### Step 7: Test Payment Flow

1. Visit your deployed dashboard
2. Click "Login / Sign Up"
3. Enter email → Check for magic link
4. Click "Buy Credits"
5. Use Stripe test card: `4242 4242 4242 4242`
6. Verify credits are added to account

---

## 🛠️ Alternative: Deploy to Heroku

```bash
# Install Heroku CLI
brew install heroku/brew/heroku  # macOS
# or download from heroku.com

# Login
heroku login

# Create app
heroku create openclaw-dashboard

# Add PostgreSQL
heroku addons:create heroku-postgresql:mini

# Set environment variables
heroku config:set SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
heroku config:set STRIPE_SECRET_KEY=sk_test_...
heroku config:set STRIPE_WEBHOOK_SECRET=whsec_...
heroku config:set SENDGRID_API_KEY=SG...

# Deploy
git push heroku main

# Initialize database
heroku run python init_db.py

# Open app
heroku open
```

---

## 🔒 Security Checklist

- [ ] Set strong `SECRET_KEY` (64+ characters)
- [ ] Use environment variables for all secrets
- [ ] Enable HTTPS (automatic on Vercel/Heroku)
- [ ] Verify Stripe webhook signatures
- [ ] Set CORS origins in production
- [ ] Use test mode until fully tested
- [ ] Add rate limiting to auth endpoints
- [ ] Monitor failed login attempts
- [ ] Set up error logging (Sentry, etc.)

---

## 📊 Going Live (Production)

1. **Switch to Stripe Live Mode**:
   - Replace `sk_test_` with `sk_live_` keys
   - Update webhook endpoint with live credentials

2. **Email Service**:
   - Verify sender domain
   - Remove SendGrid sandbox mode
   - Set up proper email templates

3. **Database**:
   - Upgrade to paid plan for production
   - Set up backups
   - Enable connection pooling

4. **Monitoring**:
   - Set up Sentry or similar for error tracking
   - Monitor Stripe dashboard for failed payments
   - Track credit usage analytics

---

## 🆘 Troubleshooting

### Magic links not sending
- Check email service API key
- Verify sender email is verified
- Look at server logs for errors

### Stripe webhooks failing
- Verify webhook secret is correct
- Check webhook URL is accessible
- Review Stripe webhook logs

### Database connection errors
- Verify DATABASE_URL is correct
- Check if database is running
- Ensure firewall allows connections

### Credits not added after payment
- Check Stripe webhook logs
- Verify webhook endpoint is working
- Check database for transaction records

---

## 📞 Support

For issues or questions:
- GitHub Issues: [your-repo]/issues
- Email: support@your-domain.com
- Documentation: [your-docs-url]
