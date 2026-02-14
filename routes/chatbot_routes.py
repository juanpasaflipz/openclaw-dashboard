"""
Chatbot Routes — conversation management and direct-LLM chat with tool calling.
"""
from flask import jsonify, request, session
from datetime import datetime
from models import db, ChatConversation, ChatMessage, UserModelConfig, ConfigFile
from llm_service import LLMService
from context_manager import trim_messages
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


def run_llm_pipeline(user_id, conversation_id, message_text, feature_slot='chatbot', system_prompt=None):
    """Shared LLM pipeline with tool-calling loop.
    Used by chatbot send_message() and channel webhooks.
    Returns: {'success': bool, 'messages': [...], 'last_assistant_content': str, 'error': str}
    """
    config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot=feature_slot).first()
    if not config:
        # Fall back to any available model config for this user
        config = UserModelConfig.query.filter_by(user_id=user_id).first()
    if not config:
        return {'success': False, 'error': f'No model configured. Please configure a model in Model Config.'}

    # --- Observability: start run ---
    import time as _time
    run_id = None
    run_tokens_in = 0
    run_tokens_out = 0
    run_cost = 0
    run_latency = 0
    run_tool_calls = 0
    try:
        from observability_service import start_run, finish_run, emit_event, calculate_cost
        run_id = start_run(user_id, model=config.model, metadata={'feature_slot': feature_slot, 'conversation_id': conversation_id})

        # Set the LLM obs hook for this request
        def _llm_obs_hook(provider, model, usage, latency_ms, success, error_msg):
            nonlocal run_tokens_in, run_tokens_out, run_cost, run_latency
            tin = (usage or {}).get('prompt_tokens', 0) or 0
            tout = (usage or {}).get('completion_tokens', 0) or 0
            cost = calculate_cost(provider, model, tin, tout)
            run_tokens_in += tin
            run_tokens_out += tout
            run_cost += cost
            run_latency += latency_ms
            emit_event(
                user_id=user_id, event_type='llm_call',
                status='success' if success else 'error',
                run_id=run_id, model=model,
                tokens_in=tin, tokens_out=tout, cost_usd=cost,
                latency_ms=latency_ms,
                payload={'provider': provider, 'error': error_msg} if error_msg else {'provider': provider},
            )

        from llm_service import LLMService
        LLMService._obs_hook = _llm_obs_hook
    except Exception:
        pass  # Observability must never break the pipeline

    # Save user message
    user_msg = ChatMessage(
        conversation_id=conversation_id,
        role='user',
        content=message_text,
    )
    db.session.add(user_msg)
    db.session.flush()

    # Get tools for this user
    from agent_tools import get_tools_for_user, execute_tool, get_tools_system_prompt

    tools = get_tools_for_user(user_id)
    tools_system_prompt = get_tools_system_prompt(user_id)

    # --- Soul Persistence: inject ConfigFile entries into system prompt ---
    soul_parts = []
    for filename, label in [('IDENTITY.md', 'IDENTITY'), ('SOUL.md', 'SOUL (Persistent Memory)'), ('USER.md', 'USER PROFILE')]:
        cfg = ConfigFile.query.filter_by(user_id=user_id, filename=filename).first()
        if cfg and cfg.content and cfg.content.strip():
            soul_parts.append(f'=== {label} ===\n{cfg.content.strip()}')
    soul_block = '\n\n'.join(soul_parts) if soul_parts else ''

    # --- Semantic Memory: inject relevant memories into prompt ---
    memory_block = ''
    try:
        from memory_service import search_memories
        memories = search_memories(user_id, message_text, limit=5)
        if memories:
            memory_lines = [f'- {m["content"]}' for m in memories]
            memory_block = 'Relevant memories from past conversations:\n' + '\n'.join(memory_lines)
    except Exception:
        pass  # Memory must never break the pipeline

    # Build system prompt with soul context + memory + tools context
    base_system = system_prompt or ''
    if soul_block:
        base_system = (soul_block + '\n\n' + base_system).strip()
    if memory_block:
        base_system = (base_system + '\n\n' + memory_block).strip()
    full_system = (base_system + '\n\n' + tools_system_prompt).strip() if tools_system_prompt else base_system

    # Build message history
    messages, history = _build_history_messages(conversation_id, config.provider, system_prompt=full_system)

    # Context window guard: trim messages to fit within model limits
    messages = trim_messages(messages, model=config.model)

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

            for tc in tool_calls:
                # --- Observability: track tool execution ---
                _tool_t0 = _time.time()
                tool_result = execute_tool(tc['name'], user_id, tc['arguments'])
                _tool_latency = int((_time.time() - _tool_t0) * 1000)
                run_tool_calls += 1
                try:
                    _tool_ok = not (isinstance(tool_result, dict) and tool_result.get('error'))
                    emit_event(
                        user_id=user_id, event_type='tool_call',
                        status='success' if _tool_ok else 'error',
                        run_id=run_id, latency_ms=_tool_latency,
                        payload={'tool_name': tc['name'], 'tool_input_keys': list((tc.get('arguments') or {}).keys())},
                    )
                except Exception:
                    pass
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

                if config.provider == 'anthropic':
                    pass
                else:
                    messages.append({
                        'role': 'tool',
                        'tool_call_id': tc['id'],
                        'content': result_str,
                    })

            db.session.flush()

            if config.provider == 'anthropic':
                messages, _ = _build_history_messages(
                    conversation_id, config.provider, system_prompt=full_system)
            else:
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
        conv = ChatConversation.query.filter_by(conversation_id=conversation_id).first()
        if conv and conv.title == 'New Chat' and len(history) <= 1:
            conv.title = message_text[:60] + ('...' if len(message_text) > 60 else '')

        if conv:
            conv.updated_at = datetime.utcnow()
        db.session.commit()

        last_assistant_content = ''
        for m in reversed(new_messages):
            if m.get('role') == 'assistant':
                last_assistant_content = m.get('content', '')
                break

        # --- Observability: finish run (success) ---
        try:
            if run_id:
                finish_run(run_id, status='success',
                           tokens_in=run_tokens_in, tokens_out=run_tokens_out,
                           cost_usd=run_cost, latency_ms=run_latency, tool_calls=run_tool_calls)
            LLMService._obs_hook = None
        except Exception:
            pass

        return {
            'success': True,
            'messages': new_messages,
            'last_assistant_content': last_assistant_content,
            'usage': result.get('usage', {}),
        }

    except Exception as e:
        # --- Observability: finish run (error) ---
        try:
            if run_id:
                finish_run(run_id, status='error', error_message=str(e)[:300],
                           tokens_in=run_tokens_in, tokens_out=run_tokens_out,
                           cost_usd=run_cost, latency_ms=run_latency, tool_calls=run_tool_calls)
            LLMService._obs_hook = None
        except Exception:
            pass
        try:
            db.session.rollback()
        except Exception:
            pass
        # Try to preserve the user message
        try:
            db.session.add(user_msg)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return {'success': False, 'error': f'LLM error: {str(e)[:300]}'}


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

        feature_slot = data.get('feature_slot', 'chatbot')
        system_prompt = data.get('system_prompt')

        result = run_llm_pipeline(user_id, conversation_id, message_text,
                                  feature_slot=feature_slot, system_prompt=system_prompt)

        if not result['success']:
            return jsonify({'error': result['error']}), 500 if 'LLM error' in result.get('error', '') else 400

        # Backward-compatible 'message' field (last assistant msg)
        last_assistant = None
        for m in reversed(result['messages']):
            if m.get('role') == 'assistant':
                last_assistant = m
                break

        return jsonify({
            'success': True,
            'messages': result['messages'],
            'message': last_assistant or (result['messages'][-1] if result['messages'] else {}),
            'usage': result.get('usage', {}),
        })

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
