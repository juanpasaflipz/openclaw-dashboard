"""
Moltbook API Routes - Feed, Upvoting, Profiles
Phase 1 Implementation
"""

from flask import Blueprint, jsonify, request, session
import requests
import json
from datetime import datetime, timedelta
from models import db, User, Agent, MoltbookFeedCache, UserUpvote

moltbook_bp = Blueprint('moltbook', __name__, url_prefix='/api/moltbook')


# ============================================
# FEED ENDPOINTS
# ============================================

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
    if not user.can_access_feed():
        return jsonify({
            'error': 'Feed access requires Starter tier or higher',
            'upgrade_required': True,
            'required_tier': 'starter'
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
    agent = user.get_primary_agent()
    if not agent or not agent.moltbook_api_key:
        return jsonify({'error': 'No Moltbook agent configured'}), 400

    try:
        params = {'sort': sort, 'limit': limit}
        if after:
            params['after'] = after

        response = requests.get(
            'https://www.moltbook.com/api/v1/posts',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Cache the results (only if not paginated)
        if not after and 'posts' in data:
            cache_feed('global', None, sort, data['posts'])

        # Add upvote states and return
        result = add_upvote_states(data, user_id)
        return jsonify(result)

    except requests.RequestException as e:
        return jsonify({'error': f'Moltbook API error: {str(e)}'}), 500


@moltbook_bp.route('/submolts/<submolt_name>/feed', methods=['GET'])
def get_submolt_feed(submolt_name):
    """Get posts from a specific submolt"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    user = User.query.get(user_id)
    if not user.can_access_feed():
        return jsonify({
            'error': 'Feed access requires Starter tier',
            'upgrade_required': True
        }), 403

    sort = request.args.get('sort', 'hot')
    limit = min(int(request.args.get('limit', 25)), 50)

    # Check cache
    cached = check_feed_cache('submolt', submolt_name, sort, 180)
    if cached:
        return jsonify(add_upvote_states(cached, user_id))

    # Fetch from Moltbook
    agent = user.get_primary_agent()
    if not agent or not agent.moltbook_api_key:
        return jsonify({'error': 'No Moltbook agent configured'}), 400

    try:
        response = requests.get(
            f'https://www.moltbook.com/api/v1/submolts/{submolt_name}/feed',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            params={'sort': sort, 'limit': limit},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Cache
        if 'posts' in data:
            cache_feed('submolt', submolt_name, sort, data['posts'])

        return jsonify(add_upvote_states(data, user_id))

    except requests.RequestException as e:
        return jsonify({'error': f'Moltbook API error: {str(e)}'}), 500


# ============================================
# UPVOTE ENDPOINTS
# ============================================

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
    if not user.can_upvote():
        return jsonify({
            'error': 'Upvoting requires Starter tier',
            'upgrade_required': True,
            'required_tier': 'starter'
        }), 403

    data = request.get_json() or {}
    agent_id = data.get('agent_id')

    if not agent_id:
        # Use primary agent if not specified
        agent = user.get_primary_agent()
        if not agent:
            return jsonify({'error': 'No agent found'}), 404
        agent_id = agent.id
    else:
        # Verify agent belongs to user
        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

    # Check if already upvoted
    existing = UserUpvote.query.filter_by(
        agent_id=agent_id,
        moltbook_post_id=post_id
    ).first()

    if existing:
        return jsonify({
            'success': True,
            'message': 'Already upvoted',
            'already_upvoted': True
        }), 200

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

        return jsonify({
            'success': True,
            'message': '⬆️ Upvoted!'
        })

    except requests.RequestException as e:
        return jsonify({'error': f'Failed to upvote: {str(e)}'}), 500


@moltbook_bp.route('/posts/<post_id>/upvote', methods=['DELETE'])
def remove_upvote(post_id):
    """Remove upvote (un-upvote)"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json() or {}
    agent_id = data.get('agent_id')

    if not agent_id:
        agent = User.query.get(user_id).get_primary_agent()
        if not agent:
            return jsonify({'error': 'No agent found'}), 404
        agent_id = agent.id

    # Find upvote record
    upvote = UserUpvote.query.filter_by(
        agent_id=agent_id,
        moltbook_post_id=post_id
    ).first()

    if not upvote:
        return jsonify({
            'success': True,
            'message': 'Not upvoted'
        }), 200

    agent = Agent.query.get(agent_id)

    # Call Moltbook API (assuming they have an un-upvote endpoint)
    # Note: Check if Moltbook API supports this
    try:
        response = requests.delete(
            f'https://www.moltbook.com/api/v1/posts/{post_id}/upvote',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            timeout=10
        )
        # Don't fail if endpoint doesn't exist
        if response.status_code != 404:
            response.raise_for_status()

    except requests.RequestException:
        pass  # Continue anyway to remove from our DB

    # Remove from our DB
    db.session.delete(upvote)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Upvote removed'
    })


# ============================================
# PROFILE ENDPOINTS
# ============================================

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
            'upgrade_required': True,
            'required_tier': 'starter'
        }), 403

    # Get user's agent to make API call
    agent = user.get_primary_agent()
    if not agent or not agent.moltbook_api_key:
        return jsonify({'error': 'No Moltbook agent configured'}), 400

    try:
        response = requests.get(
            'https://www.moltbook.com/api/v1/agents/profile',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            params={'name': agent_name},
            timeout=10
        )
        response.raise_for_status()
        return jsonify(response.json())

    except requests.RequestException as e:
        return jsonify({'error': f'Failed to load profile: {str(e)}'}), 500


# ============================================
# HELPER FUNCTIONS
# ============================================

def check_feed_cache(feed_type, feed_key, sort_type, ttl_seconds):
    """Check if we have cached feed data"""
    cutoff = datetime.utcnow() - timedelta(seconds=ttl_seconds)

    query = MoltbookFeedCache.query.filter(
        MoltbookFeedCache.feed_type == feed_type,
        MoltbookFeedCache.sort_type == sort_type,
        MoltbookFeedCache.cached_at >= cutoff
    )

    if feed_key:
        query = query.filter(MoltbookFeedCache.feed_key == feed_key)

    cached = query.order_by(MoltbookFeedCache.cached_at.desc()).all()

    if cached:
        posts = [json.loads(c.post_data) for c in cached]
        return {'posts': posts}

    return None


def cache_feed(feed_type, feed_key, sort_type, posts):
    """Cache feed posts"""
    if not posts:
        return

    expires_at = datetime.utcnow() + timedelta(minutes=5)

    for post in posts[:25]:  # Cache max 25 posts
        cache_entry = MoltbookFeedCache(
            feed_type=feed_type,
            feed_key=feed_key,
            sort_type=sort_type,
            post_data=json.dumps(post),
            expires_at=expires_at
        )
        db.session.add(cache_entry)

    try:
        db.session.commit()
    except:
        db.session.rollback()


def add_upvote_states(data, user_id):
    """Add 'is_upvoted' field to posts based on user's upvote history"""
    user = User.query.get(user_id)
    if not user:
        return data

    agent_ids = [a.id for a in user.agents.all()]

    if not agent_ids:
        return data

    # Get all upvoted post IDs for this user's agents
    upvoted_posts = set()
    for agent_id in agent_ids:
        upvotes = UserUpvote.query.filter_by(agent_id=agent_id).all()
        upvoted_posts.update(u.moltbook_post_id for u in upvotes)

    # Add is_upvoted flag to each post
    if 'posts' in data:
        for post in data['posts']:
            post['is_upvoted'] = post.get('id') in upvoted_posts

    return data
