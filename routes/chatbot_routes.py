"""
Chatbot Routes — conversation management and direct-LLM chat with tool calling.
"""
from flask import jsonify, request, session
from datetime import datetime
from models import db, ChatConversation, ChatMessage, UserModelConfig
from llm_service import LLMService
import secrets
import json


MAX_TOOL_ITERATIONS = 5


def _build_history_messages(conversation_id, provider, system_prompt=None):
    """
    Load DB messages and reconstruct provider-specific format.
    Tool messages and assistant tool_calls are converted back to the
    format each provider expects.
    """
    history = ChatMessage.query.filter_by(conversation_id=conversation_id)\
        .order_by(ChatMessage.created_at.asc()).all()

    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})

    is_anthropic = (provider == 'anthropic')

    i = 0
    while i < len(history):
        msg = history[i]
        meta = msg.metadata_json or {}

        if msg.role == 'assistant' and meta.get('tool_calls'):
            # Assistant message that requested tool calls
            tc_list = meta['tool_calls']

            if is_anthropic:
                # Anthropic: content blocks with text + tool_use
                content_blocks = []
                if msg.content:
                    content_blocks.append({'type': 'text', 'text': msg.content})
                for tc in tc_list:
                    content_blocks.append({
                        'type': 'tool_use',
                        'id': tc.get('id', ''),
                        'name': tc['name'],
                        'input': tc.get('arguments', {}),
                    })
                messages.append({'role': 'assistant', 'content': content_blocks})

                # Collect subsequent tool result messages into one user message
                tool_results = []
                j = i + 1
                while j < len(history) and history[j].role == 'tool':
                    t = history[j]
                    t_meta = t.metadata_json or {}
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': t_meta.get('tool_call_id', ''),
                        'content': t.content,
                    })
                    j += 1
                if tool_results:
                    messages.append({'role': 'user', 'content': tool_results})
                i = j
                continue
            else:
                # OpenAI-compatible: assistant with tool_calls + separate tool messages
                openai_tool_calls = []
                for tc in tc_list:
                    openai_tool_calls.append({
                        'id': tc.get('id', ''),
                        'type': 'function',
                        'function': {
                            'name': tc['name'],
                            'arguments': json.dumps(tc.get('arguments', {})),
                        },
                    })
                assistant_msg = {'role': 'assistant', 'content': msg.content or ''}
                assistant_msg['tool_calls'] = openai_tool_calls
                messages.append(assistant_msg)

                # Add subsequent tool result messages
                j = i + 1
                while j < len(history) and history[j].role == 'tool':
                    t = history[j]
                    t_meta = t.metadata_json or {}
                    messages.append({
                        'role': 'tool',
                        'tool_call_id': t_meta.get('tool_call_id', ''),
                        'content': t.content,
                    })
                    j += 1
                i = j
                continue

        elif msg.role == 'tool':
            # Orphan tool message (shouldn't happen normally) — skip
            i += 1
            continue
        elif msg.role in ('user', 'assistant', 'system'):
            messages.append({'role': msg.role, 'content': msg.content})

        i += 1

    return messages, history


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
        """Send a message in direct LLM mode — with tool-calling loop."""
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

        # Get tools for this user (lazy import to avoid circular deps)
        from agent_tools import get_tools_for_user, execute_tool, get_tools_system_prompt

        tools = get_tools_for_user(user_id)
        tools_system_prompt = get_tools_system_prompt(user_id)

        # Build system prompt with tools context
        base_system = data.get('system_prompt') or ''
        full_system = (base_system + '\n\n' + tools_system_prompt).strip() if tools_system_prompt else base_system

        # Build message history
        messages, history = _build_history_messages(conversation_id, config.provider, system_prompt=full_system)

        # Track new messages to return to frontend
        new_messages = []

        try:
            for iteration in range(MAX_TOOL_ITERATIONS):
                result = LLMService.call(
                    provider=config.provider,
                    model=config.model,
                    api_key=config.api_key,
                    messages=messages,
                    endpoint_url=config.endpoint_url,
                    extra_config=config.extra_config,
                    tools=tools if tools else None,
                )

                tool_calls = result.get('tool_calls')

                if not tool_calls:
                    # Final text response — save and return
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
                    new_messages.append(assistant_msg.to_dict())
                    break

                # --- Tool calls: execute and loop ---

                # Save assistant message with tool_calls metadata
                tc_meta = [{'id': tc['id'], 'name': tc['name'], 'arguments': tc['arguments']}
                           for tc in tool_calls]
                assistant_msg = ChatMessage(
                    conversation_id=conversation_id,
                    role='assistant',
                    content=result.get('content') or '',
                    metadata_json={
                        'tool_calls': tc_meta,
                        'model': result.get('model'),
                        'usage': result.get('usage'),
                        'provider': config.provider,
                    },
                )
                db.session.add(assistant_msg)
                db.session.flush()

                # Execute each tool and save results
                for tc in tool_calls:
                    tool_result = execute_tool(tc['name'], user_id, tc['arguments'])
                    result_str = json.dumps(tool_result, default=str)

                    tool_msg = ChatMessage(
                        conversation_id=conversation_id,
                        role='tool',
                        content=result_str,
                        metadata_json={
                            'tool_name': tc['name'],
                            'tool_input': tc['arguments'],
                            'tool_call_id': tc['id'],
                        },
                    )
                    db.session.add(tool_msg)
                    new_messages.append(tool_msg.to_dict())

                    # Append to messages for next LLM call
                    if config.provider == 'anthropic':
                        # Will be bundled in the history reconstruction on next iteration
                        pass
                    else:
                        messages.append({
                            'role': 'tool',
                            'tool_call_id': tc['id'],
                            'content': result_str,
                        })

                db.session.flush()

                # For Anthropic, rebuild messages from DB to get proper format
                if config.provider == 'anthropic':
                    messages, _ = _build_history_messages(
                        conversation_id, config.provider, system_prompt=full_system)
                else:
                    # Append assistant message with tool_calls for OpenAI-compat
                    # Insert before the tool results we just added
                    insert_idx = len(messages) - len(tool_calls)
                    openai_tc = [{
                        'id': tc['id'],
                        'type': 'function',
                        'function': {
                            'name': tc['name'],
                            'arguments': json.dumps(tc['arguments']),
                        },
                    } for tc in tool_calls]
                    assistant_api_msg = {
                        'role': 'assistant',
                        'content': result.get('content') or '',
                        'tool_calls': openai_tc,
                    }
                    messages.insert(insert_idx, assistant_api_msg)

            # Auto-title on first exchange
            if conv.title == 'New Chat' and len(history) <= 1:
                conv.title = message_text[:60] + ('...' if len(message_text) > 60 else '')

            conv.updated_at = datetime.utcnow()
            db.session.commit()

            # Return all new messages (tool cards + final response)
            # Also include backward-compatible 'message' field (last assistant msg)
            last_assistant = None
            for m in reversed(new_messages):
                if m.get('role') == 'assistant':
                    last_assistant = m
                    break

            return jsonify({
                'success': True,
                'messages': new_messages,
                'message': last_assistant or (new_messages[-1] if new_messages else {}),
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
        msgs_data = data.get('messages', [])

        if not conversation_id:
            return jsonify({'error': 'conversation_id is required'}), 400

        conv = ChatConversation.query.filter_by(conversation_id=conversation_id, user_id=user_id).first()
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404

        saved = []
        for msg_data in msgs_data:
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
