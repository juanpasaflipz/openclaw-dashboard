-- Add Moltbook-related fields to agents table
-- Migration 004: Add avatar_url, personality, and moltbook_api_key columns

ALTER TABLE agents ADD COLUMN avatar_url TEXT;
ALTER TABLE agents ADD COLUMN personality TEXT;
ALTER TABLE agents ADD COLUMN moltbook_api_key TEXT;

-- Create index on moltbook_api_key for faster lookups
CREATE INDEX IF NOT EXISTS idx_agents_moltbook_api_key ON agents(moltbook_api_key);
