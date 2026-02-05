#!/bin/bash
# Test OpenClaw Dashboard Deployment

echo "🧪 Testing OpenClaw Dashboard Deployment"
echo "========================================"
echo ""

echo "1️⃣ Testing Health Check..."
echo "URL: https://openclaw-dashboard-delta.vercel.app/api/health"
curl -s https://openclaw-dashboard-delta.vercel.app/api/health | jq '.'
echo ""
echo ""

echo "2️⃣ Testing Auth Endpoint..."
echo "URL: https://openclaw-dashboard-delta.vercel.app/api/auth/me"
curl -s https://openclaw-dashboard-delta.vercel.app/api/auth/me | jq '.'
echo ""
echo ""

echo "3️⃣ Testing Subscription Plans..."
echo "URL: https://openclaw-dashboard-delta.vercel.app/api/subscriptions/plans"
curl -s https://openclaw-dashboard-delta.vercel.app/api/subscriptions/plans | jq '.'
echo ""
echo ""

echo "✅ Tests Complete!"
echo ""
echo "Expected Results:"
echo "  1. Health Check: Should show 'status: healthy' and 'database: connected'"
echo "  2. Auth Endpoint: Should return 'authenticated: false' (you're not logged in)"
echo "  3. Subscription Plans: Should list 3 plans (Starter, Pro, Team)"
echo ""
echo "Next Steps:"
echo "  1. Open https://openclaw-dashboard-delta.vercel.app in your browser"
echo "  2. Try logging in with your email"
echo "  3. Check the 💎 Subscription tab"
echo "  4. Update Stripe webhook with subscription events"
echo ""
