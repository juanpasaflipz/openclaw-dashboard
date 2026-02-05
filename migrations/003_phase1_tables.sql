-- Phase 1: Feed + Analytics Database Schema
-- Run this to add tables for feed caching, upvotes, and analytics

-- Cache for Moltbook feed data (avoid hitting API every time)
CREATE TABLE IF NOT EXISTS moltbook_feed_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_type TEXT NOT NULL,  -- 'global', 'submolt', 'personal'
    feed_key TEXT,  -- submolt name if feed_type='submolt'
    sort_type TEXT NOT NULL,  -- 'hot', 'new', 'top', 'rising'
    post_data TEXT NOT NULL,  -- JSON of post
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

-- Track user upvotes (to show upvoted state in UI)
CREATE TABLE IF NOT EXISTS user_upvotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    moltbook_post_id TEXT NOT NULL,  -- Moltbook's post ID
    upvoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    UNIQUE(agent_id, moltbook_post_id)
);

-- Analytics snapshots (daily rollup for historical charts)
CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    karma INTEGER DEFAULT 0,
    total_posts INTEGER DEFAULT 0,
    total_comments INTEGER DEFAULT 0,
    followers INTEGER DEFAULT 0,
    following INTEGER DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    UNIQUE(agent_id, snapshot_date)
);

-- Post performance tracking
CREATE TABLE IF NOT EXISTS post_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    moltbook_post_id TEXT NOT NULL,
    title TEXT,
    submolt TEXT,
    upvotes INTEGER DEFAULT 0,
    downvotes INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    UNIQUE(agent_id, moltbook_post_id)
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_feed_cache_type_sort ON moltbook_feed_cache(feed_type, sort_type, expires_at);
CREATE INDEX IF NOT EXISTS idx_upvotes_agent ON user_upvotes(agent_id, moltbook_post_id);
CREATE INDEX IF NOT EXISTS idx_analytics_agent_date ON analytics_snapshots(agent_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_post_analytics_agent ON post_analytics(agent_id);

-- Add column to users table for tracking subscription features
-- (Skip if column already exists - SQLite will error if it does)
-- ALTER TABLE users ADD COLUMN can_access_feed INTEGER DEFAULT 0;
