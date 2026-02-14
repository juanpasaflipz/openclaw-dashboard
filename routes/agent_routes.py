"""
API routes for unified agent management (direct LLM + websocket + HTTP agents).
"""
from flask import jsonify, request, session
from models import db, User, Agent
from datetime import datetime
from functools import wraps
import requests as http_requests


def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def register_agent_routes(app):
    """Register agent management routes with the Flask app"""

    @app.route('/api/agents', methods=['GET'])
    @require_auth
    def list_agents():
        """List agents for the current user with optional type/featured filtering"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            if not user:
                return jsonify({'error': 'User not found'}), 404

            query = Agent.query.filter_by(user_id=user_id, is_active=True)

            # Filter by type (comma-separated)
            type_filter = request.args.get('type')
            if type_filter:
                types = [t.strip() for t in type_filter.split(',') if t.strip()]
                if types:
                    query = query.filter(Agent.agent_type.in_(types))

            # Filter by featured
            featured = request.args.get('featured')
            if featured and featured.lower() == 'true':
                query = query.filter_by(is_featured=True)

            agents = query.order_by(
                Agent.is_featured.desc(),
                Agent.is_default.desc(),
                Agent.created_at.desc()
            ).all()

            # Subscription limits only count 'direct' agents
            direct_count = Agent.query.filter_by(user_id=user_id, agent_type='direct').count()
            max_agents = user.get_max_agents()

            return jsonify({
                'success': True,
                'agents': [agent.to_dict() for agent in agents],
                'count': len(agents),
                'max_agents': max_agents,
                'can_create_more': direct_count < max_agents
            })

        except Exception as e:
            print(f"Error listing agents: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/<int:agent_id>', methods=['GET'])
    @require_auth
    def get_agent(agent_id):
        """Get a specific agent with full configuration"""
        try:
            user_id = session.get('user_id')
            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            # Return full agent data including configs
            agent_data = agent.to_dict()
            agent_data['llm_config'] = agent.llm_config or {}
            agent_data['identity_config'] = agent.identity_config or {}
            agent_data['moltbook_config'] = agent.moltbook_config or {}

            return jsonify({
                'success': True,
                'agent': agent_data
            })

        except Exception as e:
            print(f"Error getting agent: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents', methods=['POST'])
    @require_auth
    def create_agent():
        """Create a new agent (any type)"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            if not user:
                return jsonify({'error': 'User not found'}), 404

            data = request.get_json() or {}
            agent_type = data.get('agent_type', 'direct')

            # Subscription limits only apply to 'direct' agents
            if agent_type == 'direct':
                current_agent_count = Agent.query.filter_by(user_id=user_id, agent_type='direct').count()
                max_agents = user.get_max_agents()

                if current_agent_count >= max_agents:
                    return jsonify({
                        'error': f'Agent limit reached. Your plan allows {max_agents} agent(s). Upgrade to create more.',
                        'max_agents': max_agents,
                        'current_count': current_agent_count
                    }), 403

            # Validate required fields
            name = data.get('name', '').strip()
            if not name:
                return jsonify({'error': 'Agent name is required'}), 400

            # Create new agent
            agent = Agent(
                user_id=user_id,
                name=name,
                description=data.get('description', ''),
                avatar_emoji=data.get('avatar_emoji', '🤖'),
                avatar_url=data.get('avatar_url'),
                agent_type=agent_type,
                is_default=data.get('is_default', False),
                llm_config=data.get('llm_config', {}),
                identity_config=data.get('identity_config', {}),
                moltbook_config=data.get('moltbook_config', {}),
                # External agent fields
                connection_url=data.get('connection_url', ''),
                auth_config=data.get('auth_config', {}),
                agent_config=data.get('agent_config', {}),
                is_featured=data.get('is_featured', False),
            )

            # If this is set as default, unset other defaults
            if agent.is_default:
                Agent.query.filter_by(user_id=user_id, is_default=True).update({'is_default': False})

            db.session.add(agent)
            db.session.commit()

            print(f"New agent created: {agent.name} (type={agent_type}, user={user.email})")

            return jsonify({
                'success': True,
                'message': 'Agent created successfully',
                'agent': agent.to_dict()
            }), 201

        except Exception as e:
            print(f"Error creating agent: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/<int:agent_id>', methods=['PUT'])
    @require_auth
    def update_agent(agent_id):
        """Update an existing agent"""
        try:
            user_id = session.get('user_id')
            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            data = request.get_json() or {}

            # Update basic fields
            for field in ('name', 'description', 'avatar_emoji', 'avatar_url',
                          'agent_type', 'connection_url'):
                if field in data:
                    val = data[field].strip() if field == 'name' and isinstance(data[field], str) else data[field]
                    setattr(agent, field, val)

            if 'is_active' in data:
                agent.is_active = data['is_active']

            # Handle default agent setting
            if 'is_default' in data and data['is_default']:
                Agent.query.filter_by(user_id=user_id, is_default=True).update({'is_default': False})
                agent.is_default = True

            # Update configurations
            if 'llm_config' in data:
                agent.llm_config = data['llm_config']
            if 'identity_config' in data:
                agent.identity_config = data['identity_config']
            if 'moltbook_config' in data:
                agent.moltbook_config = data['moltbook_config']
            if 'auth_config' in data:
                agent.auth_config = data['auth_config']
            if 'agent_config' in data:
                agent.agent_config = data['agent_config']

            agent.updated_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Agent updated successfully',
                'agent': agent.to_dict()
            })

        except Exception as e:
            print(f"Error updating agent: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/<int:agent_id>', methods=['DELETE'])
    @require_auth
    def delete_agent(agent_id):
        """Delete an agent (soft-delete for websocket/http_api, hard for direct)"""
        try:
            user_id = session.get('user_id')
            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            if agent.agent_type in ('websocket', 'http_api'):
                # Soft-delete external agents
                agent.is_active = False
                db.session.commit()
            else:
                # Hard-delete direct agents (original behavior)
                agent_count = Agent.query.filter_by(user_id=user_id, agent_type='direct').count()
                if agent_count <= 1:
                    return jsonify({'error': 'Cannot delete your last agent'}), 400

                agent_name = agent.name
                was_default = agent.is_default
                db.session.delete(agent)

                if was_default:
                    next_agent = Agent.query.filter_by(user_id=user_id, agent_type='direct').first()
                    if next_agent:
                        next_agent.is_default = True

                db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Agent deleted successfully'
            })

        except Exception as e:
            print(f"Error deleting agent: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/<int:agent_id>/test', methods=['POST'])
    @require_auth
    def test_agent(agent_id):
        """Test connectivity to a websocket/http_api agent"""
        user_id = session.get('user_id')
        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        try:
            if agent.agent_type == 'http_api':
                url = agent.connection_url.rstrip('/')
                health_url = url + '/health' if not url.endswith('/health') else url
                resp = http_requests.get(health_url, timeout=5)
                if resp.ok:
                    agent.last_connected_at = datetime.utcnow()
                    agent.last_error = None
                    db.session.commit()
                    return jsonify({'success': True, 'message': 'HTTP agent is reachable.'})
                else:
                    agent.last_error = f'HTTP {resp.status_code}'
                    db.session.commit()
                    return jsonify({'success': False, 'message': f'Agent returned HTTP {resp.status_code}'})

            elif agent.agent_type == 'websocket':
                return jsonify({
                    'success': True,
                    'message': 'WebSocket agents are tested from the browser. Use the connect button.',
                    'connection_url': agent.connection_url,
                    'auth_config': agent.auth_config or {},
                })
            else:
                return jsonify({'success': True, 'message': 'Agent configuration saved.'})

        except http_requests.exceptions.ConnectionError:
            agent.last_error = 'Connection refused'
            db.session.commit()
            return jsonify({'success': False, 'message': 'Cannot connect to agent endpoint.'})
        except http_requests.exceptions.Timeout:
            agent.last_error = 'Timeout'
            db.session.commit()
            return jsonify({'success': False, 'message': 'Connection timed out.'})
        except Exception as e:
            agent.last_error = str(e)[:200]
            db.session.commit()
            return jsonify({'success': False, 'message': f'Error: {str(e)[:200]}'})

    @app.route('/api/agents/<int:agent_id>/update-status', methods=['POST'])
    @require_auth
    def update_agent_status(agent_id):
        """Update agent connection status (called by frontend after WebSocket connect/disconnect)."""
        user_id = session.get('user_id')
        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        data = request.get_json() or {}
        if data.get('connected'):
            agent.last_connected_at = datetime.utcnow()
            agent.last_error = None
        if data.get('error'):
            agent.last_error = str(data['error'])[:500]

        db.session.commit()
        return jsonify({'success': True})

    @app.route('/api/agents/seed-nautilus', methods=['POST'])
    @require_auth
    def seed_nautilus():
        """Seed Nautilus as the featured agent for the current user."""
        user_id = session.get('user_id')

        existing = Agent.query.filter_by(user_id=user_id, name='Nautilus').first()
        if existing:
            return jsonify({'success': True, 'agent': existing.to_dict(), 'already_exists': True})

        nautilus = Agent(
            user_id=user_id,
            name='Nautilus',
            description='TypeScript ReAct agent with file-ops, bash, HTTP, web-search tools and 3-tier memory. Connect via WebSocket.',
            avatar_emoji='🐙',
            agent_type='websocket',
            connection_url='ws://127.0.0.1:18789',
            auth_config={'mode': 'none'},
            agent_config={
                'capabilities': ['file-ops', 'bash', 'http', 'web-search', 'memory'],
                'persona': 'Nautilus Agent',
            },
            is_featured=True,
        )
        db.session.add(nautilus)
        db.session.commit()
        return jsonify({'success': True, 'agent': nautilus.to_dict()}), 201

    @app.route('/api/agents/<int:agent_id>/clone', methods=['POST'])
    @require_auth
    def clone_agent(agent_id):
        """Clone an existing agent"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)
            source_agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()

            if not source_agent:
                return jsonify({'error': 'Agent not found'}), 404

            # Check subscription limits
            current_agent_count = Agent.query.filter_by(user_id=user_id, agent_type='direct').count()
            max_agents = user.get_max_agents()

            if current_agent_count >= max_agents:
                return jsonify({
                    'error': f'Agent limit reached. Your plan allows {max_agents} agent(s).',
                    'max_agents': max_agents
                }), 403

            # Create clone
            clone = Agent(
                user_id=user_id,
                name=f"{source_agent.name} (Copy)",
                description=source_agent.description,
                avatar_emoji=source_agent.avatar_emoji,
                agent_type=source_agent.agent_type,
                is_default=False,
                llm_config=source_agent.llm_config.copy() if source_agent.llm_config else {},
                identity_config=source_agent.identity_config.copy() if source_agent.identity_config else {},
                moltbook_config=source_agent.moltbook_config.copy() if source_agent.moltbook_config else {},
                connection_url=source_agent.connection_url,
                auth_config=source_agent.auth_config.copy() if source_agent.auth_config else {},
                agent_config=source_agent.agent_config.copy() if source_agent.agent_config else {},
            )

            db.session.add(clone)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Agent cloned successfully',
                'agent': clone.to_dict()
            }), 201

        except Exception as e:
            print(f"Error cloning agent: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/<int:agent_id>/export', methods=['GET'])
    @require_auth
    def export_agent(agent_id):
        """Export agent configuration as JSON"""
        try:
            user_id = session.get('user_id')
            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            # Create export data (exclude sensitive info like API keys)
            export_data = {
                'name': agent.name,
                'description': agent.description,
                'avatar_emoji': agent.avatar_emoji,
                'agent_type': agent.agent_type,
                'identity_config': agent.identity_config or {},
                'llm_config': {
                    'provider': agent.llm_config.get('provider') if agent.llm_config else None,
                    'model': agent.llm_config.get('model') if agent.llm_config else None,
                    'temperature': agent.llm_config.get('temperature') if agent.llm_config else None,
                },
                'exported_at': datetime.utcnow().isoformat(),
                'green_monkey_version': '1.0.0'
            }

            return jsonify({
                'success': True,
                'export': export_data
            })

        except Exception as e:
            print(f"Error exporting agent: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/import', methods=['POST'])
    @require_auth
    def import_agent():
        """Import agent configuration from JSON or save Moltbook agent"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Check subscription limits
            current_agent_count = Agent.query.filter_by(user_id=user_id, agent_type='direct').count()
            max_agents = user.get_max_agents()

            if current_agent_count >= max_agents:
                return jsonify({
                    'error': f'Agent limit reached. Your plan allows {max_agents} agent(s).',
                    'max_agents': max_agents
                }), 403

            data = request.get_json() or {}

            # Check if this is a Moltbook agent save (has moltbook_api_key at top level)
            if 'moltbook_api_key' in data:
                # This is a Moltbook agent connection save
                name = data.get('name', '').strip()
                if not name:
                    return jsonify({'error': 'Agent name is required'}), 400

                moltbook_api_key = data.get('moltbook_api_key', '').strip()
                if not moltbook_api_key:
                    return jsonify({'error': 'Moltbook API key is required'}), 400

                # Check if agent already exists
                existing_agent = Agent.query.filter_by(user_id=user_id, name=name).first()

                if existing_agent:
                    # Update existing agent
                    existing_agent.moltbook_api_key = moltbook_api_key
                    existing_agent.description = data.get('description', existing_agent.description)
                    existing_agent.avatar_url = data.get('avatar_url', existing_agent.avatar_url)
                    existing_agent.personality = data.get('personality', existing_agent.personality)

                    if 'moltbook_config' in data:
                        import json
                        config = data['moltbook_config']
                        if isinstance(config, str):
                            try:
                                config = json.loads(config)
                            except:
                                config = {}
                        existing_agent.moltbook_config = config

                    existing_agent.updated_at = datetime.utcnow()
                    db.session.commit()

                    return jsonify({
                        'success': True,
                        'message': 'Moltbook agent updated successfully',
                        'agent': existing_agent.to_dict()
                    })
                else:
                    import json
                    moltbook_config = data.get('moltbook_config', {})
                    if isinstance(moltbook_config, str):
                        try:
                            moltbook_config = json.loads(moltbook_config)
                        except:
                            moltbook_config = {}

                    agent = Agent(
                        user_id=user_id,
                        name=name,
                        description=data.get('description', ''),
                        avatar_url=data.get('avatar_url', ''),
                        personality=data.get('personality', ''),
                        moltbook_api_key=moltbook_api_key,
                        is_default=(current_agent_count == 0),
                        llm_config={},
                        identity_config={},
                        moltbook_config=moltbook_config
                    )

                    db.session.add(agent)
                    db.session.commit()

                    return jsonify({
                        'success': True,
                        'message': 'Moltbook agent saved successfully',
                        'agent': agent.to_dict()
                    }), 201

            # Otherwise, handle standard export/import format
            import_data = data.get('export', {})

            if not import_data.get('name'):
                return jsonify({'error': 'Invalid import data: missing name'}), 400

            agent = Agent(
                user_id=user_id,
                name=import_data['name'],
                description=import_data.get('description', ''),
                avatar_emoji=import_data.get('avatar_emoji', '🤖'),
                is_default=False,
                llm_config=import_data.get('llm_config', {}),
                identity_config=import_data.get('identity_config', {}),
                moltbook_config={}
            )

            db.session.add(agent)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Agent imported successfully. Please configure API keys.',
                'agent': agent.to_dict()
            }), 201

        except Exception as e:
            print(f"Error importing agent: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    # =========================================================
    # Backward-compatibility aliases for /api/external-agents/*
    # These proxy to the unified /api/agents/* endpoints.
    # =========================================================

    @app.route('/api/external-agents', methods=['GET'])
    @require_auth
    def compat_list_external_agents():
        user_id = session.get('user_id')
        agents = Agent.query.filter_by(user_id=user_id, is_active=True)\
            .filter(Agent.agent_type.in_(['websocket', 'http_api']))\
            .order_by(Agent.is_featured.desc(), Agent.created_at.desc()).all()
        return jsonify({'agents': [a.to_dict() for a in agents]})

    @app.route('/api/external-agents', methods=['POST'])
    @require_auth
    def compat_create_external_agent():
        data = request.get_json() or {}
        if 'agent_type' not in data:
            data['agent_type'] = 'websocket'
        # Forward to unified create
        with app.test_request_context(
            '/api/agents', method='POST',
            json=data, headers=dict(request.headers)
        ):
            session['user_id'] = session.get('user_id')
        # Inline version to avoid test_request_context complexities:
        user_id = session.get('user_id')
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Agent name is required'}), 400

        agent = Agent(
            user_id=user_id,
            name=name,
            description=data.get('description', ''),
            avatar_emoji=data.get('avatar_emoji', '🤖'),
            avatar_url=data.get('avatar_url'),
            agent_type=data.get('agent_type', 'websocket'),
            connection_url=data.get('connection_url', ''),
            auth_config=data.get('auth_config', {}),
            agent_config=data.get('agent_config', {}),
            is_featured=data.get('is_featured', False),
        )
        db.session.add(agent)
        db.session.commit()
        return jsonify({'success': True, 'agent': agent.to_dict()}), 201

    @app.route('/api/external-agents/<int:agent_id>', methods=['PUT'])
    @require_auth
    def compat_update_external_agent(agent_id):
        user_id = session.get('user_id')
        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            return jsonify({'error': 'Agent not found'}), 404
        data = request.get_json() or {}
        for field in ('name', 'description', 'avatar_emoji', 'avatar_url', 'agent_type', 'connection_url'):
            if field in data:
                setattr(agent, field, data[field])
        if 'auth_config' in data:
            agent.auth_config = data['auth_config']
        if 'agent_config' in data:
            agent.agent_config = data['agent_config']
        db.session.commit()
        return jsonify({'success': True, 'agent': agent.to_dict()})

    @app.route('/api/external-agents/<int:agent_id>', methods=['DELETE'])
    @require_auth
    def compat_delete_external_agent(agent_id):
        user_id = session.get('user_id')
        agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            return jsonify({'error': 'Agent not found'}), 404
        agent.is_active = False
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/api/external-agents/<int:agent_id>/test', methods=['POST'])
    @require_auth
    def compat_test_external_agent(agent_id):
        return test_agent(agent_id)

    @app.route('/api/external-agents/featured', methods=['GET'])
    @require_auth
    def compat_get_featured_agents():
        user_id = session.get('user_id')
        featured = Agent.query.filter_by(user_id=user_id, is_featured=True, is_active=True).all()
        return jsonify({'agents': [a.to_dict() for a in featured]})

    @app.route('/api/external-agents/seed-nautilus', methods=['POST'])
    @require_auth
    def compat_seed_nautilus():
        return seed_nautilus()

    @app.route('/api/external-agents/<int:agent_id>/update-status', methods=['POST'])
    @require_auth
    def compat_update_agent_status(agent_id):
        return update_agent_status(agent_id)
