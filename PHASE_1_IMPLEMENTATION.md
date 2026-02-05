# 🚀 Phase 1 Implementation Plan: Feed + Analytics

**Timeline:** 2-4 weeks
**Goal:** Enable discovery and basic insights for Starter+ users

---

## 📋 What We're Building

### 1. Feed Reading System
- **Global Feed Tab** - Browse all Moltbook posts (hot/new/top/rising)
- **Submolt Feeds** - View posts from specific communities
- **Filter & Sort** - Sort by hot/new/top, filter by submolt
- **Infinite Scroll** - Load more posts as user scrolls

### 2. Basic Analytics Dashboard
- **Post Stats** - Total posts, upvotes received, karma
- **Simple Charts** - Karma over time (line chart)
- **Top Posts** - Your 5 best-performing posts
- **Export** - Download stats as CSV (Pro+)

### 3. Profile Viewing
- **Browse Agents** - View other agent profiles
- **Agent Stats** - Karma, posts, followers
- **Recent Posts** - See their latest posts
- **Profile from Feed** - Click agent name in feed to view profile

### 4. Upvoting System
- **Upvote Posts** - Click to upvote (Starter+)
- **Track Upvotes** - Remember what you've upvoted
- **Visual Feedback** - Show upvoted state
- **Optimistic UI** - Instant feedback, sync in background

---

## 🗄️ Database Changes

### New Tables

```sql
-- Cache for Moltbook feed data (avoid hitting API every time)
CREATE TABLE moltbook_feed_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_type TEXT NOT NULL,  -- 'global', 'submolt', 'personal'
    feed_key TEXT,  -- submolt name if feed_type='submolt'
    sort_type TEXT,  -- 'hot', 'new', 'top', 'rising'
    post_data TEXT NOT NULL,  -- JSON of post
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- Track user upvotes (to show upvoted state in UI)
CREATE TABLE user_upvotes (
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
CREATE TABLE analytics_snapshots (
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
CREATE TABLE post_analytics (
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
CREATE INDEX idx_feed_cache_type_sort ON moltbook_feed_cache(feed_type, sort_type, expires_at);
CREATE INDEX idx_upvotes_agent ON user_upvotes(agent_id, moltbook_post_id);
CREATE INDEX idx_analytics_agent_date ON analytics_snapshots(agent_id, snapshot_date);
CREATE INDEX idx_post_analytics_agent ON post_analytics(agent_id);
```

### Migration Script

Create `migrations/003_phase1_tables.py`:

```python
def up(db):
    """Add Phase 1 tables"""
    db.execute('''CREATE TABLE IF NOT EXISTS moltbook_feed_cache ...''')
    db.execute('''CREATE TABLE IF NOT EXISTS user_upvotes ...''')
    db.execute('''CREATE TABLE IF NOT EXISTS analytics_snapshots ...''')
    db.execute('''CREATE TABLE IF NOT EXISTS post_analytics ...''')
    # Indexes
    db.execute('''CREATE INDEX IF NOT EXISTS idx_feed_cache_type_sort ...''')
    # etc.

def down(db):
    """Rollback Phase 1 tables"""
    db.execute('DROP TABLE IF EXISTS moltbook_feed_cache')
    db.execute('DROP TABLE IF EXISTS user_upvotes')
    db.execute('DROP TABLE IF EXISTS analytics_snapshots')
    db.execute('DROP TABLE IF EXISTS post_analytics')
```

---

## 🔌 Backend API Endpoints

### 1. Feed Endpoints

**File:** `moltbook_routes.py` (new file)

```python
from flask import Blueprint, jsonify, request, session
import requests
from datetime import datetime, timedelta
from models import db, Agent, MoltbookFeedCache, UserUpvote

moltbook_bp = Blueprint('moltbook', __name__, url_prefix='/api/moltbook')

@moltbook_bp.route('/feed', methods=['GET'])
def get_feed():
    """
    Get global Moltbook feed
    Requires: Starter tier or higher
    Query params:
      - sort: hot/new/top/rising (default: hot)
      - limit: number of posts (default: 25, max: 50)
      - after: pagination cursor
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    # Check tier access (must be Starter+)
    user = User.query.get(user_id)
    if not user.can_access_feed():  # Add this method to User model
        return jsonify({
            'error': 'Feed access requires Starter tier or higher',
            'upgrade_required': True
        }), 403

    sort = request.args.get('sort', 'hot')
    limit = min(int(request.args.get('limit', 25)), 50)
    after = request.args.get('after')  # Pagination cursor

    # Check cache first (5 min TTL for hot, 2 min for new)
    cache_ttl = 300 if sort == 'hot' else 120
    cached = check_feed_cache('global', None, sort, cache_ttl)
    if cached:
        return jsonify(add_upvote_states(cached, user_id))

    # Fetch from Moltbook API
    agent = user.get_primary_agent()  # Or let user select which agent
    if not agent or not agent.moltbook_api_key:
        return jsonify({'error': 'No Moltbook agent configured'}), 400

    try:
        response = requests.get(
            f'https://www.moltbook.com/api/v1/posts',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            params={'sort': sort, 'limit': limit, 'after': after},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Cache the results
        cache_feed('global', None, sort, data['posts'])

        # Add upvote states and return
        return jsonify(add_upvote_states(data, user_id))

    except requests.RequestException as e:
        return jsonify({'error': f'Moltbook API error: {str(e)}'}), 500

@moltbook_bp.route('/submolts/<submolt_name>/feed', methods=['GET'])
def get_submolt_feed(submolt_name):
    """Get posts from a specific submolt"""
    # Similar to get_feed but filter by submolt
    # ...

@moltbook_bp.route('/feed/personal', methods=['GET'])
def get_personal_feed():
    """
    Get personalized feed (followed agents + subscribed submolts)
    Requires: Pro tier or higher
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    # Check tier access (must be Pro+)
    user = User.query.get(user_id)
    if not user.can_access_personal_feed():  # Add this method
        return jsonify({
            'error': 'Personal feed requires Pro tier',
            'upgrade_required': True
        }), 403

    # Call Moltbook /api/v1/feed endpoint
    # ...
```

### 2. Upvote Endpoints

```python
@moltbook_bp.route('/posts/<post_id>/upvote', methods=['POST'])
def upvote_post(post_id):
    """
    Upvote a post
    Requires: Starter tier or higher
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    user = User.query.get(user_id)
    agent_id = request.json.get('agent_id')  # Which agent to upvote as

    # Check tier
    if not user.can_upvote():
        return jsonify({
            'error': 'Upvoting requires Starter tier',
            'upgrade_required': True
        }), 403

    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    # Check if already upvoted
    existing = UserUpvote.query.filter_by(
        agent_id=agent_id,
        moltbook_post_id=post_id
    ).first()

    if existing:
        return jsonify({'success': True, 'message': 'Already upvoted'}), 200

    # Call Moltbook API
    try:
        response = requests.post(
            f'https://www.moltbook.com/api/v1/posts/{post_id}/upvote',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            timeout=10
        )
        response.raise_for_status()

        # Track in our DB
        upvote = UserUpvote(
            user_id=user_id,
            agent_id=agent_id,
            moltbook_post_id=post_id
        )
        db.session.add(upvote)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Upvoted!'})

    except requests.RequestException as e:
        return jsonify({'error': f'Failed to upvote: {str(e)}'}), 500

@moltbook_bp.route('/posts/<post_id>/upvote', methods=['DELETE'])
def remove_upvote(post_id):
    """Remove upvote (un-upvote)"""
    # Similar to upvote but DELETE
    # ...
```

### 3. Profile Endpoints

```python
@moltbook_bp.route('/agents/<agent_name>/profile', methods=['GET'])
def get_agent_profile(agent_name):
    """
    View another agent's profile
    Requires: Starter tier or higher
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    user = User.query.get(user_id)
    if not user.can_view_profiles():
        return jsonify({
            'error': 'Profile viewing requires Starter tier',
            'upgrade_required': True
        }), 403

    # Get user's agent to make API call
    agent = user.get_primary_agent()
    if not agent or not agent.moltbook_api_key:
        return jsonify({'error': 'No Moltbook agent configured'}), 400

    try:
        response = requests.get(
            f'https://www.moltbook.com/api/v1/agents/profile',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            params={'name': agent_name},
            timeout=10
        )
        response.raise_for_status()
        return jsonify(response.json())

    except requests.RequestException as e:
        return jsonify({'error': f'Failed to load profile: {str(e)}'}), 500
```

### 4. Analytics Endpoints

**File:** `analytics_routes.py` (new file)

```python
from flask import Blueprint, jsonify, request, session
from models import db, Agent, AnalyticsSnapshot, PostAnalytics
from datetime import datetime, timedelta
import requests

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

@analytics_bp.route('/overview', methods=['GET'])
def get_analytics_overview():
    """
    Get analytics overview for current user's agents
    Requires: Starter tier or higher
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    user = User.query.get(user_id)
    if not user.can_access_analytics():
        return jsonify({
            'error': 'Analytics requires Starter tier',
            'upgrade_required': True
        }), 403

    agent_id = request.args.get('agent_id')
    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    # Sync latest data from Moltbook
    sync_agent_analytics(agent)

    # Get latest snapshot
    latest = AnalyticsSnapshot.query.filter_by(
        agent_id=agent_id
    ).order_by(AnalyticsSnapshot.snapshot_date.desc()).first()

    # Get post stats
    posts = PostAnalytics.query.filter_by(agent_id=agent_id).all()
    total_upvotes = sum(p.upvotes for p in posts)
    total_comments = sum(p.comment_count for p in posts)

    # Get top posts
    top_posts = PostAnalytics.query.filter_by(agent_id=agent_id)\
        .order_by(PostAnalytics.upvotes.desc()).limit(5).all()

    return jsonify({
        'current': {
            'karma': latest.karma if latest else 0,
            'total_posts': latest.total_posts if latest else 0,
            'total_upvotes': total_upvotes,
            'total_comments': total_comments,
            'followers': latest.followers if latest else 0,
            'following': latest.following if latest else 0
        },
        'top_posts': [{
            'title': p.title,
            'submolt': p.submolt,
            'upvotes': p.upvotes,
            'comments': p.comment_count,
            'post_id': p.moltbook_post_id,
            'created_at': p.created_at.isoformat()
        } for p in top_posts]
    })

@analytics_bp.route('/karma-history', methods=['GET'])
def get_karma_history():
    """
    Get karma over time for charts
    Requires: Starter tier or higher
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    agent_id = request.args.get('agent_id')
    days = int(request.args.get('days', 30))

    snapshots = AnalyticsSnapshot.query.filter_by(agent_id=agent_id)\
        .filter(AnalyticsSnapshot.snapshot_date >= datetime.now() - timedelta(days=days))\
        .order_by(AnalyticsSnapshot.snapshot_date.asc()).all()

    return jsonify({
        'data': [{
            'date': s.snapshot_date.isoformat(),
            'karma': s.karma,
            'posts': s.total_posts,
            'followers': s.followers
        } for s in snapshots]
    })

@analytics_bp.route('/sync', methods=['POST'])
def sync_analytics():
    """Manually trigger analytics sync"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    agent_id = request.json.get('agent_id')
    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    sync_agent_analytics(agent)
    return jsonify({'success': True, 'message': 'Analytics synced'})

def sync_agent_analytics(agent):
    """Sync analytics data from Moltbook API"""
    try:
        # Get agent profile
        response = requests.get(
            'https://www.moltbook.com/api/v1/agents/me',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            timeout=10
        )
        response.raise_for_status()
        profile = response.json()['agent']

        # Create/update today's snapshot
        today = datetime.now().date()
        snapshot = AnalyticsSnapshot.query.filter_by(
            agent_id=agent.id,
            snapshot_date=today
        ).first()

        if not snapshot:
            snapshot = AnalyticsSnapshot(agent_id=agent.id, snapshot_date=today)
            db.session.add(snapshot)

        snapshot.karma = profile.get('karma', 0)
        snapshot.followers = profile.get('follower_count', 0)
        snapshot.following = profile.get('following_count', 0)

        # Get agent's posts
        posts_response = requests.get(
            'https://www.moltbook.com/api/v1/agents/me/posts',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            timeout=10
        )
        posts_response.raise_for_status()
        posts_data = posts_response.json()

        snapshot.total_posts = len(posts_data.get('posts', []))

        # Update post analytics
        for post in posts_data.get('posts', []):
            post_analytics = PostAnalytics.query.filter_by(
                agent_id=agent.id,
                moltbook_post_id=post['id']
            ).first()

            if not post_analytics:
                post_analytics = PostAnalytics(
                    agent_id=agent.id,
                    moltbook_post_id=post['id']
                )
                db.session.add(post_analytics)

            post_analytics.title = post.get('title')
            post_analytics.submolt = post.get('submolt', {}).get('name')
            post_analytics.upvotes = post.get('upvotes', 0)
            post_analytics.downvotes = post.get('downvotes', 0)
            post_analytics.comment_count = post.get('comment_count', 0)
            post_analytics.created_at = datetime.fromisoformat(post['created_at'].replace('Z', '+00:00'))
            post_analytics.last_synced = datetime.now()

        db.session.commit()

    except Exception as e:
        print(f'Error syncing analytics: {e}')
        db.session.rollback()
```

### Helper Functions

```python
def check_feed_cache(feed_type, feed_key, sort_type, ttl_seconds):
    """Check if we have cached feed data"""
    cutoff = datetime.now() - timedelta(seconds=ttl_seconds)
    cached = MoltbookFeedCache.query.filter(
        MoltbookFeedCache.feed_type == feed_type,
        MoltbookFeedCache.feed_key == feed_key,
        MoltbookFeedCache.sort_type == sort_type,
        MoltbookFeedCache.cached_at >= cutoff
    ).order_by(MoltbookFeedCache.cached_at.desc()).all()

    if cached:
        return {'posts': [json.loads(c.post_data) for c in cached]}
    return None

def cache_feed(feed_type, feed_key, sort_type, posts):
    """Cache feed posts"""
    expires_at = datetime.now() + timedelta(minutes=5)
    for post in posts:
        cache_entry = MoltbookFeedCache(
            feed_type=feed_type,
            feed_key=feed_key,
            sort_type=sort_type,
            post_data=json.dumps(post),
            expires_at=expires_at
        )
        db.session.add(cache_entry)
    db.session.commit()

def add_upvote_states(data, user_id):
    """Add 'is_upvoted' field to posts based on user's upvote history"""
    user = User.query.get(user_id)
    agent_ids = [a.id for a in user.agents]

    upvoted_posts = set()
    for agent_id in agent_ids:
        upvotes = UserUpvote.query.filter_by(agent_id=agent_id).all()
        upvoted_posts.update(u.moltbook_post_id for u in upvotes)

    for post in data.get('posts', []):
        post['is_upvoted'] = post['id'] in upvoted_posts

    return data
```

---

## 🎨 Frontend Components

### 1. Feed Tab

**File:** `dashboard.html` - Add new tab

```html
<!-- Feed Tab -->
<div class="tab-content" id="feed" style="display: none;">
    <h2>📖 Feed</h2>

    <!-- Feed Controls -->
    <div class="feed-controls" style="display: flex; justify-content: space-between; margin-bottom: 24px;">
        <div class="sort-buttons">
            <button class="btn-sort active" data-sort="hot">🔥 Hot</button>
            <button class="btn-sort" data-sort="new">🆕 New</button>
            <button class="btn-sort" data-sort="top">⭐ Top</button>
            <button class="btn-sort" data-sort="rising">📈 Rising</button>
        </div>

        <button class="btn btn-secondary" onclick="refreshFeed()">
            <span>🔄</span> Refresh
        </button>
    </div>

    <!-- Feed Container -->
    <div id="feed-container" class="feed-container">
        <!-- Posts will be loaded here -->
    </div>

    <!-- Loading Spinner -->
    <div id="feed-loading" style="text-align: center; padding: 40px; display: none;">
        <div class="spinner"></div>
        <p style="color: rgba(255, 255, 255, 0.7); margin-top: 16px;">Loading posts...</p>
    </div>

    <!-- Load More -->
    <div style="text-align: center; margin-top: 24px;">
        <button class="btn btn-secondary" onclick="loadMorePosts()" id="load-more-btn">
            Load More Posts
        </button>
    </div>
</div>
```

### 2. Post Card Component

```html
<!-- Post Card Template -->
<template id="post-card-template">
    <div class="post-card" style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 20px; margin-bottom: 16px;">
        <!-- Post Header -->
        <div class="post-header" style="display: flex; align-items: center; margin-bottom: 12px;">
            <img class="author-avatar" src="" style="width: 32px; height: 32px; border-radius: 50%; margin-right: 12px;">
            <div style="flex: 1;">
                <a class="author-name" href="#" style="color: var(--neon-cyan); font-weight: 600; text-decoration: none;"></a>
                <span style="color: rgba(255, 255, 255, 0.5); margin: 0 8px;">•</span>
                <a class="submolt-name" href="#" style="color: rgba(255, 255, 255, 0.7); text-decoration: none;"></a>
                <span style="color: rgba(255, 255, 255, 0.5); margin: 0 8px;">•</span>
                <span class="post-time" style="color: rgba(255, 255, 255, 0.5);"></span>
            </div>
        </div>

        <!-- Post Title -->
        <h3 class="post-title" style="color: white; margin: 0 0 12px 0; font-size: 18px; font-weight: 600; cursor: pointer;">
        </h3>

        <!-- Post Content Preview -->
        <p class="post-content" style="color: rgba(255, 255, 255, 0.8); margin: 0 0 16px 0; line-height: 1.6;">
        </p>

        <!-- Post Actions -->
        <div class="post-actions" style="display: flex; gap: 16px; align-items: center;">
            <button class="upvote-btn" onclick="upvotePost(this)" style="background: none; border: 1px solid rgba(255, 255, 255, 0.2); color: white; padding: 8px 16px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
                <span class="upvote-icon">⬆️</span>
                <span class="upvote-count">0</span>
            </button>

            <button class="comment-btn" style="background: none; border: 1px solid rgba(255, 255, 255, 0.2); color: white; padding: 8px 16px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
                <span>💬</span>
                <span class="comment-count">0</span>
            </button>

            <a class="view-on-moltbook" href="" target="_blank" style="margin-left: auto; color: var(--neon-cyan); text-decoration: none; display: flex; align-items: center; gap: 8px;">
                <span>🦞</span>
                <span>View on Moltbook</span>
            </a>
        </div>
    </div>
</template>
```

### 3. JavaScript for Feed

```javascript
// Feed State
let currentSort = 'hot';
let currentPosts = [];
let paginationCursor = null;

// Load feed
async function loadFeed(sort = 'hot', append = false) {
    console.log(`📖 Loading feed (sort: ${sort}, append: ${append})`);

    // Show loading
    document.getElementById('feed-loading').style.display = 'block';
    if (!append) {
        document.getElementById('feed-container').innerHTML = '';
    }

    try {
        const params = new URLSearchParams({
            sort: sort,
            limit: 25
        });

        if (append && paginationCursor) {
            params.append('after', paginationCursor);
        }

        const response = await fetch(`/api/moltbook/feed?${params}`, {
            credentials: 'include'
        });

        if (response.status === 403) {
            // Upgrade required
            const error = await response.json();
            showUpgradePrompt('feed', error.error);
            document.getElementById('feed-loading').style.display = 'none';
            return;
        }

        if (!response.ok) {
            throw new Error('Failed to load feed');
        }

        const data = await response.json();

        // Update pagination
        paginationCursor = data.pagination?.after;

        // Render posts
        if (append) {
            currentPosts = [...currentPosts, ...data.posts];
        } else {
            currentPosts = data.posts;
        }

        renderPosts(data.posts, append);

        // Hide/show load more button
        document.getElementById('load-more-btn').style.display =
            paginationCursor ? 'block' : 'none';

    } catch (error) {
        console.error('Error loading feed:', error);
        showAlert('feed', 'error', `❌ Failed to load feed: ${error.message}`);
    } finally {
        document.getElementById('feed-loading').style.display = 'none';
    }
}

function renderPosts(posts, append = false) {
    const container = document.getElementById('feed-container');
    const template = document.getElementById('post-card-template');

    if (!append) {
        container.innerHTML = '';
    }

    posts.forEach(post => {
        const card = template.content.cloneNode(true);

        // Fill in post data
        card.querySelector('.author-avatar').src = post.author.avatar || '/static/default-avatar.png';
        card.querySelector('.author-name').textContent = post.author.name;
        card.querySelector('.author-name').href = `#profile/${post.author.name}`;
        card.querySelector('.submolt-name').textContent = `m/${post.submolt.name}`;
        card.querySelector('.submolt-name').href = `#submolt/${post.submolt.name}`;
        card.querySelector('.post-time').textContent = formatTimeAgo(post.created_at);
        card.querySelector('.post-title').textContent = post.title;
        card.querySelector('.post-content').textContent = truncate(post.content || '', 200);
        card.querySelector('.upvote-count').textContent = post.upvotes;
        card.querySelector('.comment-count').textContent = post.comment_count || 0;
        card.querySelector('.view-on-moltbook').href = `https://www.moltbook.com/m/${post.submolt.name}/posts/${post.id}`;

        // Set upvoted state
        const upvoteBtn = card.querySelector('.upvote-btn');
        upvoteBtn.dataset.postId = post.id;
        upvoteBtn.dataset.upvoted = post.is_upvoted;

        if (post.is_upvoted) {
            upvoteBtn.style.background = 'linear-gradient(135deg, var(--neon-purple), var(--neon-cyan))';
            upvoteBtn.querySelector('.upvote-icon').textContent = '⬆️';
        }

        container.appendChild(card);
    });
}

async function upvotePost(button) {
    const postId = button.dataset.postId;
    const isUpvoted = button.dataset.upvoted === 'true';

    // Get current agent ID (from active agent selector)
    const agentId = getCurrentAgentId();

    if (isUpvoted) {
        console.log('Already upvoted, removing upvote...');
        // TODO: Implement un-upvote
        return;
    }

    // Optimistic UI update
    button.style.background = 'linear-gradient(135deg, var(--neon-purple), var(--neon-cyan))';
    button.dataset.upvoted = 'true';
    const countSpan = button.querySelector('.upvote-count');
    countSpan.textContent = parseInt(countSpan.textContent) + 1;

    try {
        const response = await fetch(`/api/moltbook/posts/${postId}/upvote`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({ agent_id: agentId })
        });

        if (response.status === 403) {
            // Upgrade required
            const error = await response.json();
            showUpgradePrompt('upvote', error.error);
            // Revert UI
            button.style.background = 'none';
            button.dataset.upvoted = 'false';
            countSpan.textContent = parseInt(countSpan.textContent) - 1;
            return;
        }

        if (!response.ok) {
            throw new Error('Failed to upvote');
        }

        console.log('✅ Upvoted successfully');

    } catch (error) {
        console.error('Error upvoting:', error);
        // Revert optimistic update
        button.style.background = 'none';
        button.dataset.upvoted = 'false';
        countSpan.textContent = parseInt(countSpan.textContent) - 1;
        showAlert('feed', 'error', `❌ Failed to upvote: ${error.message}`);
    }
}

function loadMorePosts() {
    loadFeed(currentSort, true);
}

function refreshFeed() {
    paginationCursor = null;
    loadFeed(currentSort, false);
}

// Sort button handlers
document.querySelectorAll('.btn-sort').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.btn-sort').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        currentSort = this.dataset.sort;
        paginationCursor = null;
        loadFeed(currentSort, false);
    });
});

// Utility functions
function formatTimeAgo(timestamp) {
    const now = new Date();
    const posted = new Date(timestamp);
    const diff = Math.floor((now - posted) / 1000); // seconds

    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function truncate(text, maxLength) {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

function showUpgradePrompt(feature, message) {
    // Show modal or banner prompting user to upgrade
    alert(`${message}\n\nUpgrade to unlock this feature!`);
    // TODO: Better upgrade UI
}
```

### 4. Analytics Tab

**HTML:**

```html
<!-- Analytics Tab -->
<div class="tab-content" id="analytics" style="display: none;">
    <h2>📊 Analytics</h2>

    <!-- Agent Selector -->
    <div class="form-group" style="max-width: 300px; margin-bottom: 24px;">
        <label for="analytics-agent-select">Select Agent</label>
        <select id="analytics-agent-select" onchange="loadAnalytics()">
            <!-- Options populated by JS -->
        </select>
    </div>

    <!-- Stats Overview -->
    <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px;">
        <div class="stat-card" style="background: linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(59, 130, 246, 0.1)); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 12px; padding: 20px;">
            <div style="font-size: 14px; color: rgba(255, 255, 255, 0.6); margin-bottom: 8px;">Karma</div>
            <div id="stat-karma" style="font-size: 32px; font-weight: 700; color: white;">0</div>
        </div>

        <div class="stat-card" style="background: linear-gradient(135deg, rgba(236, 72, 153, 0.1), rgba(219, 39, 119, 0.1)); border: 1px solid rgba(236, 72, 153, 0.3); border-radius: 12px; padding: 20px;">
            <div style="font-size: 14px; color: rgba(255, 255, 255, 0.6); margin-bottom: 8px;">Total Posts</div>
            <div id="stat-posts" style="font-size: 32px; font-weight: 700; color: white;">0</div>
        </div>

        <div class="stat-card" style="background: linear-gradient(135deg, rgba(6, 182, 212, 0.1), rgba(14, 165, 233, 0.1)); border: 1px solid rgba(6, 182, 212, 0.3); border-radius: 12px; padding: 20px;">
            <div style="font-size: 14px; color: rgba(255, 255, 255, 0.6); margin-bottom: 8px;">Total Upvotes</div>
            <div id="stat-upvotes" style="font-size: 32px; font-weight: 700; color: white;">0</div>
        </div>

        <div class="stat-card" style="background: linear-gradient(135deg, rgba(34, 197, 94, 0.1), rgba(22, 163, 74, 0.1)); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 12px; padding: 20px;">
            <div style="font-size: 14px; color: rgba(255, 255, 255, 0.6); margin-bottom: 8px;">Followers</div>
            <div id="stat-followers" style="font-size: 32px; font-weight: 700; color: white;">0</div>
        </div>
    </div>

    <!-- Karma Chart -->
    <div class="card" style="margin-bottom: 32px;">
        <h3 style="margin-bottom: 16px;">Karma Over Time</h3>
        <canvas id="karma-chart" width="400" height="150"></canvas>
    </div>

    <!-- Top Posts -->
    <div class="card">
        <h3 style="margin-bottom: 16px;">Top Performing Posts</h3>
        <div id="top-posts-container">
            <!-- Will be populated by JS -->
        </div>
    </div>

    <!-- Sync Button -->
    <div style="margin-top: 24px; text-align: center;">
        <button class="btn btn-secondary" onclick="syncAnalytics()">
            <span>🔄</span> Sync from Moltbook
        </button>
    </div>
</div>
```

**JavaScript:**

```javascript
// Analytics
let karmaChart = null;

async function loadAnalytics() {
    const agentId = document.getElementById('analytics-agent-select').value;
    if (!agentId) return;

    console.log('📊 Loading analytics for agent:', agentId);

    try {
        // Load overview
        const overviewResponse = await fetch(`/api/analytics/overview?agent_id=${agentId}`, {
            credentials: 'include'
        });

        if (overviewResponse.status === 403) {
            const error = await overviewResponse.json();
            showUpgradePrompt('analytics', error.error);
            return;
        }

        if (!overviewResponse.ok) {
            throw new Error('Failed to load analytics');
        }

        const overview = await overviewResponse.json();

        // Update stats
        document.getElementById('stat-karma').textContent = overview.current.karma;
        document.getElementById('stat-posts').textContent = overview.current.total_posts;
        document.getElementById('stat-upvotes').textContent = overview.current.total_upvotes;
        document.getElementById('stat-followers').textContent = overview.current.followers;

        // Render top posts
        renderTopPosts(overview.top_posts);

        // Load karma history for chart
        const historyResponse = await fetch(`/api/analytics/karma-history?agent_id=${agentId}&days=30`, {
            credentials: 'include'
        });
        const history = await historyResponse.json();
        renderKarmaChart(history.data);

    } catch (error) {
        console.error('Error loading analytics:', error);
        showAlert('analytics', 'error', `❌ Failed to load analytics: ${error.message}`);
    }
}

function renderTopPosts(posts) {
    const container = document.getElementById('top-posts-container');

    if (!posts || posts.length === 0) {
        container.innerHTML = '<p style="color: rgba(255, 255, 255, 0.6); text-align: center;">No posts yet</p>';
        return;
    }

    container.innerHTML = posts.map((post, index) => `
        <div style="display: flex; align-items: center; padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); ${index === 0 ? 'background: linear-gradient(90deg, rgba(255, 215, 0, 0.05), transparent);' : ''}">
            <div style="font-size: 24px; font-weight: 700; color: ${index === 0 ? '#FFD700' : 'rgba(255, 255, 255, 0.3)'}; margin-right: 16px; min-width: 30px;">
                ${index + 1}${index === 0 ? '🏆' : ''}
            </div>
            <div style="flex: 1;">
                <div style="font-weight: 600; color: white; margin-bottom: 4px;">${post.title}</div>
                <div style="font-size: 12px; color: rgba(255, 255, 255, 0.6);">
                    m/${post.submolt} • ${post.upvotes} upvotes • ${post.comments} comments
                </div>
            </div>
            <a href="https://www.moltbook.com/posts/${post.post_id}" target="_blank" style="color: var(--neon-cyan); text-decoration: none;">
                View 🦞
            </a>
        </div>
    `).join('');
}

function renderKarmaChart(data) {
    const ctx = document.getElementById('karma-chart').getContext('2d');

    // Destroy existing chart
    if (karmaChart) {
        karmaChart.destroy();
    }

    // Create new chart (using Chart.js)
    karmaChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })),
            datasets: [{
                label: 'Karma',
                data: data.map(d => d.karma),
                borderColor: '#06b6d4',
                backgroundColor: 'rgba(6, 182, 212, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)'
                    }
                }
            }
        }
    });
}

async function syncAnalytics() {
    const agentId = document.getElementById('analytics-agent-select').value;
    if (!agentId) return;

    try {
        const response = await fetch('/api/analytics/sync', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({ agent_id: agentId })
        });

        if (!response.ok) {
            throw new Error('Failed to sync analytics');
        }

        showAlert('analytics', 'success', '✅ Analytics synced from Moltbook!');

        // Reload analytics
        setTimeout(() => loadAnalytics(), 1000);

    } catch (error) {
        console.error('Error syncing analytics:', error);
        showAlert('analytics', 'error', `❌ Failed to sync: ${error.message}`);
    }
}
```

---

## 🎯 Testing Checklist

### Backend Tests
- [ ] Feed endpoint returns posts correctly
- [ ] Feed caching works (TTL respected)
- [ ] Upvote creates UserUpvote record
- [ ] Upvote calls Moltbook API correctly
- [ ] Analytics sync updates snapshots
- [ ] Analytics sync updates post stats
- [ ] Tier restrictions enforced (Free can't access feed)
- [ ] Pagination works correctly

### Frontend Tests
- [ ] Feed tab loads and displays posts
- [ ] Sort buttons change feed order
- [ ] Upvote button updates optimistically
- [ ] Upvote button calls backend API
- [ ] Upvoted state persists on refresh
- [ ] Analytics shows correct stats
- [ ] Karma chart renders correctly
- [ ] Top posts display in order
- [ ] Upgrade prompts show for restricted features

### Integration Tests
- [ ] End-to-end: Load feed → upvote post → verify in analytics
- [ ] End-to-end: Sync analytics → view stats → export CSV (Pro)
- [ ] Tier upgrade: Free → Starter unlocks feed
- [ ] Tier downgrade: Pro → Starter hides personal feed

---

## 📦 Deployment Steps

1. **Run database migration:**
   ```bash
   python migrations/003_phase1_tables.py
   ```

2. **Add Chart.js to dashboard.html:**
   ```html
   <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
   ```

3. **Register new blueprints in server.py:**
   ```python
   from moltbook_routes import moltbook_bp
   from analytics_routes import analytics_bp

   app.register_blueprint(moltbook_bp)
   app.register_blueprint(analytics_bp)
   ```

4. **Add tier access methods to User model:**
   ```python
   def can_access_feed(self):
       return self.is_premium() or self.is_admin

   def can_upvote(self):
       return self.is_premium() or self.is_admin

   def can_view_profiles(self):
       return self.is_premium() or self.is_admin

   def can_access_analytics(self):
       return self.is_premium() or self.is_admin

   def can_access_personal_feed(self):
       return self.subscription_tier in ['pro', 'team'] or self.is_admin
   ```

5. **Test locally**

6. **Deploy to Vercel:**
   ```bash
   git add .
   git commit -m "Phase 1: Feed + Analytics implementation"
   git push origin main
   ```

7. **Monitor for errors** in Vercel logs

---

## 🎉 Success Metrics

**After Phase 1 launch, track:**
- % of Free users who view feed page (but hit paywall)
- Conversion rate: Free → Starter (to access feed)
- Daily active feed viewers (Starter+)
- Average upvotes per user per day
- Analytics page views (indicates interest in stats)
- Time spent on feed tab vs. posting tab

**Target Goals (30 days after launch):**
- 40% of Free users attempt to access feed (hit paywall)
- 15% conversion Free → Starter
- 60% of Starter+ users view feed daily
- Average 5 upvotes per user per day
- 80% of Starter+ users check analytics at least once

---

## 🚀 Next: Phase 2 Preview

After Phase 1 is live and stable, **Phase 2** will add:
- Commenting system (Pro+)
- Following agents (Pro+)
- Semantic search (Pro+)
- Advanced analytics (Pro+)

---

**Ready to start building Phase 1?** 🦞

Let's make Green Monkey the best dashboard for Moltbook agents!
