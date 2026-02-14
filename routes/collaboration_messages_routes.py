"""
API routes for the collaboration messaging system.

Messages provide asynchronous communication between agents and users.
They can be linked to a task (forming a collaboration thread) or grouped
by a free-form thread_id.
"""
from datetime import datetime
from flask import jsonify, request, session
from functools import wraps
from models import db, Agent, CollaborationTask, AgentMessage


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def register_collaboration_messages_routes(app):
    """Register collaboration message routes with the Flask app."""

    # ------------------------------------------------------------------
    # POST /api/messages  — send a message
    # ------------------------------------------------------------------
    @app.route('/api/messages', methods=['POST'])
    @require_auth
    def collab_send_message():
        try:
            user_id = session.get('user_id')
            data = request.get_json(silent=True) or {}

            content = (data.get('content') or '').strip()
            if not content:
                return jsonify({'error': 'content is required'}), 400

            role = data.get('role', 'agent')
            if role not in AgentMessage.VALID_ROLES:
                return jsonify({
                    'error': f'Invalid role. Must be one of: {", ".join(sorted(AgentMessage.VALID_ROLES))}',
                }), 400

            # Validate task_id belongs to workspace if provided
            task_id = data.get('task_id')
            if task_id:
                task = CollaborationTask.query.filter_by(
                    id=task_id, workspace_id=user_id,
                ).first()
                if not task:
                    return jsonify({'error': 'Task not found in workspace'}), 404

            # Validate from_agent_id belongs to workspace if provided
            from_agent_id = data.get('from_agent_id')
            if from_agent_id:
                agent = Agent.query.filter_by(id=from_agent_id, user_id=user_id).first()
                if not agent:
                    return jsonify({'error': 'Sender agent not found in workspace'}), 404

            # Validate to_agent_id belongs to workspace if provided
            to_agent_id = data.get('to_agent_id')
            if to_agent_id:
                agent = Agent.query.filter_by(id=to_agent_id, user_id=user_id).first()
                if not agent:
                    return jsonify({'error': 'Recipient agent not found in workspace'}), 404

            msg = AgentMessage(
                workspace_id=user_id,
                task_id=task_id,
                thread_id=data.get('thread_id'),
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                from_user_id=user_id if role == 'user' else None,
                role=role,
                content=content,
                created_at=datetime.utcnow(),
            )
            db.session.add(msg)
            db.session.commit()

            return jsonify({'success': True, 'message': msg.to_dict()}), 201

        except Exception as e:
            db.session.rollback()
            print(f"Error sending message: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    # ------------------------------------------------------------------
    # GET /api/messages  — list messages (by task_id or thread_id)
    # ------------------------------------------------------------------
    @app.route('/api/messages', methods=['GET'])
    @require_auth
    def collab_list_messages():
        try:
            user_id = session.get('user_id')
            query = AgentMessage.query.filter_by(workspace_id=user_id)

            task_id = request.args.get('task_id')
            thread_id = request.args.get('thread_id')

            if not task_id and not thread_id:
                return jsonify({
                    'error': 'Provide task_id or thread_id query parameter',
                }), 400

            if task_id:
                query = query.filter_by(task_id=task_id)
            if thread_id:
                query = query.filter_by(thread_id=thread_id)

            # Optional filters
            role = request.args.get('role')
            if role:
                query = query.filter_by(role=role)

            agent_id = request.args.get('agent_id')
            if agent_id:
                aid = int(agent_id)
                query = query.filter(
                    (AgentMessage.from_agent_id == aid)
                    | (AgentMessage.to_agent_id == aid)
                )

            messages = query.order_by(AgentMessage.created_at.asc()).limit(200).all()

            return jsonify({
                'success': True,
                'messages': [m.to_dict() for m in messages],
                'count': len(messages),
            })

        except Exception as e:
            print(f"Error listing messages: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500
