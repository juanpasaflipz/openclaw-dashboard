-- Migration 004: Add Agent Actions Table
-- Run this in your Neon SQL Editor: https://console.neon.tech/

-- 1. Create agent_actions table
CREATE TABLE agent_actions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    agent_id INTEGER,
    action_type VARCHAR(50) NOT NULL,
    service_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    action_data TEXT NOT NULL,
    ai_reasoning TEXT,
    ai_confidence FLOAT,
    result_data TEXT,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    executed_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- 2. Create indexes for fast queries
CREATE INDEX ix_agent_actions_action_type ON agent_actions(action_type);
CREATE INDEX ix_agent_actions_status ON agent_actions(status);
CREATE INDEX ix_agent_actions_created_at ON agent_actions(created_at);

-- 3. Update alembic version tracking
INSERT INTO alembic_version (version_num) VALUES ('004')
ON CONFLICT (version_num) DO NOTHING;

-- ✅ Migration complete! Now agents can propose actions for user approval.
