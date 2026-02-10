"""
AI Agent Actions for Gmail
Routes for AI-powered email operations with approval queue
"""
from flask import Blueprint, request, jsonify, session
from models import db, User, Agent, AgentAction, Superpower
from gmail_routes import get_gmail_service
from calendar_routes import get_calendar_service
from drive_routes import get_drive_service
from datetime import datetime
import json
import os


def get_anthropic_client():
    """Get Anthropic client (lazy initialization)"""
    try:
        import anthropic
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return None, "ANTHROPIC_API_KEY not configured"

        # Initialize client with minimal config to avoid proxy issues
        try:
            client = anthropic.Anthropic(api_key=api_key)
        except TypeError as te:
            # Handle version-specific initialization issues
            client = anthropic.Client(api_key=api_key)

        return client, None
    except ImportError:
        return None, "anthropic package not installed"
    except Exception as e:
        return None, f"Anthropic client error: {str(e)}"


def register_agent_actions_routes(app):
    """Register agent action routes with the Flask app"""

    @app.route('/api/agent-actions/analyze-inbox', methods=['POST'])
    def analyze_inbox():
        """AI analyzes recent emails and provides insights"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']
        user = User.query.get(user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        try:
            # Get agent (optional - used for tracking who made the request)
            agent_id = request.json.get('agent_id')
            agent = None
            if agent_id:
                agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            else:
                agent = user.get_primary_agent()

            # Get Gmail service
            service, error = get_gmail_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Fetch recent emails
            results = service.users().messages().list(
                userId='me',
                maxResults=10,
                labelIds=['INBOX']
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                return jsonify({
                    'success': True,
                    'analysis': 'Your inbox is empty! 📬',
                    'insights': [],
                    'suggested_actions': []
                })

            # Fetch email details
            emails = []
            for msg in messages[:5]:  # Analyze top 5
                email_data = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()

                headers = {h['name']: h['value'] for h in email_data['payload']['headers']}
                emails.append({
                    'id': email_data['id'],
                    'from': headers.get('From', ''),
                    'subject': headers.get('Subject', ''),
                    'snippet': email_data.get('snippet', '')
                })

            # Use Claude to analyze emails
            analysis_prompt = f"""Analyze these recent emails and provide insights:

{json.dumps(emails, indent=2)}

Provide:
1. A brief summary of what's in the inbox
2. Any urgent items that need attention
3. Suggested actions (reply needed, can archive, etc.)

Format your response as JSON with keys: summary, urgent_items (array), suggested_actions (array)"""

            # Get Anthropic client
            client, error = get_anthropic_client()
            if error:
                return jsonify({'error': f'AI not configured: {error}'}), 500

            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": analysis_prompt
                }]
            )

            # Parse AI response
            ai_response = response.content[0].text

            # Try to extract JSON from response
            try:
                # Look for JSON in the response
                import re
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                else:
                    # Fallback: use the text response
                    analysis = {
                        'summary': ai_response,
                        'urgent_items': [],
                        'suggested_actions': []
                    }
            except:
                analysis = {
                    'summary': ai_response,
                    'urgent_items': [],
                    'suggested_actions': []
                }

            return jsonify({
                'success': True,
                'analysis': analysis.get('summary', ai_response),
                'urgent_items': analysis.get('urgent_items', []),
                'suggested_actions': analysis.get('suggested_actions', []),
                'emails_analyzed': len(emails)
            })

        except Exception as e:
            print(f"Error analyzing inbox: {str(e)}")
            return jsonify({'error': str(e)}), 500


    @app.route('/api/agent-actions/draft-reply', methods=['POST'])
    def draft_reply():
        """AI drafts a reply to an email (queued for approval)"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']
        user = User.query.get(user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        try:
            data = request.json
            email_id = data.get('email_id')
            context = data.get('context', '')  # Optional context from user

            if not email_id:
                return jsonify({'error': 'email_id required'}), 400

            # Get agent (optional)
            agent = user.get_primary_agent()

            # Get Gmail service
            service, error = get_gmail_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Fetch original email
            email_data = service.users().messages().get(
                userId='me',
                id=email_id,
                format='full'
            ).execute()

            headers = {h['name']: h['value'] for h in email_data['payload']['headers']}

            # Use Claude to draft reply
            draft_prompt = f"""Draft a professional reply to this email:

From: {headers.get('From', '')}
Subject: {headers.get('Subject', '')}
Content: {email_data.get('snippet', '')}

{f'Additional context: {context}' if context else ''}

Write a clear, professional reply. Be concise and helpful."""

            # Get Anthropic client
            client, error = get_anthropic_client()
            if error:
                return jsonify({'error': f'AI not configured: {error}'}), 500

            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": draft_prompt
                }]
            )

            draft_text = response.content[0].text

            # Create action for approval
            action = AgentAction(
                user_id=user_id,
                agent_id=agent.id if agent else None,
                action_type='send_email',
                service_type='gmail',
                status='pending',
                action_data=json.dumps({
                    'to': headers.get('From', ''),
                    'subject': f"Re: {headers.get('Subject', '')}",
                    'body': draft_text,
                    'in_reply_to': email_id
                }),
                ai_reasoning=f"Drafted reply to email from {headers.get('From', '')}",
                ai_confidence=0.85
            )

            db.session.add(action)
            db.session.commit()

            return jsonify({
                'success': True,
                'action_id': action.id,
                'draft': draft_text,
                'message': 'Draft created! Review and approve to send.'
            })

        except Exception as e:
            print(f"Error drafting reply: {str(e)}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500


    @app.route('/api/agent-actions/pending', methods=['GET'])
    def get_pending_actions():
        """Get all pending actions for user approval"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            actions = AgentAction.query.filter_by(
                user_id=user_id,
                status='pending'
            ).order_by(AgentAction.created_at.desc()).all()

            return jsonify({
                'success': True,
                'actions': [action.to_dict() for action in actions],
                'count': len(actions)
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500


    @app.route('/api/agent-actions/<int:action_id>/approve', methods=['POST'])
    def approve_action(action_id):
        """Approve and execute an agent action"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            action = AgentAction.query.filter_by(
                id=action_id,
                user_id=user_id,
                status='pending'
            ).first()

            if not action:
                return jsonify({'error': 'Action not found or already processed'}), 404

            # Mark as approved
            action.status = 'approved'
            action.approved_at = datetime.utcnow()

            # Execute the action
            if action.action_type == 'send_email' and action.service_type == 'gmail':
                # Get Gmail service
                service, error = get_gmail_service(user_id)
                if error:
                    action.status = 'failed'
                    action.error_message = error
                    db.session.commit()
                    return jsonify({'error': error}), 400

                # Parse action data
                email_data = json.loads(action.action_data)

                # Create email
                from email.mime.text import MIMEText
                import base64

                message = MIMEText(email_data['body'])
                message['To'] = email_data['to']
                message['Subject'] = email_data['subject']

                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

                # Send email
                sent_message = service.users().messages().send(
                    userId='me',
                    body={'raw': raw}
                ).execute()

                # Mark as executed
                action.status = 'executed'
                action.executed_at = datetime.utcnow()
                action.result_data = json.dumps({'message_id': sent_message['id']})

                # Update superpower usage
                superpower = Superpower.query.filter_by(
                    user_id=user_id,
                    service_type='gmail'
                ).first()
                if superpower:
                    superpower.usage_count += 1
                    superpower.last_used = datetime.utcnow()

            elif action.action_type == 'place_order' and action.service_type == 'binance':
                from binance_service import place_order, is_trading_enabled

                # Verify trading is still enabled
                if not is_trading_enabled(user_id):
                    action.status = 'failed'
                    action.error_message = 'Trading is not enabled'
                    db.session.commit()
                    return jsonify({'error': 'Trading is not enabled. Enable it in Binance settings.'}), 400

                # Parse action data
                trade_data = json.loads(action.action_data)

                # Execute the trade
                result, error = place_order(
                    user_id=user_id,
                    symbol=trade_data['symbol'],
                    side=trade_data['side'],
                    order_type=trade_data['order_type'],
                    amount=trade_data['amount'],
                    price=trade_data.get('price'),
                )

                if error:
                    action.status = 'failed'
                    action.error_message = error
                    db.session.commit()
                    return jsonify({'error': error}), 400

                # Mark as executed
                action.status = 'executed'
                action.executed_at = datetime.utcnow()
                action.result_data = json.dumps(result)

                # Update superpower usage
                superpower = Superpower.query.filter_by(
                    user_id=user_id,
                    service_type='binance'
                ).first()
                if superpower:
                    superpower.usage_count = (superpower.usage_count or 0) + 1
                    superpower.last_used = datetime.utcnow()

            elif action.action_type == 'create_event' and action.service_type == 'calendar':
                service, error = get_calendar_service(user_id)
                if error:
                    action.status = 'failed'
                    action.error_message = error
                    db.session.commit()
                    return jsonify({'error': error}), 400

                event_data = json.loads(action.action_data)

                event_body = {
                    'summary': event_data.get('summary', 'Untitled Event'),
                    'start': event_data.get('start', {}),
                    'end': event_data.get('end', {}),
                }
                if event_data.get('description'):
                    event_body['description'] = event_data['description']
                if event_data.get('location'):
                    event_body['location'] = event_data['location']
                if event_data.get('attendees'):
                    event_body['attendees'] = [{'email': e} for e in event_data['attendees']]

                created_event = service.events().insert(
                    calendarId='primary',
                    body=event_body,
                    sendUpdates='all' if event_data.get('attendees') else 'none'
                ).execute()

                action.status = 'executed'
                action.executed_at = datetime.utcnow()
                action.result_data = json.dumps({
                    'event_id': created_event['id'],
                    'html_link': created_event.get('htmlLink', '')
                })

                superpower = Superpower.query.filter_by(
                    user_id=user_id, service_type='calendar'
                ).first()
                if superpower:
                    superpower.usage_count = (superpower.usage_count or 0) + 1
                    superpower.last_used = datetime.utcnow()

            elif action.action_type == 'update_event' and action.service_type == 'calendar':
                service, error = get_calendar_service(user_id)
                if error:
                    action.status = 'failed'
                    action.error_message = error
                    db.session.commit()
                    return jsonify({'error': error}), 400

                event_data = json.loads(action.action_data)
                event_id = event_data.get('event_id')

                if not event_id:
                    action.status = 'failed'
                    action.error_message = 'event_id required'
                    db.session.commit()
                    return jsonify({'error': 'event_id required'}), 400

                update_body = {}
                if event_data.get('summary'):
                    update_body['summary'] = event_data['summary']
                if event_data.get('description'):
                    update_body['description'] = event_data['description']
                if event_data.get('start'):
                    update_body['start'] = event_data['start']
                if event_data.get('end'):
                    update_body['end'] = event_data['end']
                if event_data.get('location'):
                    update_body['location'] = event_data['location']

                updated_event = service.events().patch(
                    calendarId='primary',
                    eventId=event_id,
                    body=update_body
                ).execute()

                action.status = 'executed'
                action.executed_at = datetime.utcnow()
                action.result_data = json.dumps({
                    'event_id': updated_event['id'],
                    'html_link': updated_event.get('htmlLink', '')
                })

                superpower = Superpower.query.filter_by(
                    user_id=user_id, service_type='calendar'
                ).first()
                if superpower:
                    superpower.usage_count = (superpower.usage_count or 0) + 1
                    superpower.last_used = datetime.utcnow()

            elif action.action_type == 'delete_event' and action.service_type == 'calendar':
                service, error = get_calendar_service(user_id)
                if error:
                    action.status = 'failed'
                    action.error_message = error
                    db.session.commit()
                    return jsonify({'error': error}), 400

                event_data = json.loads(action.action_data)
                event_id = event_data.get('event_id')

                if not event_id:
                    action.status = 'failed'
                    action.error_message = 'event_id required'
                    db.session.commit()
                    return jsonify({'error': 'event_id required'}), 400

                service.events().delete(
                    calendarId='primary',
                    eventId=event_id
                ).execute()

                action.status = 'executed'
                action.executed_at = datetime.utcnow()
                action.result_data = json.dumps({'deleted_event_id': event_id})

                superpower = Superpower.query.filter_by(
                    user_id=user_id, service_type='calendar'
                ).first()
                if superpower:
                    superpower.usage_count = (superpower.usage_count or 0) + 1
                    superpower.last_used = datetime.utcnow()

            elif action.action_type == 'create_folder' and action.service_type == 'drive':
                service, error = get_drive_service(user_id)
                if error:
                    action.status = 'failed'
                    action.error_message = error
                    db.session.commit()
                    return jsonify({'error': error}), 400

                folder_data = json.loads(action.action_data)

                file_metadata = {
                    'name': folder_data.get('name', 'Untitled Folder'),
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                if folder_data.get('parent_id'):
                    file_metadata['parents'] = [folder_data['parent_id']]

                created_folder = service.files().create(
                    body=file_metadata,
                    fields='id, name, webViewLink'
                ).execute()

                action.status = 'executed'
                action.executed_at = datetime.utcnow()
                action.result_data = json.dumps({
                    'folder_id': created_folder['id'],
                    'name': created_folder.get('name', ''),
                    'web_link': created_folder.get('webViewLink', '')
                })

                superpower = Superpower.query.filter_by(
                    user_id=user_id, service_type='drive'
                ).first()
                if superpower:
                    superpower.usage_count = (superpower.usage_count or 0) + 1
                    superpower.last_used = datetime.utcnow()

            elif action.action_type == 'upload_file' and action.service_type == 'drive':
                service, error = get_drive_service(user_id)
                if error:
                    action.status = 'failed'
                    action.error_message = error
                    db.session.commit()
                    return jsonify({'error': error}), 400

                from googleapiclient.http import MediaInMemoryUpload

                file_data = json.loads(action.action_data)

                file_metadata = {
                    'name': file_data.get('name', 'untitled.txt'),
                }
                if file_data.get('parent_id'):
                    file_metadata['parents'] = [file_data['parent_id']]

                content = file_data.get('content', '')
                mime_type = file_data.get('mime_type', 'text/plain')
                media = MediaInMemoryUpload(
                    content.encode('utf-8'),
                    mimetype=mime_type,
                    resumable=False
                )

                created_file = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name, webViewLink'
                ).execute()

                action.status = 'executed'
                action.executed_at = datetime.utcnow()
                action.result_data = json.dumps({
                    'file_id': created_file['id'],
                    'name': created_file.get('name', ''),
                    'web_link': created_file.get('webViewLink', '')
                })

                superpower = Superpower.query.filter_by(
                    user_id=user_id, service_type='drive'
                ).first()
                if superpower:
                    superpower.usage_count = (superpower.usage_count or 0) + 1
                    superpower.last_used = datetime.utcnow()

            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Action executed successfully!',
                'action': action.to_dict()
            })

        except Exception as e:
            print(f"Error approving action: {str(e)}")
            action.status = 'failed'
            action.error_message = str(e)
            db.session.commit()
            return jsonify({'error': str(e)}), 500


    @app.route('/api/agent-actions/<int:action_id>/reject', methods=['POST'])
    def reject_action(action_id):
        """Reject an agent action"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            action = AgentAction.query.filter_by(
                id=action_id,
                user_id=user_id,
                status='pending'
            ).first()

            if not action:
                return jsonify({'error': 'Action not found or already processed'}), 404

            action.status = 'rejected'
            action.approved_at = datetime.utcnow()

            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Action rejected'
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
