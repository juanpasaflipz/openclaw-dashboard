"""
External Agents Routes — manage third-party agents including Nautilus.
"""
from flask import jsonify, request, session
from datetime import datetime
from models import db, ExternalAgent
import requests as http_requests


def register_external_agents_routes(app):

    @app.route('/api/external-agents', methods=['GET'])
    def list_external_agents():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        agents = ExternalAgent.query.filter_by(user_id=user_id, is_active=True)\
            .order_by(ExternalAgent.is_featured.desc(), ExternalAgent.created_at.desc()).all()
        return jsonify({'agents': [a.to_dict() for a in agents]})

    @app.route('/api/external-agents', methods=['POST'])
    def create_external_agent():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Agent name is required'}), 400

        agent = ExternalAgent(
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
    def update_external_agent(agent_id):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        agent = ExternalAgent.query.filter_by(id=agent_id, user_id=user_id).first()
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
    def delete_external_agent(agent_id):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        agent = ExternalAgent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        agent.is_active = False
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/api/external-agents/<int:agent_id>/test', methods=['POST'])
    def test_external_agent(agent_id):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        agent = ExternalAgent.query.filter_by(id=agent_id, user_id=user_id).first()
        if not agent:
            return jsonify({'error': 'Agent not found'}), 404

        try:
            if agent.agent_type == 'http_api':
                # HTTP health check
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
                # For WebSocket agents, we can't test from Flask backend.
                # Return the connection info for the frontend to test directly.
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

    @app.route('/api/external-agents/featured', methods=['GET'])
    def get_featured_agents():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        featured = ExternalAgent.query.filter_by(user_id=user_id, is_featured=True, is_active=True).all()
        return jsonify({'agents': [a.to_dict() for a in featured]})

    @app.route('/api/external-agents/seed-nautilus', methods=['POST'])
    def seed_nautilus():
        """Seed Nautilus as the featured agent for the current user."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        # Check if Nautilus already exists for this user
        existing = ExternalAgent.query.filter_by(user_id=user_id, name='Nautilus').first()
        if existing:
            return jsonify({'success': True, 'agent': existing.to_dict(), 'already_exists': True})

        nautilus = ExternalAgent(
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

    @app.route('/api/external-agents/<int:agent_id>/update-status', methods=['POST'])
    def update_agent_status(agent_id):
        """Update agent connection status (called by frontend after WebSocket connect/disconnect)."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        agent = ExternalAgent.query.filter_by(id=agent_id, user_id=user_id).first()
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
