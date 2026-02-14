"""
Gmail integration routes - Read and send emails
"""
from flask import jsonify, request, session
from models import db, User, Superpower
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import json
import os


def get_gmail_service(user_id):
    """
    Get authenticated Gmail API service for a user.

    Returns:
        Gmail API service object or (None, error_message)
    """
    try:
        # Get Gmail superpower for user
        superpower = Superpower.query.filter_by(
            user_id=user_id,
            service_type='gmail',
            is_enabled=True
        ).first()

        if not superpower:
            return None, 'Gmail not connected'

        if not superpower.access_token_encrypted:
            return None, 'Gmail access token missing'

        # Create credentials object with OAuth client info for token refresh
        # TODO: Decrypt tokens
        credentials = Credentials(
            token=superpower.access_token_encrypted,
            refresh_token=superpower.refresh_token_encrypted,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.environ.get('GOOGLE_CLIENT_ID'),
            client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
            scopes=json.loads(superpower.scopes_granted) if superpower.scopes_granted else []
        )

        # Build Gmail service
        service = build('gmail', 'v1', credentials=credentials)

        # Update last used
        superpower.last_used = datetime.utcnow()
        superpower.usage_count = (superpower.usage_count or 0) + 1
        db.session.commit()

        return service, None

    except Exception as e:
        return None, str(e)


def register_gmail_routes(app):
    """Register Gmail-specific routes"""

    @app.route('/api/gmail/recent', methods=['GET'])
    def get_recent_emails():
        """Get recent emails from Gmail"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            # Get limit from query params
            limit = request.args.get('limit', 10, type=int)
            limit = min(limit, 50)  # Cap at 50

            # Get Gmail service
            service, error = get_gmail_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # List messages
            results = service.users().messages().list(
                userId='me',
                maxResults=limit,
                labelIds=['INBOX']
            ).execute()

            messages = results.get('messages', [])

            # Fetch full message details
            emails = []
            for msg in messages:
                message = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'To', 'Subject', 'Date']
                ).execute()

                headers = {}
                for header in message.get('payload', {}).get('headers', []):
                    headers[header['name']] = header['value']

                emails.append({
                    'id': message['id'],
                    'threadId': message['threadId'],
                    'from': headers.get('From', ''),
                    'to': headers.get('To', ''),
                    'subject': headers.get('Subject', ''),
                    'date': headers.get('Date', ''),
                    'snippet': message.get('snippet', '')
                })

            return jsonify({
                'success': True,
                'emails': emails,
                'count': len(emails)
            })

        except HttpError as error:
            print(f"❌ Gmail API error: {error}")
            return jsonify({'error': 'An internal error occurred'}), 500
        except Exception as e:
            print(f"❌ Error fetching emails: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/gmail/email/<email_id>', methods=['GET'])
    def get_email_details(email_id):
        """Get full details of a specific email"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            # Get Gmail service
            service, error = get_gmail_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Fetch full message
            message = service.users().messages().get(
                userId='me',
                id=email_id,
                format='full'
            ).execute()

            # Extract headers
            headers = {}
            for header in message.get('payload', {}).get('headers', []):
                headers[header['name']] = header['value']

            # Extract body
            body = ''
            if 'parts' in message['payload']:
                for part in message['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        if 'data' in part['body']:
                            body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                            break
            elif 'body' in message['payload'] and 'data' in message['payload']['body']:
                body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')

            return jsonify({
                'success': True,
                'email': {
                    'id': message['id'],
                    'threadId': message['threadId'],
                    'from': headers.get('From', ''),
                    'to': headers.get('To', ''),
                    'subject': headers.get('Subject', ''),
                    'date': headers.get('Date', ''),
                    'body': body,
                    'snippet': message.get('snippet', '')
                }
            })

        except HttpError as error:
            print(f"❌ Gmail API error: {error}")
            return jsonify({'error': 'An internal error occurred'}), 500
        except Exception as e:
            print(f"❌ Error fetching email: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/gmail/send', methods=['POST'])
    def send_email():
        """Send an email via Gmail"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            data = request.get_json()
            to = data.get('to')
            subject = data.get('subject')
            body = data.get('body')

            if not to or not subject or not body:
                return jsonify({'error': 'Missing required fields: to, subject, body'}), 400

            # Get Gmail service
            service, error = get_gmail_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Create message
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            message.attach(MIMEText(body, 'plain'))

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            # Send message
            sent_message = service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()

            print(f"✅ Email sent: {sent_message['id']}")

            return jsonify({
                'success': True,
                'message': 'Email sent successfully',
                'messageId': sent_message['id']
            })

        except HttpError as error:
            print(f"❌ Gmail API error: {error}")
            return jsonify({'error': 'An internal error occurred'}), 500
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/gmail/labels', methods=['GET'])
    def get_labels():
        """Get Gmail labels/folders"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            # Get Gmail service
            service, error = get_gmail_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Get labels
            results = service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])

            return jsonify({
                'success': True,
                'labels': [{
                    'id': label['id'],
                    'name': label['name'],
                    'type': label.get('type', 'user')
                } for label in labels]
            })

        except HttpError as error:
            print(f"❌ Gmail API error: {error}")
            return jsonify({'error': 'An internal error occurred'}), 500
        except Exception as e:
            print(f"❌ Error fetching labels: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500
