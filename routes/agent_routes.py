"""
API routes for multi-agent management
"""
from flask import jsonify, request, session
from models import db, User, Agent
from datetime import datetime
from functools import wraps


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
        """List all agents for the current user"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Get all agents for this user
            agents = Agent.query.filter_by(user_id=user_id).order_by(
                Agent.is_default.desc(),
                Agent.created_at.desc()
            ).all()

            # Check subscription limits
            max_agents = user.get_max_agents()

            return jsonify({
                'success': True,
                'agents': [agent.to_dict() for agent in agents],
                'count': len(agents),
                'max_agents': max_agents,
                'can_create_more': len(agents) < max_agents
            })

        except Exception as e:
            print(f"❌ Error listing agents: {e}")
            return jsonify({'error': str(e)}), 500

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
            print(f"❌ Error getting agent: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/agents', methods=['POST'])
    @require_auth
    def create_agent():
        """Create a new agent"""
        try:
            user_id = session.get('user_id')
            user = User.query.get(user_id)

            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Check subscription limits
            current_agent_count = Agent.query.filter_by(user_id=user_id).count()
            max_agents = user.get_max_agents()

            if current_agent_count >= max_agents:
                return jsonify({
                    'error': f'Agent limit reached. Your plan allows {max_agents} agent(s). Upgrade to create more.',
                    'max_agents': max_agents,
                    'current_count': current_agent_count
                }), 403

            data = request.get_json() or {}

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
                is_default=data.get('is_default', False),
                llm_config=data.get('llm_config', {}),
                identity_config=data.get('identity_config', {}),
                moltbook_config=data.get('moltbook_config', {})
            )

            # If this is set as default, unset other defaults
            if agent.is_default:
                Agent.query.filter_by(user_id=user_id, is_default=True).update({'is_default': False})

            db.session.add(agent)
            db.session.commit()

            print(f"✅ New agent created: {agent.name} (user: {user.email})")

            return jsonify({
                'success': True,
                'message': 'Agent created successfully',
                'agent': agent.to_dict()
            }), 201

        except Exception as e:
            print(f"❌ Error creating agent: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

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
            if 'name' in data:
                agent.name = data['name'].strip()
            if 'description' in data:
                agent.description = data['description']
            if 'avatar_emoji' in data:
                agent.avatar_emoji = data['avatar_emoji']
            if 'is_active' in data:
                agent.is_active = data['is_active']

            # Handle default agent setting
            if 'is_default' in data and data['is_default']:
                # Unset other defaults first
                Agent.query.filter_by(user_id=user_id, is_default=True).update({'is_default': False})
                agent.is_default = True

            # Update configurations
            if 'llm_config' in data:
                agent.llm_config = data['llm_config']
            if 'identity_config' in data:
                agent.identity_config = data['identity_config']
            if 'moltbook_config' in data:
                agent.moltbook_config = data['moltbook_config']

            agent.updated_at = datetime.utcnow()
            db.session.commit()

            print(f"✅ Agent updated: {agent.name}")

            return jsonify({
                'success': True,
                'message': 'Agent updated successfully',
                'agent': agent.to_dict()
            })

        except Exception as e:
            print(f"❌ Error updating agent: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/agents/<int:agent_id>', methods=['DELETE'])
    @require_auth
    def delete_agent(agent_id):
        """Delete an agent"""
        try:
            user_id = session.get('user_id')
            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()

            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            # Don't allow deleting the last agent
            agent_count = Agent.query.filter_by(user_id=user_id).count()
            if agent_count <= 1:
                return jsonify({'error': 'Cannot delete your last agent'}), 400

            agent_name = agent.name
            db.session.delete(agent)

            # If this was the default agent, make another one default
            if agent.is_default:
                next_agent = Agent.query.filter_by(user_id=user_id).first()
                if next_agent:
                    next_agent.is_default = True

            db.session.commit()

            print(f"✅ Agent deleted: {agent_name}")

            return jsonify({
                'success': True,
                'message': 'Agent deleted successfully'
            })

        except Exception as e:
            print(f"❌ Error deleting agent: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

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
            current_agent_count = Agent.query.filter_by(user_id=user_id).count()
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
                is_default=False,
                llm_config=source_agent.llm_config.copy() if source_agent.llm_config else {},
                identity_config=source_agent.identity_config.copy() if source_agent.identity_config else {},
                moltbook_config=source_agent.moltbook_config.copy() if source_agent.moltbook_config else {}
            )

            db.session.add(clone)
            db.session.commit()

            print(f"✅ Agent cloned: {source_agent.name} -> {clone.name}")

            return jsonify({
                'success': True,
                'message': 'Agent cloned successfully',
                'agent': clone.to_dict()
            }), 201

        except Exception as e:
            print(f"❌ Error cloning agent: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

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
                'identity_config': agent.identity_config or {},
                'llm_config': {
                    'provider': agent.llm_config.get('provider') if agent.llm_config else None,
                    'model': agent.llm_config.get('model') if agent.llm_config else None,
                    'temperature': agent.llm_config.get('temperature') if agent.llm_config else None,
                    # Exclude API keys for security
                },
                'exported_at': datetime.utcnow().isoformat(),
                'green_monkey_version': '1.0.0'
            }

            return jsonify({
                'success': True,
                'export': export_data
            })

        except Exception as e:
            print(f"❌ Error exporting agent: {e}")
            return jsonify({'error': str(e)}), 500

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
            current_agent_count = Agent.query.filter_by(user_id=user_id).count()
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
                        # Parse if string, use directly if dict
                        config = data['moltbook_config']
                        if isinstance(config, str):
                            try:
                                config = json.loads(config)
                            except:
                                config = {}
                        existing_agent.moltbook_config = config

                    existing_agent.updated_at = datetime.utcnow()
                    db.session.commit()

                    print(f"✅ Moltbook agent updated: {existing_agent.name}")

                    return jsonify({
                        'success': True,
                        'message': 'Moltbook agent updated successfully',
                        'agent': existing_agent.to_dict()
                    })
                else:
                    # Create new Moltbook agent
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
                        is_default=(current_agent_count == 0),  # First agent is default
                        llm_config={},
                        identity_config={},
                        moltbook_config=moltbook_config
                    )

                    db.session.add(agent)
                    db.session.commit()

                    print(f"✅ Moltbook agent saved: {agent.name} (user: {user.email})")

                    return jsonify({
                        'success': True,
                        'message': 'Moltbook agent saved successfully',
                        'agent': agent.to_dict()
                    }), 201

            # Otherwise, handle standard export/import format
            import_data = data.get('export', {})

            # Validate import data
            if not import_data.get('name'):
                return jsonify({'error': 'Invalid import data: missing name'}), 400

            # Create agent from import
            agent = Agent(
                user_id=user_id,
                name=import_data['name'],
                description=import_data.get('description', ''),
                avatar_emoji=import_data.get('avatar_emoji', '🤖'),
                is_default=False,
                llm_config=import_data.get('llm_config', {}),
                identity_config=import_data.get('identity_config', {}),
                moltbook_config={}  # User needs to reconfigure API keys
            )

            db.session.add(agent)
            db.session.commit()

            print(f"✅ Agent imported: {agent.name}")

            return jsonify({
                'success': True,
                'message': 'Agent imported successfully. Please configure API keys.',
                'agent': agent.to_dict()
            }), 201

        except Exception as e:
            print(f"❌ Error importing agent: {e}")
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
