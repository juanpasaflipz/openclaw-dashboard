-- Migration 003: Add is_admin column to users table
-- Run this in your Neon SQL Editor: https://console.neon.tech/

-- 1. Add is_admin column
ALTER TABLE users
ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Create index on is_admin for faster admin queries
CREATE INDEX IF NOT EXISTS ix_users_is_admin ON users(is_admin);

-- 3. Update alembic version tracking
INSERT INTO alembic_version (version_num) VALUES ('003')
ON CONFLICT (version_num) DO NOTHING;

-- ✅ Migration complete!
