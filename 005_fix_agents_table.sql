-- Migration 005: Ensure all Agent columns exist
-- Run this in your Neon SQL Editor: https://console.neon.tech/

-- Add any missing columns to agents table (IF NOT EXISTS prevents errors if they already exist)

ALTER TABLE agents ADD COLUMN IF NOT EXISTS avatar_emoji VARCHAR(10) DEFAULT '🤖';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS personality TEXT;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS moltbook_api_key VARCHAR(255);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS llm_config JSON;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS identity_config JSON;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS moltbook_config JSON;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS total_posts INTEGER DEFAULT 0;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS last_post_at TIMESTAMP;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Update alembic version
INSERT INTO alembic_version (version_num) VALUES ('005')
ON CONFLICT (version_num) DO NOTHING;

-- ✅ All agent columns should now exist!
