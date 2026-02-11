"""
Telegram Bot integration routes - Connect via bot token, get info and updates
"""
from flask import jsonify, request, session
from models import db, Superpower
from datetime import datetime
import requests as http_requests


def register_telegram_routes(app):
    """Register Telegram routes"""

    @app.route('/api/telegram/connect', methods=['POST'])
    def connect_telegram():
        """Connect Telegram bot with a bot token"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json()
        bot_token = data.get('bot_token', '').strip()

        if not bot_token:
            return jsonify({'error': 'Bot token is required'}), 400

        try:
            # Validate token by calling getMe
            resp = http_requests.get(f'https://api.telegram.org/bot{bot_token}/getMe')
            result = resp.json()

            if not result.get('ok'):
                return jsonify({'error': f'Invalid bot token: {result.get("description", "unknown error")}'}), 400

            bot_info = result['result']

            # Store connection
            superpower = Superpower.query.filter_by(
                user_id=user_id,
                service_type='telegram'
            ).first()

            if superpower:
                superpower.access_token_encrypted = bot_token
                superpower.is_enabled = True
                superpower.connected_at = datetime.utcnow()
                superpower.last_error = None
            else:
                superpower = Superpower(
                    user_id=user_id,
                    service_type='telegram',
                    service_name='Telegram',
                    category='connect',
                    is_enabled=True,
                    connected_at=datetime.utcnow(),
                    access_token_encrypted=bot_token,
                    usage_count=0,
                )
                db.session.add(superpower)

            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Telegram bot @{bot_info.get("username", "")} connected!',
                'bot': {
                    'username': bot_info.get('username'),
                    'first_name': bot_info.get('first_name'),
                }
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/telegram/me', methods=['GET'])
    def telegram_me():
        """Get bot info"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        superpower = Superpower.query.filter_by(
            user_id=user_id, service_type='telegram', is_enabled=True
        ).first()
        if not superpower or not superpower.access_token_encrypted:
            return jsonify({'error': 'Telegram not connected'}), 400

        try:
            token = superpower.access_token_encrypted
            resp = http_requests.get(f'https://api.telegram.org/bot{token}/getMe')
            result = resp.json()

            if not result.get('ok'):
                return jsonify({'error': result.get('description', 'API error')}), 400

            superpower.last_used = datetime.utcnow()
            db.session.commit()

            return jsonify({'success': True, 'bot': result['result']})

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/telegram/updates', methods=['GET'])
    def telegram_updates():
        """Get recent updates"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        superpower = Superpower.query.filter_by(
            user_id=user_id, service_type='telegram', is_enabled=True
        ).first()
        if not superpower or not superpower.access_token_encrypted:
            return jsonify({'error': 'Telegram not connected'}), 400

        try:
            token = superpower.access_token_encrypted
            resp = http_requests.get(
                f'https://api.telegram.org/bot{token}/getUpdates',
                params={'limit': 20}
            )
            result = resp.json()

            if not result.get('ok'):
                return jsonify({'error': result.get('description', 'API error')}), 400

            superpower.last_used = datetime.utcnow()
            db.session.commit()

            return jsonify({'success': True, 'updates': result['result']})

        except Exception as e:
            return jsonify({'error': str(e)}), 500
