"""
AI Agent Actions for Gmail
Routes for AI-powered email operations with approval queue
"""
from flask import Blueprint, request, jsonify, session
from models import db, User, Agent, AgentAction, Superpower
from .gmail_routes import get_gmail_service
from datetime import datetime
import json
import os

from core.tasks import approve_and_execute, get_pending_actions, reject_action, create_action


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
            return jsonify({'error': 'An internal error occurred'}), 500


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

            # Create action for approval via domain service
            action = create_action(
                user_id=user_id,
                agent_id=agent.id if agent else None,
                action_type='send_email',
                service_type='gmail',
                action_data={
                    'to': headers.get('From', ''),
                    'subject': f"Re: {headers.get('Subject', '')}",
                    'body': draft_text,
                    'in_reply_to': email_id,
                },
                ai_reasoning=f"Drafted reply to email from {headers.get('From', '')}",
                ai_confidence=0.85,
            )

            return jsonify({
                'success': True,
                'action_id': action.id,
                'draft': draft_text,
                'message': 'Draft created! Review and approve to send.'
            })

        except Exception as e:
            print(f"Error drafting reply: {str(e)}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500


    @app.route('/api/agent-actions/pending', methods=['GET'])
    def get_pending_actions_route():
        """Get all pending actions for user approval"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            actions = get_pending_actions(user_id)
            return jsonify({
                'success': True,
                'actions': actions,
                'count': len(actions),
            })
        except Exception as e:
            print(f"Error getting pending actions: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500


    @app.route('/api/agent-actions/<int:action_id>/approve', methods=['POST'])
    def approve_action(action_id):
        """Approve and execute an agent action"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            result, error, status_code = approve_and_execute(action_id, user_id)

            if error:
                return jsonify({'error': error}), status_code

            return jsonify({
                'success': True,
                'message': 'Action executed successfully!',
                'action': result,
            })

        except Exception as e:
            print(f"Error approving action: {str(e)}")
            return jsonify({'error': 'An internal error occurred'}), 500


    @app.route('/api/agent-actions/<int:action_id>/reject', methods=['POST'])
    def reject_action_route(action_id):
        """Reject an agent action"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            result, error = reject_action(action_id, user_id)

            if error:
                return jsonify({'error': error}), 404

            return jsonify({
                'success': True,
                'message': result['message'],
            })

        except Exception as e:
            db.session.rollback()
            print(f"Error rejecting action: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500
