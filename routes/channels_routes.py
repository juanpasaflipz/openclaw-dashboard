"""
Chat channels management routes for connecting agents to messaging platforms.
Includes Telegram webhook handler with voice transcription.
"""
from flask import jsonify, request, session
from models import db, User, Agent, Superpower, ChatConversation, ChatMessage, UserModelConfig
from rate_limiter import limiter
import json
import os
import secrets
import requests
import tempfile


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


# ============================================
# Telegram adapter functions
# ============================================

def _parse_telegram_message(update):
    """Extract chat_id, user_id, text, voice from a Telegram webhook update."""
    message = update.get('message') or update.get('edited_message')
    if not message:
        return None

    return {
        'chat_id': str(message['chat']['id']),
        'user_id': str(message['from']['id']),
        'username': message['from'].get('username', ''),
        'first_name': message['from'].get('first_name', ''),
        'text': message.get('text', ''),
        'voice': message.get('voice'),
        'audio': message.get('audio'),
    }


def _send_telegram_response(bot_token, chat_id, text):
    """Send a text reply via Telegram Bot API. Truncates at 4000 chars."""
    if len(text) > 4000:
        text = text[:4000] + '...'

    resp = requests.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'},
        timeout=15,
    )
    # If Markdown parsing fails, retry without it
    if not resp.ok and 'parse' in resp.text.lower():
        requests.post(
            f'https://api.telegram.org/bot{bot_token}/sendMessage',
            json={'chat_id': chat_id, 'text': text},
            timeout=15,
        )


def _send_telegram_typing(bot_token, chat_id):
    """Send typing indicator for instant user feedback."""
    try:
        requests.post(
            f'https://api.telegram.org/bot{bot_token}/sendChatAction',
            json={'chat_id': chat_id, 'action': 'typing'},
            timeout=5,
        )
    except Exception:
        pass  # Non-critical


def _download_telegram_voice(bot_token, file_id):
    """Download a voice/audio file from Telegram. Returns local path or None."""
    try:
        # Get file path from Telegram
        resp = requests.get(
            f'https://api.telegram.org/bot{bot_token}/getFile',
            params={'file_id': file_id},
            timeout=10,
        )
        if not resp.ok:
            return None

        file_path = resp.json().get('result', {}).get('file_path')
        if not file_path:
            return None

        # Download the file
        dl_resp = requests.get(
            f'https://api.telegram.org/file/bot{bot_token}/{file_path}',
            timeout=30,
        )
        if not dl_resp.ok:
            return None

        # Determine extension from file_path
        ext = '.ogg'
        if '.' in file_path:
            ext = '.' + file_path.rsplit('.', 1)[-1]

        # Save to temp file
        fd, local_path = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd, 'wb') as f:
            f.write(dl_resp.content)

        return local_path
    except Exception as e:
        print(f"Error downloading Telegram voice: {e}")
        return None


# ============================================
# Speech-to-Text transcription
# ============================================

def _transcribe_voice(user_id, audio_path):
    """Route to user's configured STT provider, with fallback to OPENAI_API_KEY env var."""
    stt_config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot='stt').first()

    if stt_config:
        if stt_config.provider in ('stt_openai', 'openai'):
            return _transcribe_openai_whisper(stt_config.api_key, audio_path)
        elif stt_config.provider in ('stt_groq', 'groq'):
            return _transcribe_groq_whisper(stt_config.api_key, audio_path)

    # Fallback: use OPENAI_API_KEY env var
    openai_key = os.environ.get('OPENAI_API_KEY')
    if openai_key:
        return _transcribe_openai_whisper(openai_key, audio_path)

    return None


def _transcribe_openai_whisper(api_key, path):
    """Transcribe audio using OpenAI Whisper API."""
    try:
        with open(path, 'rb') as f:
            resp = requests.post(
                'https://api.openai.com/v1/audio/transcriptions',
                headers={'Authorization': f'Bearer {api_key}'},
                files={'file': f},
                data={'model': 'whisper-1'},
                timeout=60,
            )
        if resp.ok:
            return resp.json().get('text', '')
        print(f"Whisper API error: {resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return None


def _transcribe_groq_whisper(api_key, path):
    """Transcribe audio using Groq Whisper API."""
    try:
        with open(path, 'rb') as f:
            resp = requests.post(
                'https://api.groq.com/openai/v1/audio/transcriptions',
                headers={'Authorization': f'Bearer {api_key}'},
                files={'file': f},
                data={'model': 'whisper-large-v3'},
                timeout=60,
            )
        if resp.ok:
            return resp.json().get('text', '')
        print(f"Groq Whisper error: {resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"Groq transcription error: {e}")
        return None


# ============================================
# Channel conversation management
# ============================================

def _get_or_create_channel_conversation(user_id, platform, chat_id, metadata=None):
    """Find or create a ChatConversation for a channel (platform + chat_id)."""
    conv = ChatConversation.query.filter_by(
        user_id=user_id,
        channel_platform=platform,
        channel_chat_id=chat_id,
    ).first()

    if not conv:
        conv = ChatConversation(
            conversation_id=secrets.token_urlsafe(16),
            user_id=user_id,
            title=f'{platform.capitalize()} Chat',
            feature='chatbot',
            agent_type='direct_llm',
            channel_platform=platform,
            channel_chat_id=chat_id,
            channel_metadata=metadata,
        )
        db.session.add(conv)
        db.session.flush()

    return conv


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

            # Check which channels are already connected via Superpower table
            connected_services = {
                sp.service_type: sp.is_enabled
                for sp in Superpower.query.filter_by(user_id=user_id).all()
            }

            available_channels = {}
            locked_channels = {}

            for channel_id, channel_info in CHANNELS.items():
                channel_tier_level = tier_hierarchy.get(channel_info['tier'], 0)

                channel_data = {
                    **channel_info,
                    'id': channel_id,
                    'locked': channel_tier_level > user_tier_level,
                    'connected': connected_services.get(channel_id, False)
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

            return jsonify({
                'success': True,
                'message': 'Connection test successful',
                'details': 'Channel configuration is valid'
            })

        except Exception as e:
            print(f"Error testing channel: {e}")
            return jsonify({'error': str(e)}), 500

    # ============================================
    # Telegram: activate / deactivate / webhook
    # ============================================

    @app.route('/api/channels/telegram/activate', methods=['POST'])
    def activate_telegram():
        """Register Telegram webhook and store owner_telegram_id."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        owner_telegram_id = str(data.get('owner_telegram_id', '')).strip()
        if not owner_telegram_id:
            return jsonify({'error': 'owner_telegram_id is required (your numeric Telegram user ID)'}), 400

        # Get the Telegram superpower (holds bot_token)
        sp = Superpower.query.filter_by(user_id=user_id, service_type='telegram').first()
        if not sp or not sp.access_token_encrypted:
            return jsonify({'error': 'Telegram bot not connected. Connect it in Superpowers first.'}), 400

        bot_token = sp.access_token_encrypted

        # Build webhook URL
        base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
        webhook_url = f'{base_url}/api/channels/telegram/webhook'

        # Register webhook with Telegram
        try:
            resp = requests.post(
                f'https://api.telegram.org/bot{bot_token}/setWebhook',
                json={'url': webhook_url},
                timeout=10,
            )
            if not resp.ok:
                return jsonify({'error': f'Telegram setWebhook failed: {resp.text[:200]}'}), 502
        except requests.RequestException as e:
            return jsonify({'error': f'Failed to reach Telegram API: {str(e)[:200]}'}), 502

        # Store owner_telegram_id in superpower config
        config = json.loads(sp.config) if sp.config else {}
        config['owner_telegram_id'] = owner_telegram_id
        config['webhook_active'] = True
        sp.config = json.dumps(config)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Telegram webhook activated',
            'webhook_url': webhook_url,
        })

    @app.route('/api/channels/telegram/deactivate', methods=['POST'])
    def deactivate_telegram():
        """Remove Telegram webhook."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        sp = Superpower.query.filter_by(user_id=user_id, service_type='telegram').first()
        if not sp or not sp.access_token_encrypted:
            return jsonify({'error': 'Telegram bot not connected'}), 400

        bot_token = sp.access_token_encrypted

        try:
            requests.post(
                f'https://api.telegram.org/bot{bot_token}/deleteWebhook',
                timeout=10,
            )
        except Exception:
            pass  # Best effort

        config = json.loads(sp.config) if sp.config else {}
        config['webhook_active'] = False
        sp.config = json.dumps(config)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Telegram webhook deactivated'})

    @app.route('/api/channels/telegram/webhook', methods=['POST'])
    @limiter.exempt
    def telegram_webhook():
        """
        Main Telegram webhook handler.
        1. Parse incoming message
        2. Match sender to owner via Superpower config
        3. Voice? Download + transcribe
        4. Get/create conversation
        5. Run LLM pipeline (with all tools)
        6. Send response back via Telegram
        Always returns 200 to prevent Telegram retries.
        """
        try:
            update = request.get_json(silent=True) or {}
            parsed = _parse_telegram_message(update)
            if not parsed:
                return jsonify({'ok': True})

            sender_tg_id = parsed['user_id']
            chat_id = parsed['chat_id']

            # Find the owner: match sender's telegram user_id against all Superpowers
            sp = _find_superpower_by_telegram_id(sender_tg_id)
            if not sp:
                # Not the owner — silently ignore
                return jsonify({'ok': True})

            bot_token = sp.access_token_encrypted
            owner_user_id = sp.user_id

            # Send typing indicator immediately
            _send_telegram_typing(bot_token, chat_id)

            # Determine message text
            message_text = parsed['text']

            # Handle voice/audio messages
            voice = parsed.get('voice') or parsed.get('audio')
            if voice and not message_text:
                file_id = voice.get('file_id')
                if file_id:
                    audio_path = _download_telegram_voice(bot_token, file_id)
                    if audio_path:
                        try:
                            transcribed = _transcribe_voice(owner_user_id, audio_path)
                            if transcribed:
                                message_text = transcribed
                            else:
                                _send_telegram_response(bot_token, chat_id,
                                    'Could not transcribe voice message. Please configure an STT provider or set OPENAI_API_KEY.')
                                return jsonify({'ok': True})
                        finally:
                            # Clean up temp file
                            try:
                                os.unlink(audio_path)
                            except Exception:
                                pass
                    else:
                        _send_telegram_response(bot_token, chat_id, 'Could not download voice message.')
                        return jsonify({'ok': True})

            if not message_text:
                return jsonify({'ok': True})

            # Get or create conversation for this Telegram chat
            metadata = {
                'username': parsed.get('username', ''),
                'first_name': parsed.get('first_name', ''),
            }
            conv = _get_or_create_channel_conversation(owner_user_id, 'telegram', chat_id, metadata)

            # Run the shared LLM pipeline (with tool-calling loop)
            from routes.chatbot_routes import run_llm_pipeline
            result = run_llm_pipeline(owner_user_id, conv.conversation_id, message_text)

            if result['success']:
                response_text = result.get('last_assistant_content', '')
                if not response_text:
                    response_text = 'I processed your request but have no text response.'
            else:
                response_text = f"Error: {result.get('error', 'Unknown error')}"

            _send_telegram_response(bot_token, chat_id, response_text)

        except Exception as e:
            print(f"Telegram webhook error: {e}")
            # Try to notify user if we have enough context
            try:
                if bot_token and chat_id:
                    _send_telegram_response(bot_token, chat_id, f'Internal error: {str(e)[:200]}')
            except Exception:
                pass

        # Always return 200 to prevent Telegram retries
        return jsonify({'ok': True})


def _find_superpower_by_telegram_id(telegram_user_id):
    """Find the Superpower whose config.owner_telegram_id matches the sender."""
    superpowers = Superpower.query.filter_by(service_type='telegram', is_enabled=True).all()
    for sp in superpowers:
        if not sp.config:
            continue
        try:
            config = json.loads(sp.config) if isinstance(sp.config, str) else sp.config
        except (json.JSONDecodeError, TypeError):
            continue
        if str(config.get('owner_telegram_id', '')) == str(telegram_user_id):
            return sp
    return None
