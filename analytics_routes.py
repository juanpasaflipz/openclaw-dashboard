"""
Analytics API Routes - Stats, Charts, Post Performance
Phase 1 Implementation
"""

from flask import Blueprint, jsonify, request, session
import requests
from datetime import datetime, timedelta
from models import db, User, Agent, AnalyticsSnapshot, PostAnalytics

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')


@analytics_bp.route('/overview', methods=['GET'])
def get_analytics_overview():
    """
    Get analytics overview for an agent
    Requires: Starter tier or higher
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    user = User.query.get(user_id)
    if not user.can_access_analytics():
        return jsonify({
            'error': 'Analytics requires Starter tier or higher',
            'upgrade_required': True,
            'required_tier': 'starter'
        }), 403

    agent_id = request.args.get('agent_id')
    if not agent_id:
        return jsonify({'error': 'agent_id required'}), 400

    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    # Sync latest data from Moltbook
    try:
        sync_agent_analytics(agent)
    except Exception as e:
        print(f'Warning: Failed to sync analytics: {e}')
        # Continue anyway with cached data

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
        'success': True,
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
            'created_at': p.created_at.isoformat() if p.created_at else None
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

    user = User.query.get(user_id)
    if not user.can_access_analytics():
        return jsonify({
            'error': 'Analytics requires Starter tier',
            'upgrade_required': True
        }), 403

    agent_id = request.args.get('agent_id')
    if not agent_id:
        return jsonify({'error': 'agent_id required'}), 400

    days = int(request.args.get('days', 30))

    # Verify agent belongs to user
    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    snapshots = AnalyticsSnapshot.query.filter_by(agent_id=agent_id)\
        .filter(AnalyticsSnapshot.snapshot_date >= datetime.utcnow().date() - timedelta(days=days))\
        .order_by(AnalyticsSnapshot.snapshot_date.asc()).all()

    return jsonify({
        'success': True,
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

    user = User.query.get(user_id)
    if not user.can_access_analytics():
        return jsonify({
            'error': 'Analytics requires Starter tier',
            'upgrade_required': True
        }), 403

    data = request.get_json() or {}
    agent_id = data.get('agent_id')

    if not agent_id:
        return jsonify({'error': 'agent_id required'}), 400

    agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    try:
        sync_agent_analytics(agent)
        return jsonify({
            'success': True,
            'message': 'Analytics synced from Moltbook'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to sync: {str(e)}'
        }), 500


# ============================================
# HELPER FUNCTIONS
# ============================================

def sync_agent_analytics(agent):
    """Sync analytics data from Moltbook API"""
    if not agent.moltbook_api_key:
        raise ValueError('Agent has no Moltbook API key')

    try:
        # Get agent profile
        response = requests.get(
            'https://www.moltbook.com/api/v1/agents/me',
            headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
            timeout=10
        )
        response.raise_for_status()
        profile_data = response.json()
        profile = profile_data.get('agent', {})

        # Create/update today's snapshot
        today = datetime.utcnow().date()
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

        # Get agent's posts (if endpoint exists)
        try:
            posts_response = requests.get(
                'https://www.moltbook.com/api/v1/posts',
                headers={'Authorization': f'Bearer {agent.moltbook_api_key}'},
                params={'sort': 'new', 'limit': 50},  # Get recent posts
                timeout=10
            )
            posts_response.raise_for_status()
            posts_data = posts_response.json()

            # Filter for this agent's posts
            my_posts = [p for p in posts_data.get('posts', [])
                       if p.get('author', {}).get('name') == agent.name]

            snapshot.total_posts = len(my_posts)

            # Update post analytics
            for post in my_posts:
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

                # Parse created_at timestamp
                created_str = post.get('created_at', '')
                if created_str:
                    try:
                        # Handle ISO format with Z
                        post_analytics.created_at = datetime.fromisoformat(
                            created_str.replace('Z', '+00:00')
                        )
                    except:
                        pass

                post_analytics.last_synced = datetime.utcnow()

        except Exception as e:
            print(f'Warning: Could not fetch posts: {e}')
            # Continue with profile data at least

        db.session.commit()

    except requests.RequestException as e:
        db.session.rollback()
        raise Exception(f'Moltbook API error: {str(e)}')
    except Exception as e:
        db.session.rollback()
        raise Exception(f'Analytics sync error: {str(e)}')
