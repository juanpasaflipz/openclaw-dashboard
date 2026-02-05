# 🚀 Pre-Launch Checklist for OpenClaw Dashboard

## ✅ Already Working
- [x] SSL connection fix (no more dropped connections)
- [x] Magic link authentication
- [x] Subscription system (3 tiers)
- [x] Stripe checkout tested
- [x] Database migrations complete
- [x] Subscription UI working

---

## 🔧 Critical Tasks Before Public Launch

### 1. **Update Stripe Webhook (REQUIRED!)** ⚠️
**Status:** ⚠️ Needs to be done

Without this, subscriptions won't activate automatically!

**Steps:**
1. Go to: https://dashboard.stripe.com/webhooks
2. Click on your webhook endpoint
3. Click "Add events" or "Select events"
4. Add these events:
   - ✅ `customer.subscription.created`
   - ✅ `customer.subscription.updated`
   - ✅ `customer.subscription.deleted`
   - ✅ `invoice.payment_succeeded`
   - ✅ `invoice.payment_failed`
5. Save the webhook

**Test it:**
After adding events, purchase a subscription with test card and verify:
- User's subscription_tier updates to "pro" or "team"
- User's subscription_status becomes "active"
- User can post unlimited times (no 30-min rate limit)

---

### 2. **Switch to Stripe Live Mode** 💰
**Status:** Currently in TEST mode

**Steps:**
1. Go to Stripe Dashboard (top right toggle: Test → Live)
2. Get your **LIVE** API keys:
   - Publishable key (starts with `pk_live_...`)
   - Secret key (starts with `sk_live_...`)
3. Update Vercel environment variables:
   ```
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   STRIPE_SECRET_KEY=sk_live_...
   ```
4. Create new webhook for LIVE mode:
   - URL: `https://openclaw-dashboard-delta.vercel.app/api/stripe/webhook`
   - Add all subscription events (same as test mode)
   - Copy the LIVE webhook secret
5. Update Vercel env:
   ```
   STRIPE_WEBHOOK_SECRET=whsec_live_...
   ```
6. Redeploy Vercel (it auto-redeploys on env variable changes)

⚠️ **Important:** Keep test mode for now if you want to do more testing first!

---

### 3. **Verify SendGrid Email** ✉️
**Status:** Check if working in production

**Test:**
1. Try logging in with a new email address
2. Check if magic link email arrives
3. Verify email formatting looks good
4. Check spam folder if not received

**If emails aren't sending:**
- Check Vercel logs for SendGrid errors
- Verify `SENDGRID_API_KEY` is set
- Verify `SENDGRID_FROM_EMAIL` is verified in SendGrid
- Check SendGrid dashboard for delivery stats

---

### 4. **Set Custom Admin Password** 🔐
**Status:** Currently using default password

**Current default:** `openclaw-init-2026`

**Set a strong password in Vercel:**
```
ADMIN_PASSWORD=your-super-secret-password-here
```

This protects your `/api/admin/init-db` and migration endpoints.

---

### 5. **Add Rate Limiting for API Endpoints** 🛡️
**Status:** Only Moltbook posting has rate limits

**Consider adding rate limits to:**
- Magic link requests (prevent spam)
- Subscription checkout (prevent abuse)
- Config updates

**Quick fix - Add to server.py:**
```python
from datetime import datetime, timedelta

# In-memory rate limiting (simple)
magic_link_requests = {}

@app.route('/api/auth/request-magic-link', methods=['POST'])
def request_magic_link():
    email = request.json.get('email')

    # Rate limit: 3 requests per 10 minutes per email
    now = datetime.utcnow()
    if email in magic_link_requests:
        recent = [t for t in magic_link_requests[email] if now - t < timedelta(minutes=10)]
        if len(recent) >= 3:
            return jsonify({'error': 'Too many requests. Try again later.'}), 429
        magic_link_requests[email] = recent + [now]
    else:
        magic_link_requests[email] = [now]

    # Continue with magic link logic...
```

---

### 6. **Add Error Monitoring** 📊
**Status:** Basic console logging only

**Recommended tools:**
- **Sentry** (free tier available) - automatic error tracking
- **LogRocket** - session replay for debugging
- **Vercel Analytics** - already included

**Quick Sentry setup:**
1. Sign up at https://sentry.io
2. `pip install sentry-sdk[flask]`
3. Add to server.py:
```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[FlaskIntegration()],
    traces_sample_rate=1.0
)
```

---

### 7. **Add Terms of Service & Privacy Policy** 📄
**Status:** Not present

**Required for:**
- Stripe compliance
- Legal protection
- User trust

**Options:**
1. Use a generator: https://www.termsfeed.com
2. Hire a lawyer (recommended for serious business)
3. Copy and modify from similar services (be careful!)

**Add to dashboard:**
- Footer links to Terms & Privacy pages
- Checkbox during signup: "I agree to Terms of Service"
- Add to Stripe checkout metadata

---

### 8. **Test Edge Cases** 🧪

**Subscription scenarios to test:**
- [ ] User subscribes to Pro
- [ ] User upgrades from Starter to Pro
- [ ] User downgrades from Pro to Starter
- [ ] User cancels subscription
- [ ] Payment fails (subscription goes past_due)
- [ ] User updates payment method
- [ ] Subscription expires and renews

**Authentication scenarios:**
- [ ] User clicks expired magic link (>15 min old)
- [ ] User clicks magic link twice
- [ ] User tries to access dashboard without login
- [ ] User logs out and logs back in

---

### 9. **Add Analytics Tracking** 📈
**Status:** Not implemented

**Track key metrics:**
- Sign-ups
- Subscription conversions
- Churn rate
- Active users
- Moltbook posts created

**Quick options:**
- Google Analytics 4
- Plausible Analytics (privacy-focused)
- PostHog (open source)

---

### 10. **Performance & Security Headers** 🔒
**Status:** Basic Flask defaults

**Add to vercel.json:**
```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {
          "key": "X-Content-Type-Options",
          "value": "nosniff"
        },
        {
          "key": "X-Frame-Options",
          "value": "DENY"
        },
        {
          "key": "X-XSS-Protection",
          "value": "1; mode=block"
        },
        {
          "key": "Referrer-Policy",
          "value": "strict-origin-when-cross-origin"
        }
      ]
    }
  ]
}
```

---

## 🎯 Minimum Viable Public Launch

**Must have (do these first):**
1. ✅ Update Stripe webhook with subscription events
2. ✅ Test subscription activation with webhook
3. ✅ Set custom ADMIN_PASSWORD
4. ✅ Verify SendGrid emails working

**Should have (do soon):**
5. Add rate limiting to magic links
6. Add Terms of Service & Privacy Policy
7. Switch to Stripe Live mode (when ready to charge real money)

**Nice to have (do later):**
8. Add error monitoring (Sentry)
9. Add analytics tracking
10. Add security headers

---

## 🚀 Launch Checklist

- [ ] **Stripe webhook updated with subscription events**
- [ ] **Test subscription activation (webhook works)**
- [ ] **Custom admin password set**
- [ ] **SendGrid emails verified**
- [ ] Rate limiting added to magic links
- [ ] Terms of Service page added
- [ ] Privacy Policy page added
- [ ] Stripe Live mode configured (when ready for real payments)
- [ ] Error monitoring setup
- [ ] Analytics tracking added

---

## 🎉 Ready to Launch When:

**Minimum (Beta/Soft Launch):**
- ✅ First 4 critical tasks complete
- ✅ Tested with 3-5 beta users
- ⚠️ Keep Stripe in TEST mode
- ⚠️ Clearly label as "Beta"

**Full Public Launch:**
- ✅ All "Must have" items complete
- ✅ Most "Should have" items complete
- ✅ Stripe LIVE mode active
- ✅ Terms & Privacy pages live
- ✅ Tested thoroughly with real payments

---

## 🐛 Known Issues to Monitor

1. **PostgreSQL connection** - Watch for SSL drops (should be fixed now)
2. **Rate limiting** - Monitor for abuse
3. **Email delivery** - Check SendGrid dashboard
4. **Stripe webhooks** - Monitor webhook delivery in Stripe dashboard

---

## 📞 Support & Monitoring

**Daily checks:**
- Vercel deployment status
- Stripe webhook delivery success rate
- SendGrid email delivery rate
- Database health check: `curl https://openclaw-dashboard-delta.vercel.app/api/health`

**Weekly checks:**
- Review error logs
- Check user feedback
- Monitor subscription churn
- Review failed payments

---

## 💰 Pricing Strategy

**Current pricing:**
- Free: $0 (30-min cooldown)
- Starter: $9/month
- Pro: $29/month (UNLIMITED posts)
- Team: $79/month

**Consider:**
- Are prices competitive?
- Should you offer annual billing (discount)?
- Free trial period (7-14 days)?
- Money-back guarantee (30 days)?

---

## 🎯 Next Steps

1. **Complete critical tasks** (Stripe webhook, admin password)
2. **Soft launch** with beta users (test mode)
3. **Gather feedback** and fix issues
4. **Switch to live mode** when ready
5. **Full public launch!** 🚀

---

**Your dashboard is 95% ready for public launch!** 🎉

Focus on the 4 critical tasks first, then you can do a soft launch with Stripe test mode while you work on the "should have" items.
