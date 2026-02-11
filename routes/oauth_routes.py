"""
OAuth routes for connecting external services (Gmail, Google Calendar, etc.)
"""
from flask import jsonify, request, session, redirect, url_for
from models import db, User, Superpower
import os
import json
import secrets
import base64
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import requests as http_requests


# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/api/oauth/google/callback')

# OAuth Scopes for different Google services
GOOGLE_SCOPES = {
    'gmail': [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.labels',
    ],
    'calendar': [
        'https://www.googleapis.com/auth/calendar.readonly',
        'https://www.googleapis.com/auth/calendar.events',
    ],
    'drive': [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/drive.file',
    ]
}


def register_oauth_routes(app):
    """Register OAuth routes"""

    @app.route('/api/oauth/google/start/<service>', methods=['GET'])
    def start_google_oauth(service):
        """
        Initiate Google OAuth flow for a specific service.

        Args:
            service: 'gmail', 'calendar', or 'drive'
        """
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            if service not in GOOGLE_SCOPES:
                return jsonify({'error': 'Invalid service'}), 400

            # Check if Google OAuth is configured
            if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                return jsonify({
                    'error': 'Google OAuth not configured',
                    'message': 'Administrator needs to set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET'
                }), 500

            # Store service type in session for callback
            session['oauth_service'] = service
            session['oauth_agent_id'] = request.args.get('agent_id')  # Optional: connect to specific agent

            # Create OAuth flow
            flow = Flow.from_client_config(
                {
                    'web': {
                        'client_id': GOOGLE_CLIENT_ID,
                        'client_secret': GOOGLE_CLIENT_SECRET,
                        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                        'token_uri': 'https://oauth2.googleapis.com/token',
                        'redirect_uris': [GOOGLE_REDIRECT_URI]
                    }
                },
                scopes=GOOGLE_SCOPES[service]
            )
            flow.redirect_uri = GOOGLE_REDIRECT_URI

            # Generate authorization URL
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'  # Force consent to get refresh token
            )

            # Store state in session for security
            session['oauth_state'] = state

            return jsonify({
                'authorization_url': authorization_url,
                'service': service
            })

        except Exception as e:
            print(f"❌ Error starting OAuth: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/oauth/google/callback', methods=['GET'])
    def google_oauth_callback():
        """Handle OAuth callback from Google"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return '''
                <html>
                    <head><title>Authentication Required</title></head>
                    <body style="font-family: system-ui; text-align: center; padding: 50px;">
                        <h1>⚠️ Authentication Required</h1>
                        <p>Please log in to the dashboard first.</p>
                        <script>
                            setTimeout(() => {
                                window.location.href = '/';
                            }, 3000);
                        </script>
                    </body>
                </html>
                '''

            # Verify state to prevent CSRF
            state = request.args.get('state')
            if state != session.get('oauth_state'):
                return jsonify({'error': 'Invalid state parameter'}), 400

            # Get service type from session
            service = session.get('oauth_service')
            agent_id = session.get('oauth_agent_id')

            if not service:
                return jsonify({'error': 'OAuth session expired'}), 400

            # Exchange code for tokens
            flow = Flow.from_client_config(
                {
                    'web': {
                        'client_id': GOOGLE_CLIENT_ID,
                        'client_secret': GOOGLE_CLIENT_SECRET,
                        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                        'token_uri': 'https://oauth2.googleapis.com/token',
                        'redirect_uris': [GOOGLE_REDIRECT_URI]
                    }
                },
                scopes=GOOGLE_SCOPES[service]
            )
            flow.redirect_uri = GOOGLE_REDIRECT_URI

            # Fetch tokens
            flow.fetch_token(authorization_response=request.url)

            # Get credentials
            credentials = flow.credentials

            # Store the connection in database
            # TODO: Encrypt tokens before storing
            superpower = Superpower.query.filter_by(
                user_id=user_id,
                service_type=service
            ).first()

            if superpower:
                # Update existing connection
                superpower.access_token_encrypted = credentials.token
                superpower.refresh_token_encrypted = credentials.refresh_token
                superpower.token_expires_at = credentials.expiry
                superpower.scopes_granted = json.dumps(list(credentials.scopes))
                superpower.connected_at = datetime.utcnow()
                superpower.is_enabled = True
            else:
                # Create new connection
                superpower = Superpower(
                    user_id=user_id,
                    agent_id=agent_id,
                    service_type=service,
                    service_name=f'Google {service.capitalize()}',
                    category='connect',
                    access_token_encrypted=credentials.token,
                    refresh_token_encrypted=credentials.refresh_token,
                    token_expires_at=credentials.expiry,
                    scopes_granted=json.dumps(list(credentials.scopes))
                )
                db.session.add(superpower)

            db.session.commit()

            # Clean up session
            session.pop('oauth_service', None)
            session.pop('oauth_state', None)
            session.pop('oauth_agent_id', None)

            print(f"✅ {service.capitalize()} connected for user {user_id}")

            return '''
            <html>
                <head><title>Connection Successful</title></head>
                <body style="font-family: system-ui; text-align: center; padding: 50px;">
                    <h1>✅ Connection Successful!</h1>
                    <p>''' + service.capitalize() + ''' is now connected.</p>
                    <p>You can close this window and return to the dashboard.</p>
                    <script>
                        setTimeout(() => {
                            window.location.href = '/?tab=connect';
                        }, 2000);
                    </script>
                </body>
            </html>
            '''

        except Exception as e:
            print(f"❌ Error in OAuth callback: {e}")
            return f'''
            <html>
                <head><title>Connection Failed</title></head>
                <body style="font-family: system-ui; text-align: center; padding: 50px;">
                    <h1>❌ Connection Failed</h1>
                    <p>Error: {str(e)}</p>
                    <button onclick="window.location.href='/'">Return to Dashboard</button>
                </body>
            </html>
            '''

    @app.route('/api/superpowers/list', methods=['GET'])
    def list_superpowers():
        """Get list of connected superpowers for current user"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            superpowers = Superpower.query.filter_by(user_id=user_id).all()

            return jsonify({
                'superpowers': [{
                    'id': sp.id,
                    'service_type': sp.service_type,
                    'service_name': sp.service_name,
                    'category': sp.category,
                    'is_enabled': sp.is_enabled,
                    'connected_at': sp.connected_at.isoformat() if sp.connected_at else None,
                    'last_used': sp.last_used.isoformat() if sp.last_used else None,
                    'usage_count': sp.usage_count
                } for sp in superpowers]
            })

        except Exception as e:
            print(f"❌ Error listing superpowers: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/superpowers/<int:superpower_id>/disconnect', methods=['POST'])
    def disconnect_superpower(superpower_id):
        """Disconnect a superpower"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            superpower = Superpower.query.filter_by(
                id=superpower_id,
                user_id=user_id
            ).first()

            if not superpower:
                return jsonify({'error': 'Superpower not found'}), 404

            # Delete the connection
            service_name = superpower.service_name
            db.session.delete(superpower)
            db.session.commit()

            print(f"✅ {service_name} disconnected for user {user_id}")

            return jsonify({
                'success': True,
                'message': f'{service_name} has been disconnected'
            })

        except Exception as e:
            print(f"❌ Error disconnecting superpower: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # ========================================
    # Generic OAuth for third-party services
    # ========================================

    OAUTH_PROVIDERS = {
        'slack': {
            'client_id_env': 'SLACK_CLIENT_ID',
            'client_secret_env': 'SLACK_CLIENT_SECRET',
            'authorize_url': 'https://slack.com/oauth/v2/authorize',
            'token_url': 'https://slack.com/api/oauth.v2.access',
            'scopes': ['channels:read', 'chat:read', 'users:read', 'team:read'],
            'service_name': 'Slack',
            'category': 'connect',
            'token_response_key': 'authed_user.access_token',
        },
        'github': {
            'client_id_env': 'GITHUB_CLIENT_ID',
            'client_secret_env': 'GITHUB_CLIENT_SECRET',
            'authorize_url': 'https://github.com/login/oauth/authorize',
            'token_url': 'https://github.com/login/oauth/access_token',
            'scopes': ['repo', 'read:user', 'read:org'],
            'scope_separator': ',',
            'service_name': 'GitHub',
            'category': 'connect',
            'token_request_headers': {'Accept': 'application/json'},
        },
        'discord': {
            'client_id_env': 'DISCORD_CLIENT_ID',
            'client_secret_env': 'DISCORD_CLIENT_SECRET',
            'authorize_url': 'https://discord.com/api/oauth2/authorize',
            'token_url': 'https://discord.com/api/oauth2/token',
            'scopes': ['identify', 'guilds', 'guilds.members.read'],
            'service_name': 'Discord',
            'category': 'connect',
        },
        'spotify': {
            'client_id_env': 'SPOTIFY_CLIENT_ID',
            'client_secret_env': 'SPOTIFY_CLIENT_SECRET',
            'authorize_url': 'https://accounts.spotify.com/authorize',
            'token_url': 'https://accounts.spotify.com/api/token',
            'scopes': ['user-read-private', 'user-read-email', 'user-read-playback-state',
                       'user-read-currently-playing', 'playlist-read-private'],
            'service_name': 'Spotify',
            'category': 'connect',
            'token_auth': 'basic',
        },
        'todoist': {
            'client_id_env': 'TODOIST_CLIENT_ID',
            'client_secret_env': 'TODOIST_CLIENT_SECRET',
            'authorize_url': 'https://todoist.com/oauth/authorize',
            'token_url': 'https://todoist.com/oauth/access_token',
            'scopes': ['data:read'],
            'service_name': 'Todoist',
            'category': 'connect',
        },
        'dropbox': {
            'client_id_env': 'DROPBOX_CLIENT_ID',
            'client_secret_env': 'DROPBOX_CLIENT_SECRET',
            'authorize_url': 'https://www.dropbox.com/oauth2/authorize',
            'token_url': 'https://api.dropboxapi.com/oauth2/token',
            'scopes': [],
            'service_name': 'Dropbox',
            'category': 'connect',
            'extra_auth_params': {'token_access_type': 'offline'},
        },
    }

    @app.route('/api/oauth/<provider>/start', methods=['GET'])
    def start_oauth(provider):
        """Initiate OAuth flow for a third-party provider"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            if provider not in OAUTH_PROVIDERS:
                return jsonify({'error': 'Unknown provider'}), 400

            config = OAUTH_PROVIDERS[provider]
            client_id = os.environ.get(config['client_id_env'])
            client_secret = os.environ.get(config['client_secret_env'])

            if not client_id or not client_secret:
                return jsonify({
                    'error': f'{config["service_name"]} OAuth not configured',
                    'message': f'Administrator needs to set {config["client_id_env"]} and {config["client_secret_env"]}'
                }), 500

            base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
            redirect_uri = f'{base_url}/api/oauth/{provider}/callback'

            state = secrets.token_urlsafe(32)
            session[f'oauth_state_{provider}'] = state

            separator = config.get('scope_separator', ' ')
            scope_str = separator.join(config['scopes'])

            params = {
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'response_type': 'code',
                'state': state,
            }
            if scope_str:
                params['scope'] = scope_str

            # Add extra auth params (e.g. Dropbox token_access_type)
            extra = config.get('extra_auth_params', {})
            params.update(extra)

            from urllib.parse import urlencode
            authorization_url = f'{config["authorize_url"]}?{urlencode(params)}'

            return jsonify({'authorization_url': authorization_url})

        except Exception as e:
            print(f"Error starting {provider} OAuth: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/oauth/<provider>/callback', methods=['GET'])
    def oauth_callback(provider):
        """Handle OAuth callback for a third-party provider"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return '<html><body style="font-family:system-ui;text-align:center;padding:50px;"><h1>Authentication Required</h1><p>Please log in first.</p><script>setTimeout(()=>window.location.href="/",3000)</script></body></html>'

            if provider not in OAUTH_PROVIDERS:
                return '<html><body style="font-family:system-ui;text-align:center;padding:50px;"><h1>Unknown Provider</h1></body></html>'

            state = request.args.get('state')
            if state != session.get(f'oauth_state_{provider}'):
                return '<html><body style="font-family:system-ui;text-align:center;padding:50px;"><h1>Invalid State</h1><p>OAuth state mismatch. Please try again.</p></body></html>'

            code = request.args.get('code')
            if not code:
                error = request.args.get('error', 'unknown')
                return f'<html><body style="font-family:system-ui;text-align:center;padding:50px;"><h1>Authorization Failed</h1><p>{error}</p></body></html>'

            config = OAUTH_PROVIDERS[provider]
            client_id = os.environ.get(config['client_id_env'])
            client_secret = os.environ.get(config['client_secret_env'])
            base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
            redirect_uri = f'{base_url}/api/oauth/{provider}/callback'

            # Exchange code for tokens
            token_data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            }

            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            headers.update(config.get('token_request_headers', {}))

            # Spotify requires Basic auth for token exchange
            if config.get('token_auth') == 'basic':
                creds = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
                headers['Authorization'] = f'Basic {creds}'
                del token_data['client_id']
                del token_data['client_secret']

            resp = http_requests.post(config['token_url'], data=token_data, headers=headers)
            token_json = resp.json()

            if resp.status_code != 200 and 'access_token' not in token_json:
                error_msg = token_json.get('error_description', token_json.get('error', 'Token exchange failed'))
                raise Exception(error_msg)

            # Extract access token (handle non-standard responses like Slack)
            token_key = config.get('token_response_key', 'access_token')
            access_token = token_json
            for key_part in token_key.split('.'):
                access_token = access_token.get(key_part, {}) if isinstance(access_token, dict) else None
            if not access_token or isinstance(access_token, dict):
                access_token = token_json.get('access_token')

            refresh_token = token_json.get('refresh_token')
            expires_in = token_json.get('expires_in')
            token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in)) if expires_in else None

            # Store connection
            superpower = Superpower.query.filter_by(
                user_id=user_id,
                service_type=provider
            ).first()

            if superpower:
                superpower.access_token_encrypted = access_token
                superpower.refresh_token_encrypted = refresh_token
                superpower.token_expires_at = token_expires_at
                superpower.scopes_granted = json.dumps(config['scopes'])
                superpower.connected_at = datetime.utcnow()
                superpower.is_enabled = True
            else:
                superpower = Superpower(
                    user_id=user_id,
                    service_type=provider,
                    service_name=config['service_name'],
                    category=config['category'],
                    access_token_encrypted=access_token,
                    refresh_token_encrypted=refresh_token,
                    token_expires_at=token_expires_at,
                    scopes_granted=json.dumps(config['scopes']),
                )
                db.session.add(superpower)

            db.session.commit()

            session.pop(f'oauth_state_{provider}', None)
            print(f"{config['service_name']} connected for user {user_id}")

            service_name = config['service_name']
            return f'''
            <html>
                <head><title>Connection Successful</title></head>
                <body style="font-family: system-ui; text-align: center; padding: 50px;">
                    <h1>Connection Successful!</h1>
                    <p>{service_name} is now connected.</p>
                    <p>You can close this window and return to the dashboard.</p>
                    <script>
                        setTimeout(() => {{ window.location.href = '/?tab=connect'; }}, 2000);
                    </script>
                </body>
            </html>
            '''

        except Exception as e:
            print(f"Error in {provider} OAuth callback: {e}")
            return f'''
            <html>
                <head><title>Connection Failed</title></head>
                <body style="font-family: system-ui; text-align: center; padding: 50px;">
                    <h1>Connection Failed</h1>
                    <p>Error: {str(e)}</p>
                    <button onclick="window.location.href='/'">Return to Dashboard</button>
                </body>
            </html>
            '''


def refresh_oauth_token(superpower, provider_key):
    """Refresh an expired OAuth token for a third-party provider.
    Returns True if refresh succeeded, False otherwise."""
    from routes.oauth_routes import register_oauth_routes
    # Access the OAUTH_PROVIDERS from the closure isn't possible, so we define it here too
    providers = {
        'spotify': {
            'client_id_env': 'SPOTIFY_CLIENT_ID',
            'client_secret_env': 'SPOTIFY_CLIENT_SECRET',
            'token_url': 'https://accounts.spotify.com/api/token',
            'token_auth': 'basic',
        },
        'discord': {
            'client_id_env': 'DISCORD_CLIENT_ID',
            'client_secret_env': 'DISCORD_CLIENT_SECRET',
            'token_url': 'https://discord.com/api/oauth2/token',
        },
        'dropbox': {
            'client_id_env': 'DROPBOX_CLIENT_ID',
            'client_secret_env': 'DROPBOX_CLIENT_SECRET',
            'token_url': 'https://api.dropboxapi.com/oauth2/token',
        },
    }

    config = providers.get(provider_key)
    if not config or not superpower.refresh_token_encrypted:
        return False

    client_id = os.environ.get(config['client_id_env'])
    client_secret = os.environ.get(config['client_secret_env'])
    if not client_id or not client_secret:
        return False

    token_data = {
        'grant_type': 'refresh_token',
        'refresh_token': superpower.refresh_token_encrypted,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    if config.get('token_auth') == 'basic':
        creds = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
        headers['Authorization'] = f'Basic {creds}'
    else:
        token_data['client_id'] = client_id
        token_data['client_secret'] = client_secret

    try:
        resp = http_requests.post(config['token_url'], data=token_data, headers=headers)
        token_json = resp.json()

        if resp.status_code != 200 or 'access_token' not in token_json:
            print(f"Token refresh failed for {provider_key}: {token_json}")
            return False

        superpower.access_token_encrypted = token_json['access_token']
        if token_json.get('refresh_token'):
            superpower.refresh_token_encrypted = token_json['refresh_token']
        expires_in = token_json.get('expires_in')
        if expires_in:
            superpower.token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
        db.session.commit()
        return True

    except Exception as e:
        print(f"Error refreshing {provider_key} token: {e}")
        return False
