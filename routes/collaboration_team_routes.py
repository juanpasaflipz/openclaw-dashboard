"""
API routes for the collaboration team hierarchy system.

Provides optional, human-defined agent roles (supervisor/worker/specialist)
and workspace-level team rules that influence task assignment enforcement.
"""
from datetime import datetime
from flask import jsonify, request, session
from functools import wraps
from models import db, Agent, AgentRole, TeamRule


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def register_collaboration_team_routes(app):
    """Register collaboration team hierarchy routes with the Flask app."""

    # ------------------------------------------------------------------
    # GET /api/team/roles  — list all agent roles in workspace
    # ------------------------------------------------------------------
    @app.route('/api/team/roles', methods=['GET'])
    @require_auth
    def collab_list_roles():
        try:
            user_id = session.get('user_id')
            roles = AgentRole.query.filter_by(workspace_id=user_id).all()
            return jsonify({
                'success': True,
                'roles': [r.to_dict() for r in roles],
                'count': len(roles),
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # GET /api/team/roles/<agent_id>  — get role for a specific agent
    # ------------------------------------------------------------------
    @app.route('/api/team/roles/<int:agent_id>', methods=['GET'])
    @require_auth
    def collab_get_role(agent_id):
        try:
            user_id = session.get('user_id')

            # Verify agent belongs to workspace
            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Agent not found in workspace'}), 404

            role = AgentRole.query.filter_by(
                workspace_id=user_id, agent_id=agent_id,
            ).first()
            if not role:
                return jsonify({'error': 'No role assigned to this agent'}), 404

            return jsonify({'success': True, 'role': role.to_dict()})

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # POST /api/team/roles  — assign or update a role for an agent
    # ------------------------------------------------------------------
    @app.route('/api/team/roles', methods=['POST'])
    @require_auth
    def collab_set_role():
        try:
            user_id = session.get('user_id')
            data = request.get_json(silent=True) or {}

            agent_id = data.get('agent_id')
            if not agent_id:
                return jsonify({'error': 'agent_id is required'}), 400

            role_name = data.get('role', '').strip()
            if role_name not in AgentRole.VALID_ROLES:
                return jsonify({
                    'error': f'Invalid role. Must be one of: {", ".join(sorted(AgentRole.VALID_ROLES))}',
                }), 400

            # Verify agent belongs to workspace
            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Agent not found in workspace'}), 404

            # Upsert: update if exists, create if not
            existing = AgentRole.query.filter_by(
                workspace_id=user_id, agent_id=agent_id,
            ).first()

            if existing:
                existing.role = role_name
                if 'can_assign_to_peers' in data:
                    existing.can_assign_to_peers = bool(data['can_assign_to_peers'])
                if 'can_escalate_to_supervisor' in data:
                    existing.can_escalate_to_supervisor = bool(data['can_escalate_to_supervisor'])
                existing.updated_at = datetime.utcnow()
                role_obj = existing
            else:
                role_obj = AgentRole(
                    workspace_id=user_id,
                    agent_id=int(agent_id),
                    role=role_name,
                    can_assign_to_peers=bool(data.get('can_assign_to_peers', False)),
                    can_escalate_to_supervisor=bool(data.get('can_escalate_to_supervisor', True)),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.session.add(role_obj)

            db.session.commit()
            return jsonify({'success': True, 'role': role_obj.to_dict()}), 201

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # POST /api/team/roles/<agent_id>/delete  — remove a role assignment
    # ------------------------------------------------------------------
    @app.route('/api/team/roles/<int:agent_id>/delete', methods=['POST'])
    @require_auth
    def collab_delete_role(agent_id):
        try:
            user_id = session.get('user_id')
            role = AgentRole.query.filter_by(
                workspace_id=user_id, agent_id=agent_id,
            ).first()
            if not role:
                return jsonify({'error': 'No role found for this agent'}), 404

            db.session.delete(role)
            db.session.commit()
            return jsonify({'success': True})

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # GET /api/team/rules  — get workspace team rules
    # ------------------------------------------------------------------
    @app.route('/api/team/rules', methods=['GET'])
    @require_auth
    def collab_get_rules():
        try:
            user_id = session.get('user_id')
            rules = TeamRule.query.filter_by(workspace_id=user_id).first()
            if not rules:
                # Return defaults if no rules configured yet
                return jsonify({
                    'success': True,
                    'rules': {
                        'workspace_id': user_id,
                        'allow_peer_assignment': False,
                        'require_supervisor_for_tasks': False,
                        'default_supervisor_agent_id': None,
                        'created_at': None,
                        'updated_at': None,
                    },
                })
            return jsonify({'success': True, 'rules': rules.to_dict()})

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # POST /api/team/rules  — update workspace team rules
    # ------------------------------------------------------------------
    @app.route('/api/team/rules', methods=['POST'])
    @require_auth
    def collab_set_rules():
        try:
            user_id = session.get('user_id')
            data = request.get_json(silent=True) or {}

            # Validate default_supervisor if provided
            supervisor_id = data.get('default_supervisor_agent_id')
            if supervisor_id is not None:
                if supervisor_id:  # non-null, non-zero
                    agent = Agent.query.filter_by(id=supervisor_id, user_id=user_id).first()
                    if not agent:
                        return jsonify({'error': 'Supervisor agent not found in workspace'}), 404
                    # Verify agent has supervisor role
                    role = AgentRole.query.filter_by(
                        workspace_id=user_id, agent_id=supervisor_id,
                    ).first()
                    if not role or role.role != 'supervisor':
                        return jsonify({
                            'error': 'Agent must have supervisor role to be default supervisor',
                        }), 400

            rules = TeamRule.query.filter_by(workspace_id=user_id).first()
            if rules:
                if 'allow_peer_assignment' in data:
                    rules.allow_peer_assignment = bool(data['allow_peer_assignment'])
                if 'require_supervisor_for_tasks' in data:
                    rules.require_supervisor_for_tasks = bool(data['require_supervisor_for_tasks'])
                if 'default_supervisor_agent_id' in data:
                    rules.default_supervisor_agent_id = supervisor_id or None
                rules.updated_at = datetime.utcnow()
            else:
                rules = TeamRule(
                    workspace_id=user_id,
                    allow_peer_assignment=bool(data.get('allow_peer_assignment', False)),
                    require_supervisor_for_tasks=bool(data.get('require_supervisor_for_tasks', False)),
                    default_supervisor_agent_id=supervisor_id or None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.session.add(rules)

            db.session.commit()
            return jsonify({'success': True, 'rules': rules.to_dict()}), 201

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # GET /api/team/summary  — team overview (roles + rules + agents)
    # ------------------------------------------------------------------
    @app.route('/api/team/summary', methods=['GET'])
    @require_auth
    def collab_team_summary():
        try:
            user_id = session.get('user_id')

            roles = AgentRole.query.filter_by(workspace_id=user_id).all()
            rules = TeamRule.query.filter_by(workspace_id=user_id).first()

            # Group agents by role
            supervisors = [r.to_dict() for r in roles if r.role == 'supervisor']
            workers = [r.to_dict() for r in roles if r.role == 'worker']
            specialists = [r.to_dict() for r in roles if r.role == 'specialist']

            # Agents without roles
            assigned_ids = {r.agent_id for r in roles}
            unassigned = Agent.query.filter(
                Agent.user_id == user_id,
                Agent.is_active == True,
                ~Agent.id.in_(assigned_ids) if assigned_ids else True,
            ).all()

            return jsonify({
                'success': True,
                'supervisors': supervisors,
                'workers': workers,
                'specialists': specialists,
                'unassigned_agents': [{'id': a.id, 'name': a.name} for a in unassigned],
                'rules': rules.to_dict() if rules else None,
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500
