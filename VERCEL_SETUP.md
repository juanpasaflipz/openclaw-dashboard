# 🚀 Vercel Deployment Setup Guide

## Step 1: Get Your Stripe Keys

### 1.1 Create/Login to Stripe Account
- Go to [dashboard.stripe.com](https://dashboard.stripe.com/register)
- Sign up or log in

### 1.2 Get API Keys
1. Click **Developers** in the left sidebar
2. Click **API keys**
3. **IMPORTANT:** Make sure you're in **Test mode** (toggle in top right)
4. Copy these keys:
   - **Publishable key** (starts with `pk_test_...`)
   - **Secret key** (starts with `sk_test_...`) - Click "Reveal test key"

### 1.3 Set Up Webhook Endpoint
1. Still in **Developers** section, click **Webhooks**
2. Click **Add endpoint**
3. For **Endpoint URL**, enter: `https://your-app-name.vercel.app/api/stripe/webhook`
   - (You'll update this after deploying to Vercel)
4. Click **Select events** and choose: `checkout.session.completed`
5. Click **Add endpoint**
6. Click on the webhook you just created
7. Copy the **Signing secret** (starts with `whsec_...`)

**Note:** You'll need to create this webhook AFTER deploying to Vercel, since you need your actual domain.

---

## Step 2: Deploy to Vercel

### 2.1 Push to GitHub
```bash
cd /Users/juanmac/Public/clawd
git push origin main
```

### 2.2 Deploy on Vercel
1. Go to [vercel.com](https://vercel.com)
2. Sign in with GitHub
3. Click **Add New** → **Project**
4. Import your `openclaw-dashboard` repository
5. Click **Deploy**

### 2.3 Set Environment Variables in Vercel
After deployment, go to your project:
1. Click **Settings** → **Environment Variables**
2. Add these variables:

```
SECRET_KEY=<generate-a-random-string>
BASE_URL=https://your-app-name.vercel.app
DATABASE_URL=<postgres-connection-string>
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
SENDGRID_API_KEY=<optional-for-emails>
```

---

## Step 3: Set Up Database

### 3.1 Create Vercel Postgres (Recommended)
1. In Vercel Dashboard, go to **Storage**
2. Click **Create Database** → **Postgres**
3. Choose a name and region
4. Vercel will automatically set `DATABASE_URL` in your environment variables

### 3.2 Initialize Database
After database is created and environment variables are set:

**Option A: Via Vercel CLI**
```bash
npm install -g vercel
vercel login
vercel env pull
python3 init_db.py
```

**Option B: Add initialization endpoint** (recommended)
I can add a one-time setup endpoint to initialize the database remotely.

---

## Step 4: Update Stripe Webhook URL

Now that you have your Vercel URL:
1. Go back to Stripe Dashboard → **Developers** → **Webhooks**
2. Click on your webhook endpoint
3. Update the URL to: `https://your-actual-vercel-url.vercel.app/api/stripe/webhook`
4. Save changes

---

## Step 5: Test Everything

### 5.1 Test Authentication
1. Visit your Vercel URL
2. Click **Login / Sign Up**
3. Enter your email
4. Check console logs in Vercel (or set up SendGrid for real emails)

### 5.2 Test Stripe Checkout
1. After logging in, click **Buy Credits**
2. Select a package
3. Use Stripe test card: `4242 4242 4242 4242`
4. Complete checkout
5. Verify credits are added to your account

### 5.3 Test Moltbook Posting
1. Go to Moltbook tab
2. Import your agent with API key
3. Create a test post
4. Verify credit is deducted

---

## Environment Variables Reference

### Required:
```env
SECRET_KEY=<64-char-random-string>
BASE_URL=https://your-app.vercel.app
DATABASE_URL=postgresql://user:pass@host/db
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

### Optional (for production):
```env
SENDGRID_API_KEY=SG....  # For sending magic link emails
```

### Generate SECRET_KEY:
```python
import secrets
print(secrets.token_hex(32))
```

Or use this online: `openssl rand -hex 32`

---

## Stripe Test Cards

For testing payments:
- **Success**: `4242 4242 4242 4242`
- **Decline**: `4000 0000 0000 0002`
- **Requires Auth**: `4000 0025 0000 3155`

Any future expiry date, any 3-digit CVC.

---

## Going Live (Production)

When ready to accept real payments:

1. **Switch to Live Mode in Stripe**:
   - Get live API keys (starts with `sk_live_` and `pk_live_`)
   - Create new webhook for live mode
   - Update environment variables in Vercel

2. **Set Up Email Service**:
   - Sign up for SendGrid (100 emails/day free)
   - Get API key
   - Add to Vercel environment variables

3. **Database**:
   - Upgrade to production plan
   - Enable backups

4. **Monitoring**:
   - Set up error tracking (Sentry, etc.)
   - Monitor Stripe dashboard

---

## Troubleshooting

### "Database connection failed"
- Check DATABASE_URL is correct
- Ensure database allows connections from Vercel
- Try running `python3 init_db.py` locally against production DB

### "Webhook signature verification failed"
- Make sure STRIPE_WEBHOOK_SECRET matches the one in Stripe Dashboard
- Verify webhook URL is exactly: `https://your-domain.vercel.app/api/stripe/webhook`

### "Magic links not working"
- For development: Links print to Vercel logs (Function Logs)
- For production: Set up SendGrid API key

### "Credits not added after payment"
- Check Stripe webhook logs in Dashboard
- Check Vercel function logs
- Verify webhook endpoint is receiving events

---

## Quick Reference

**Your Stripe Dashboard**: https://dashboard.stripe.com/test/dashboard
**Your Vercel Dashboard**: https://vercel.com/dashboard
**Vercel Function Logs**: Project → Deployments → Latest → Functions

---

## Need Help?

1. Check Vercel function logs for errors
2. Check Stripe webhook logs
3. Review [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed guide
4. Check [QUICKSTART.md](./QUICKSTART.md) for local testing

Good luck! 🚀
