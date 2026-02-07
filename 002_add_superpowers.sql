-- Migration 002: Add Superpowers Table
-- Run this in your Neon SQL Editor: https://console.neon.tech/

-- 1. Create superpowers table
CREATE TABLE superpowers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    agent_id INTEGER,
    service_type VARCHAR(50) NOT NULL,
    service_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expires_at TIMESTAMP,
    config TEXT,
    scopes_granted TEXT,
    usage_count INTEGER DEFAULT 0,
    last_error TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- 2. Create indexes
CREATE INDEX ix_superpowers_service_type ON superpowers(service_type);
CREATE INDEX ix_superpowers_user_id ON superpowers(user_id);

-- 3. Update alembic version tracking
INSERT INTO alembic_version (version_num) VALUES ('002')
ON CONFLICT (version_num) DO NOTHING;

-- ✅ Migration complete!
