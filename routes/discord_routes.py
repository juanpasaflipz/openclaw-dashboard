"""
Discord integration routes - Guilds and channels
"""
from flask import jsonify, session
from models import db, Superpower
from datetime import datetime
import requests as http_requests

from routes.oauth_routes import refresh_oauth_token


def get_discord_headers(user_id):
    """Get Discord API headers with authentication, refreshing token if needed"""
    superpower = Superpower.query.filter_by(
        user_id=user_id,
        service_type='discord',
        is_enabled=True
    ).first()

    if not superpower:
        return None, 'Discord not connected'
    if not superpower.access_token_encrypted:
        return None, 'Discord access token missing'

    # Refresh token if expired
    if superpower.token_expires_at and superpower.token_expires_at < datetime.utcnow():
        if not refresh_oauth_token(superpower, 'discord'):
            return None, 'Discord token expired and refresh failed. Please reconnect.'

    headers = {
        'Authorization': f'Bearer {superpower.access_token_encrypted}',
    }

    superpower.last_used = datetime.utcnow()
    db.session.commit()

    return headers, None


def register_discord_routes(app):
    """Register Discord routes"""

    @app.route('/api/discord/guilds', methods=['GET'])
    def discord_guilds():
        """List user's Discord guilds (servers)"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_discord_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                'https://discord.com/api/v10/users/@me/guilds',
                headers=headers
            )
            if resp.status_code != 200:
                return jsonify({'error': f'Discord API error: {resp.text}'}), resp.status_code

            guilds = resp.json()
            return jsonify({
                'success': True,
                'guilds': [{
                    'id': g['id'],
                    'name': g['name'],
                    'icon': g.get('icon'),
                    'owner': g.get('owner', False),
                    'permissions': g.get('permissions'),
                } for g in guilds]
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/discord/guilds/<guild_id>/channels', methods=['GET'])
    def discord_channels(guild_id):
        """List channels in a Discord guild"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_discord_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                f'https://discord.com/api/v10/guilds/{guild_id}/channels',
                headers=headers
            )
            if resp.status_code != 200:
                return jsonify({'error': f'Discord API error: {resp.text}'}), resp.status_code

            channels = resp.json()
            return jsonify({
                'success': True,
                'channels': [{
                    'id': ch['id'],
                    'name': ch['name'],
                    'type': ch['type'],
                    'position': ch.get('position'),
                    'topic': ch.get('topic'),
                } for ch in channels]
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500
