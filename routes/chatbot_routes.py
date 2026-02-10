"""
Chatbot Routes — conversation management and direct-LLM chat.
"""
from flask import jsonify, request, session
from datetime import datetime
from models import db, ChatConversation, ChatMessage, UserModelConfig
from llm_service import LLMService
import secrets


def register_chatbot_routes(app):

    @app.route('/api/chat/conversations', methods=['GET'])
    def list_conversations():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        feature = request.args.get('feature')
        agent_type = request.args.get('agent_type')

        query = ChatConversation.query.filter_by(user_id=user_id)
        if feature:
            query = query.filter_by(feature=feature)
        if agent_type:
            query = query.filter_by(agent_type=agent_type)

        convos = query.order_by(ChatConversation.updated_at.desc()).all()
        return jsonify({'conversations': [c.to_dict() for c in convos]})

    @app.route('/api/chat/conversations', methods=['POST'])
    def create_conversation():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        conv = ChatConversation(
            conversation_id=secrets.token_urlsafe(16),
            user_id=user_id,
            title=data.get('title', 'New Chat'),
            feature=data.get('feature', 'chatbot'),
            agent_type=data.get('agent_type', 'direct_llm'),
            agent_id=data.get('agent_id'),
        )
        db.session.add(conv)
        db.session.commit()
        return jsonify({'success': True, 'conversation': conv.to_dict()}), 201

    @app.route('/api/chat/conversations/<conversation_id>', methods=['DELETE'])
    def delete_conversation(conversation_id):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        conv = ChatConversation.query.filter_by(conversation_id=conversation_id, user_id=user_id).first()
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404

        db.session.delete(conv)
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/api/chat/conversations/<conversation_id>/messages', methods=['GET'])
    def get_messages(conversation_id):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        conv = ChatConversation.query.filter_by(conversation_id=conversation_id, user_id=user_id).first()
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        per_page = min(per_page, 100)

        msgs = ChatMessage.query.filter_by(conversation_id=conversation_id)\
            .order_by(ChatMessage.created_at.asc())\
            .paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'messages': [m.to_dict() for m in msgs.items],
            'total': msgs.total,
            'page': page,
            'pages': msgs.pages,
        })

    @app.route('/api/chat/send', methods=['POST'])
    def send_message():
        """Send a message in direct LLM mode — Flask calls LLMService and returns response."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        conversation_id = data.get('conversation_id')
        message_text = (data.get('message') or '').strip()

        if not conversation_id or not message_text:
            return jsonify({'error': 'conversation_id and message are required'}), 400

        conv = ChatConversation.query.filter_by(conversation_id=conversation_id, user_id=user_id).first()
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404

        # Load user's model config for the chatbot feature
        feature_slot = data.get('feature_slot', 'chatbot')
        config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot=feature_slot).first()
        if not config:
            return jsonify({'error': f'No model configured for {feature_slot}. Please configure a model first.'}), 400

        # Save user message
        user_msg = ChatMessage(
            conversation_id=conversation_id,
            role='user',
            content=message_text,
        )
        db.session.add(user_msg)
        db.session.flush()

        # Build message history for LLM
        history = ChatMessage.query.filter_by(conversation_id=conversation_id)\
            .order_by(ChatMessage.created_at.asc()).all()

        messages = []
        system_prompt = data.get('system_prompt')
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})

        for msg in history:
            if msg.role in ('user', 'assistant', 'system'):
                messages.append({'role': msg.role, 'content': msg.content})

        try:
            result = LLMService.call(
                provider=config.provider,
                model=config.model,
                api_key=config.api_key,
                messages=messages,
                endpoint_url=config.endpoint_url,
                extra_config=config.extra_config,
            )

            # Save assistant message
            assistant_msg = ChatMessage(
                conversation_id=conversation_id,
                role='assistant',
                content=result['content'],
                metadata_json={
                    'model': result.get('model'),
                    'usage': result.get('usage'),
                    'provider': config.provider,
                },
            )
            db.session.add(assistant_msg)

            # Auto-title on first exchange
            if conv.title == 'New Chat' and len(history) <= 1:
                conv.title = message_text[:60] + ('...' if len(message_text) > 60 else '')

            conv.updated_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'success': True,
                'message': assistant_msg.to_dict(),
                'usage': result.get('usage', {}),
            })

        except Exception as e:
            db.session.rollback()
            # Still save the user message
            db.session.add(user_msg)
            db.session.commit()
            return jsonify({'error': f'LLM error: {str(e)[:300]}'}), 500

    @app.route('/api/chat/messages/save', methods=['POST'])
    def save_messages():
        """Save messages from WebSocket agents (Nautilus/external) for persistence."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        conversation_id = data.get('conversation_id')
        messages = data.get('messages', [])

        if not conversation_id:
            return jsonify({'error': 'conversation_id is required'}), 400

        conv = ChatConversation.query.filter_by(conversation_id=conversation_id, user_id=user_id).first()
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404

        saved = []
        for msg_data in messages:
            msg = ChatMessage(
                conversation_id=conversation_id,
                role=msg_data.get('role', 'assistant'),
                content=msg_data.get('content', ''),
                metadata_json=msg_data.get('metadata'),
            )
            db.session.add(msg)
            saved.append(msg)

        conv.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'success': True, 'saved_count': len(saved)})

    @app.route('/api/chat/conversations/<conversation_id>/title', methods=['PUT'])
    def update_conversation_title(conversation_id):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        conv = ChatConversation.query.filter_by(conversation_id=conversation_id, user_id=user_id).first()
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404

        data = request.get_json() or {}
        conv.title = data.get('title', conv.title)
        db.session.commit()
        return jsonify({'success': True, 'conversation': conv.to_dict()})
