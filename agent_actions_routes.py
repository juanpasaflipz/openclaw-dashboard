"""
AI Agent Actions for Gmail
Routes for AI-powered email operations with approval queue
"""
from flask import Blueprint, request, jsonify, session
from models import db, User, Agent, AgentAction, Superpower
from gmail_routes import get_gmail_service
from datetime import datetime
import json
import os
import anthropic

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))


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
            # Get agent (use primary or specified)
            agent_id = request.json.get('agent_id')
            if agent_id:
                agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            else:
                agent = user.get_primary_agent()

            if not agent:
                return jsonify({'error': 'No agent found'}), 404

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

            # Get agent
            agent = user.get_primary_agent()
            if not agent:
                return jsonify({'error': 'No agent found'}), 404

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
                agent_id=agent.id,
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
