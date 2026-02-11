"""
Slack integration routes - Channels and messages
"""
from flask import jsonify, session
from models import db, Superpower
from datetime import datetime
import requests as http_requests


def get_slack_headers(user_id):
    """Get Slack API headers with authentication"""
    superpower = Superpower.query.filter_by(
        user_id=user_id,
        service_type='slack',
        is_enabled=True
    ).first()

    if not superpower:
        return None, 'Slack not connected'
    if not superpower.access_token_encrypted:
        return None, 'Slack access token missing'

    headers = {
        'Authorization': f'Bearer {superpower.access_token_encrypted}',
        'Content-Type': 'application/json',
    }

    superpower.last_used = datetime.utcnow()
    db.session.commit()

    return headers, None


def register_slack_routes(app):
    """Register Slack routes"""

    @app.route('/api/slack/channels', methods=['GET'])
    def slack_channels():
        """List Slack channels"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_slack_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                'https://slack.com/api/conversations.list',
                headers=headers,
                params={'types': 'public_channel,private_channel', 'limit': 50}
            )
            data = resp.json()

            if not data.get('ok'):
                return jsonify({'error': data.get('error', 'Slack API error')}), 400

            channels = [{
                'id': ch['id'],
                'name': ch['name'],
                'is_private': ch.get('is_private', False),
                'num_members': ch.get('num_members', 0),
                'topic': ch.get('topic', {}).get('value', ''),
            } for ch in data.get('channels', [])]

            return jsonify({'success': True, 'channels': channels})

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/slack/messages/<channel_id>', methods=['GET'])
    def slack_messages(channel_id):
        """List messages in a Slack channel"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_slack_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                'https://slack.com/api/conversations.history',
                headers=headers,
                params={'channel': channel_id, 'limit': 20}
            )
            data = resp.json()

            if not data.get('ok'):
                return jsonify({'error': data.get('error', 'Slack API error')}), 400

            messages = [{
                'ts': msg['ts'],
                'text': msg.get('text', ''),
                'user': msg.get('user'),
                'type': msg.get('type'),
            } for msg in data.get('messages', [])]

            return jsonify({'success': True, 'messages': messages})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
