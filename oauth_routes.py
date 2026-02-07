"""
OAuth routes for connecting external services (Gmail, Google Calendar, etc.)
"""
from flask import jsonify, request, session, redirect, url_for
from models import db, User, Superpower
import os
import json
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build


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
