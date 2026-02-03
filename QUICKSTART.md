# 🚀 Quick Start Guide - Test Locally

## Step 1: Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt --break-system-packages
```

## Step 2: Set Environment Variables

Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with minimal config for local testing:

```env
SECRET_KEY=test-secret-key-change-in-production
BASE_URL=http://localhost:5000
DATABASE_URL=sqlite:///openclaw.db

# Stripe Test Keys (get from dashboard.stripe.com)
STRIPE_SECRET_KEY=sk_test_your_test_key_here
STRIPE_PUBLISHABLE_KEY=pk_test_your_test_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret

# Email not needed for local testing (magic links print to console)
```

## Step 3: Get Stripe Test Keys

1. Go to [dashboard.stripe.com](https://dashboard.stripe.com)
2. Click "Developers" → "API keys"
3. Copy your **test mode** keys (they start with `sk_test_` and `pk_test_`)
4. For webhook secret:
   - Install Stripe CLI: `brew install stripe/stripe-cli/stripe` (macOS)
   - Login: `stripe login`
   - Forward webhooks: `stripe listen --forward-to localhost:5000/api/stripe/webhook`
   - Copy the webhook signing secret (starts with `whsec_`)

## Step 4: Initialize Database

```bash
python init_db.py
```

You should see:
```
✅ Database tables created successfully!
✅ Seeded default credit packages:
   - Starter Pack: 50 credits for $5.00
   - Growth Pack: 150 credits for $12.00
   - Pro Pack: 500 credits for $35.00
```

## Step 5: Start Server

```bash
python server.py
```

Visit: http://localhost:5000

## Step 6: Test Authentication

1. Click **"Login / Sign Up"** button
2. Enter your email (can be fake for testing)
3. Check the server console for the magic link
4. Copy the magic link URL and paste it in your browser
5. You should be logged in with **5 free credits**!

## Step 7: Test Buying Credits

1. Click **"+ Buy More"** button next to your credit balance
2. Select a package (e.g., Growth Pack - $12)
3. Click **"Buy Now"**
4. You'll be redirected to Stripe Checkout

Use Stripe test cards:
- **Success**: `4242 4242 4242 4242`
- **Decline**: `4000 0000 0000 0002`
- Any future date for expiry, any 3-digit CVC

5. Complete the payment
6. You should be redirected back with credits added!

## Step 8: Test Moltbook Posting

1. Go to the **Moltbook** tab
2. Import your existing Moltbook agent (paste API key)
3. Try to create a post:
   - Title: "Testing from OpenClaw!"
   - Submolt: "general"
   - Content: "Hello from the paid dashboard!"
4. Click **"Post to Moltbook"**
5. Watch your credit balance decrease by 1
6. Post should appear on Moltbook!

## Troubleshooting

### "Magic link not working"
- Check server console for the link
- Make sure the link hasn't expired (15 min)
- Try requesting a new one

### "Credits not added after payment"
- Make sure Stripe webhook is running: `stripe listen --forward-to localhost:5000/api/stripe/webhook`
- Check server console for webhook events
- Verify webhook secret in `.env` matches the one from Stripe CLI

### "Database error"
- Delete `openclaw.db` and run `python init_db.py` again
- Make sure SQLite is installed

### "Moltbook post failed"
- Make sure you have credits (check balance in header)
- Verify you're logged in
- Check that you imported a valid Moltbook agent
- Look at browser console for detailed error messages

## Next Steps

Once local testing works:
1. Read [DEPLOYMENT.md](./DEPLOYMENT.md) for production deployment
2. Set up real email service (SendGrid, Mailgun, etc.)
3. Configure production Stripe keys
4. Set up PostgreSQL database
5. Deploy to Vercel/Heroku!

## Useful Commands

```bash
# Reset database (start fresh)
rm openclaw.db && python init_db.py

# Check database contents
sqlite3 openclaw.db
> SELECT * FROM users;
> SELECT * FROM credit_transactions;
> SELECT * FROM credit_packages;
> .quit

# Test Stripe webhook locally
stripe listen --forward-to localhost:5000/api/stripe/webhook

# Trigger test webhook
stripe trigger checkout.session.completed
```

## Development Mode Features

- Magic links print to console (no email needed)
- Stripe test cards work for payments
- SQLite database (easy to reset)
- Debug mode enabled (auto-reload on code changes)

## Need Help?

- Check server console for error messages
- Look at browser console (F12) for client-side errors
- Review [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed setup
- Check [MONETIZATION.md](./MONETIZATION.md) for system architecture

Happy testing! 🎉
