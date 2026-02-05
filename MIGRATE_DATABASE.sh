#!/bin/bash
# Migrate Production Database to Add Subscription Columns

echo "🔄 Migrating Production Database..."
echo "===================================="
echo ""

echo "Running database migration on Vercel..."
curl -X POST https://openclaw-dashboard-delta.vercel.app/api/admin/init-db

echo ""
echo ""
echo "✅ Migration Complete!"
echo ""
echo "Expected output:"
echo "  - Database tables created successfully"
echo "  - Subscription plans seeded (Starter, Pro, Team)"
echo ""
echo "Next: Try logging in again!"
echo "URL: https://openclaw-dashboard-delta.vercel.app"
echo ""
