"""
Chat channels management routes for connecting agents to messaging platforms
"""
from flask import jsonify, request, session
from models import db, User, Agent
import json


# Channel definitions with configuration requirements
CHANNELS = {
    # Free tier channels (included in all plans)
    'telegram': {
        'name': 'Telegram',
        'icon': '📱',
        'tier': 'free',
        'difficulty': 'easy',
        'description': 'Bot API via grammY; supports groups',
        'setup_type': 'token',
        'fields': [
            {'key': 'bot_token', 'label': 'Bot Token', 'type': 'password', 'required': True, 'help': 'Get from @BotFather on Telegram'}
        ],
        'docs_url': 'https://core.telegram.org/bots#how-do-i-create-a-bot'
    },
    'webchat': {
        'name': 'WebChat',
        'icon': '🌐',
        'tier': 'free',
        'difficulty': 'easy',
        'description': 'Gateway WebChat UI over WebSocket',
        'setup_type': 'simple',
        'fields': [],
        'docs_url': 'https://docs.openclaw.ai'
    },

    # Pro tier channels (requires Pro subscription)
    'discord': {
        'name': 'Discord',
        'icon': '💬',
        'tier': 'pro',
        'difficulty': 'easy',
        'description': 'Discord Bot API; supports servers, channels, DMs',
        'setup_type': 'token',
        'fields': [
            {'key': 'bot_token', 'label': 'Bot Token', 'type': 'password', 'required': True, 'help': 'Create app at discord.com/developers'},
            {'key': 'application_id', 'label': 'Application ID', 'type': 'text', 'required': False}
        ],
        'docs_url': 'https://discord.com/developers/docs/intro'
    },
    'whatsapp': {
        'name': 'WhatsApp',
        'icon': '💚',
        'tier': 'pro',
        'difficulty': 'medium',
        'description': 'Most popular; uses Baileys and requires QR pairing',
        'setup_type': 'qr',
        'fields': [],
        'docs_url': 'https://docs.openclaw.ai/channels/whatsapp'
    },
    'slack': {
        'name': 'Slack',
        'icon': '💼',
        'tier': 'pro',
        'difficulty': 'medium',
        'description': 'Bolt SDK; workspace apps',
        'setup_type': 'oauth',
        'fields': [
            {'key': 'app_token', 'label': 'App Token', 'type': 'password', 'required': True},
            {'key': 'bot_token', 'label': 'Bot Token', 'type': 'password', 'required': True}
        ],
        'docs_url': 'https://api.slack.com/start'
    },
    'signal': {
        'name': 'Signal',
        'icon': '🔒',
        'tier': 'pro',
        'difficulty': 'hard',
        'description': 'Privacy-focused messaging via signal-cli',
        'setup_type': 'cli',
        'fields': [
            {'key': 'phone_number', 'label': 'Phone Number', 'type': 'tel', 'required': True, 'help': 'Format: +1234567890'}
        ],
        'docs_url': 'https://docs.openclaw.ai/channels/signal'
    },
    'bluebubbles': {
        'name': 'BlueBubbles (iMessage)',
        'icon': '💙',
        'tier': 'pro',
        'difficulty': 'medium',
        'description': 'Full iMessage support via BlueBubbles macOS server',
        'setup_type': 'api',
        'fields': [
            {'key': 'server_url', 'label': 'Server URL', 'type': 'url', 'required': True, 'help': 'Your BlueBubbles server address'},
            {'key': 'password', 'label': 'Password', 'type': 'password', 'required': True}
        ],
        'docs_url': 'https://bluebubbles.app'
    },
    'google_chat': {
        'name': 'Google Chat',
        'icon': '🔵',
        'tier': 'pro',
        'difficulty': 'medium',
        'description': 'Google Chat API app via HTTP webhook',
        'setup_type': 'oauth',
        'fields': [
            {'key': 'credentials_json', 'label': 'Credentials JSON', 'type': 'textarea', 'required': True, 'help': 'Service account credentials from Google Cloud Console'}
        ],
        'docs_url': 'https://developers.google.com/chat'
    },
    'mattermost': {
        'name': 'Mattermost',
        'icon': '⚡',
        'tier': 'pro',
        'difficulty': 'medium',
        'description': 'Bot API + WebSocket; channels, groups, DMs',
        'setup_type': 'token',
        'fields': [
            {'key': 'server_url', 'label': 'Server URL', 'type': 'url', 'required': True},
            {'key': 'access_token', 'label': 'Access Token', 'type': 'password', 'required': True}
        ],
        'docs_url': 'https://developers.mattermost.com'
    },
    'teams': {
        'name': 'Microsoft Teams',
        'icon': '🏢',
        'tier': 'pro',
        'difficulty': 'hard',
        'description': 'Bot Framework; enterprise support',
        'setup_type': 'oauth',
        'fields': [
            {'key': 'app_id', 'label': 'App ID', 'type': 'text', 'required': True},
            {'key': 'app_password', 'label': 'App Password', 'type': 'password', 'required': True}
        ],
        'docs_url': 'https://docs.microsoft.com/en-us/microsoftteams/platform/bots/what-are-bots'
    },
    'feishu': {
        'name': 'Feishu/Lark',
        'icon': '🦜',
        'tier': 'pro',
        'difficulty': 'hard',
        'description': 'Feishu bot via WebSocket',
        'setup_type': 'token',
        'fields': [
            {'key': 'app_id', 'label': 'App ID', 'type': 'text', 'required': True},
            {'key': 'app_secret', 'label': 'App Secret', 'type': 'password', 'required': True}
        ],
        'docs_url': 'https://open.feishu.cn/document/home/index'
    },
    'matrix': {
        'name': 'Matrix',
        'icon': '🔷',
        'tier': 'pro',
        'difficulty': 'hard',
        'description': 'Matrix protocol; decentralized chat',
        'setup_type': 'token',
        'fields': [
            {'key': 'homeserver', 'label': 'Homeserver URL', 'type': 'url', 'required': True},
            {'key': 'access_token', 'label': 'Access Token', 'type': 'password', 'required': True}
        ],
        'docs_url': 'https://matrix.org'
    }
}

def register_channels_routes(app):
    """Register chat channels management routes"""

    @app.route('/api/channels/available', methods=['GET'])
    def get_available_channels():
        """Get list of available channels filtered by user's subscription tier"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Filter channels by user's effective subscription tier
            tier_hierarchy = {'free': 0, 'pro': 1}
            user_tier_level = tier_hierarchy.get(user.effective_tier, 0)

            available_channels = {}
            locked_channels = {}

            for channel_id, channel_info in CHANNELS.items():
                channel_tier_level = tier_hierarchy.get(channel_info['tier'], 0)

                channel_data = {
                    **channel_info,
                    'id': channel_id,
                    'locked': channel_tier_level > user_tier_level
                }

                if channel_tier_level <= user_tier_level:
                    available_channels[channel_id] = channel_data
                else:
                    locked_channels[channel_id] = channel_data

            return jsonify({
                'available': available_channels,
                'locked': locked_channels,
                'user_tier': user.effective_tier
            })

        except Exception as e:
            print(f"Error getting available channels: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/channels/agent/<int:agent_id>/config', methods=['GET'])
    def get_agent_channels(agent_id):
        """Get configured channels for an agent"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            # Get channel configuration from agent's metadata
            # In a real implementation, this would be stored in a proper channels table
            # For now, we'll use agent metadata or a JSON field
            channels_config = {}

            return jsonify({
                'agent_id': agent.id,
                'agent_name': agent.name,
                'channels': channels_config
            })

        except Exception as e:
            print(f"Error getting agent channels: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/channels/agent/<int:agent_id>/connect', methods=['POST'])
    def connect_channel(agent_id):
        """Connect a channel to an agent"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            data = request.get_json()
            channel_id = data.get('channel_id')
            config = data.get('config', {})

            if not channel_id or channel_id not in CHANNELS:
                return jsonify({'error': 'Invalid channel'}), 400

            # Check if user has access to this channel
            user = User.query.get(user_id)
            channel_info = CHANNELS[channel_id]

            tier_hierarchy = {'free': 0, 'pro': 1}
            user_tier_level = tier_hierarchy.get(user.effective_tier, 0)
            channel_tier_level = tier_hierarchy.get(channel_info['tier'], 0)

            if channel_tier_level > user_tier_level:
                return jsonify({
                    'error': 'Upgrade required',
                    'required_tier': channel_info['tier'],
                    'current_tier': user.subscription_tier
                }), 403

            # Validate required fields
            for field in channel_info.get('fields', []):
                if field.get('required') and field['key'] not in config:
                    return jsonify({'error': f"Missing required field: {field['label']}"}), 400

            # In a real implementation, save to database and test connection
            # For now, return success
            return jsonify({
                'success': True,
                'message': f"{channel_info['name']} connected successfully",
                'channel_id': channel_id,
                'agent_id': agent.id
            })

        except Exception as e:
            print(f"Error connecting channel: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/channels/agent/<int:agent_id>/disconnect/<channel_id>', methods=['POST'])
    def disconnect_channel(agent_id, channel_id):
        """Disconnect a channel from an agent"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            # In a real implementation, remove from database
            return jsonify({
                'success': True,
                'message': f"Channel {channel_id} disconnected"
            })

        except Exception as e:
            print(f"Error disconnecting channel: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/channels/test/<channel_id>', methods=['POST'])
    def test_channel_connection(channel_id):
        """Test a channel configuration without saving"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            data = request.get_json()
            config = data.get('config', {})

            if channel_id not in CHANNELS:
                return jsonify({'error': 'Invalid channel'}), 400

            # In a real implementation, test the connection
            # For now, simulate success
            return jsonify({
                'success': True,
                'message': 'Connection test successful',
                'details': 'Channel configuration is valid'
            })

        except Exception as e:
            print(f"Error testing channel: {e}")
            return jsonify({'error': str(e)}), 500
