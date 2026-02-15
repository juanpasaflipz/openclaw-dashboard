"""
Blueprint API — REST endpoints for the Agent Blueprint & Capability system.

Endpoints:
    Blueprints:
        GET    /api/blueprints                         — list blueprints
        POST   /api/blueprints                         — create draft blueprint
        GET    /api/blueprints/<id>                     — get blueprint detail
        POST   /api/blueprints/<id>                     — update draft blueprint
        POST   /api/blueprints/<id>/publish             — publish a new version
        POST   /api/blueprints/<id>/archive             — archive blueprint
        POST   /api/blueprints/<id>/clone               — clone from version
        GET    /api/blueprints/<id>/versions             — list versions
        GET    /api/blueprints/<id>/versions/<ver>       — get version detail

    Capability Bundles:
        GET    /api/capabilities                        — list bundles
        POST   /api/capabilities                        — create bundle
        GET    /api/capabilities/<id>                    — get bundle
        POST   /api/capabilities/<id>                    — update bundle

    Agent Instantiation:
        POST   /api/agents/<id>/instantiate              — bind agent to blueprint
        GET    /api/agents/<id>/instance                 — get instance binding
        POST   /api/agents/<id>/instance/refresh         — refresh policy snapshot
        DELETE /api/agents/<id>/instance                 — remove instance (legacy mode)
"""
from functools import wraps

from flask import jsonify, request, session

from models import db


# ---------------------------------------------------------------------------
# Auth helper (matches existing codebase pattern)
# ---------------------------------------------------------------------------

def _require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_blueprint_routes(app):
    """Register Agent Blueprint & Capability API routes."""

    # ===================================================================
    # Blueprints
    # ===================================================================

    @app.route('/api/blueprints', methods=['GET'])
    @_require_auth
    def list_blueprints_api():
        """List blueprints for the authenticated workspace."""
        try:
            from core.identity.blueprint_registry import list_blueprints, count_blueprints

            user_id = session['user_id']
            status = request.args.get('status')
            role_type = request.args.get('role_type')
            limit = min(request.args.get('limit', 50, type=int), 100)
            offset = request.args.get('offset', 0, type=int)

            blueprints = list_blueprints(
                user_id, status=status, role_type=role_type,
                limit=limit, offset=offset,
            )
            total = count_blueprints(user_id, status=status)

            return jsonify({
                'blueprints': [bp.to_dict() for bp in blueprints],
                'total': total,
                'limit': limit,
                'offset': offset,
            })
        except Exception as e:
            print(f"[blueprint_api] list_blueprints error: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints', methods=['POST'])
    @_require_auth
    def create_blueprint_api():
        """Create a new draft blueprint."""
        try:
            from core.identity.agent_blueprint import create_blueprint

            user_id = session['user_id']
            data = request.get_json() or {}

            name = (data.get('name') or '').strip()
            if not name:
                return jsonify({'error': 'Name is required'}), 400

            description = (data.get('description') or '').strip() or None
            role_type = data.get('role_type', 'worker')

            bp = create_blueprint(
                workspace_id=user_id,
                name=name,
                created_by=user_id,
                description=description,
                role_type=role_type,
            )

            return jsonify({
                'success': True,
                'message': 'Blueprint created',
                'blueprint': bp.to_dict(),
            }), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] create_blueprint error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints/<blueprint_id>', methods=['GET'])
    @_require_auth
    def get_blueprint_api(blueprint_id):
        """Get a single blueprint with its latest version info."""
        try:
            from core.identity.agent_blueprint import get_blueprint

            user_id = session['user_id']
            bp = get_blueprint(blueprint_id, user_id)
            if bp is None:
                return jsonify({'error': 'Blueprint not found'}), 404

            result = bp.to_dict()
            # Include instance count
            result['instance_count'] = bp.instances.count()

            return jsonify({'blueprint': result})
        except Exception as e:
            print(f"[blueprint_api] get_blueprint error: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints/<blueprint_id>', methods=['POST'])
    @_require_auth
    def update_blueprint_api(blueprint_id):
        """Update a draft blueprint's metadata."""
        try:
            from core.identity.agent_blueprint import update_draft_blueprint

            user_id = session['user_id']
            data = request.get_json() or {}

            fields = {}
            for key in ('name', 'description', 'role_type'):
                if key in data:
                    value = data[key]
                    if key in ('name', 'description') and isinstance(value, str):
                        value = value.strip()
                    fields[key] = value

            if not fields:
                return jsonify({'error': 'No fields to update'}), 400

            bp = update_draft_blueprint(blueprint_id, user_id, **fields)

            return jsonify({
                'success': True,
                'message': 'Blueprint updated',
                'blueprint': bp.to_dict(),
            })
        except LookupError as e:
            return jsonify({'error': str(e)}), 404
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] update_blueprint error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints/<blueprint_id>/publish', methods=['POST'])
    @_require_auth
    def publish_blueprint_api(blueprint_id):
        """Publish a new immutable version of a blueprint."""
        try:
            from core.identity.agent_blueprint import publish_blueprint

            user_id = session['user_id']
            data = request.get_json() or {}

            ver = publish_blueprint(
                blueprint_id=blueprint_id,
                workspace_id=user_id,
                published_by=user_id,
                allowed_models=data.get('allowed_models'),
                allowed_tools=data.get('allowed_tools'),
                default_risk_profile=data.get('default_risk_profile'),
                hierarchy_defaults=data.get('hierarchy_defaults'),
                memory_strategy=data.get('memory_strategy'),
                escalation_rules=data.get('escalation_rules'),
                llm_defaults=data.get('llm_defaults'),
                identity_defaults=data.get('identity_defaults'),
                override_policy=data.get('override_policy'),
                changelog=data.get('changelog'),
                capability_ids=data.get('capability_ids'),
            )

            return jsonify({
                'success': True,
                'message': f'Published version {ver.version}',
                'version': ver.to_dict(),
            }), 201
        except LookupError as e:
            return jsonify({'error': str(e)}), 404
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] publish_blueprint error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints/<blueprint_id>/archive', methods=['POST'])
    @_require_auth
    def archive_blueprint_api(blueprint_id):
        """Archive a published blueprint."""
        try:
            from core.identity.agent_blueprint import archive_blueprint

            user_id = session['user_id']
            bp = archive_blueprint(blueprint_id, user_id)

            return jsonify({
                'success': True,
                'message': 'Blueprint archived',
                'blueprint': bp.to_dict(),
            })
        except LookupError as e:
            return jsonify({'error': str(e)}), 404
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] archive_blueprint error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints/<blueprint_id>/clone', methods=['POST'])
    @_require_auth
    def clone_blueprint_api(blueprint_id):
        """Clone a blueprint version into a new draft."""
        try:
            from core.identity.agent_blueprint import clone_blueprint

            user_id = session['user_id']
            data = request.get_json() or {}

            source_version = data.get('version')
            if source_version is None:
                return jsonify({'error': 'version is required'}), 400

            name = (data.get('name') or '').strip() or None

            new_bp = clone_blueprint(
                source_blueprint_id=blueprint_id,
                source_version=int(source_version),
                workspace_id=user_id,
                created_by=user_id,
                name=name,
            )

            return jsonify({
                'success': True,
                'message': 'Blueprint cloned',
                'blueprint': new_bp.to_dict(),
            }), 201
        except LookupError as e:
            return jsonify({'error': str(e)}), 404
        except (ValueError, TypeError) as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] clone_blueprint error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints/<blueprint_id>/versions', methods=['GET'])
    @_require_auth
    def list_versions_api(blueprint_id):
        """List all versions of a blueprint."""
        try:
            from core.identity.agent_blueprint import get_blueprint
            from core.identity.blueprint_registry import list_blueprint_versions

            user_id = session['user_id']
            bp = get_blueprint(blueprint_id, user_id)
            if bp is None:
                return jsonify({'error': 'Blueprint not found'}), 404

            limit = min(request.args.get('limit', 50, type=int), 100)
            versions = list_blueprint_versions(blueprint_id, user_id, limit=limit)

            return jsonify({
                'versions': [v.to_dict() for v in versions],
                'total': len(versions),
            })
        except Exception as e:
            print(f"[blueprint_api] list_versions error: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints/<blueprint_id>/versions/<int:version>', methods=['GET'])
    @_require_auth
    def get_version_api(blueprint_id, version):
        """Get a specific version of a blueprint."""
        try:
            from core.identity.agent_blueprint import get_blueprint_version

            user_id = session['user_id']
            ver = get_blueprint_version(blueprint_id, version, user_id)
            if ver is None:
                return jsonify({'error': 'Version not found'}), 404

            result = ver.to_dict()
            # Include attached capability bundle names
            result['capabilities'] = [
                {'id': c.id, 'name': c.name}
                for c in ver.capabilities
            ]

            return jsonify({'version': result})
        except Exception as e:
            print(f"[blueprint_api] get_version error: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    # ===================================================================
    # Capability Bundles
    # ===================================================================

    @app.route('/api/capabilities', methods=['GET'])
    @_require_auth
    def list_capabilities_api():
        """List capability bundles for the workspace."""
        try:
            from core.identity.agent_capabilities import list_capability_bundles

            user_id = session['user_id']
            bundles = list_capability_bundles(user_id)

            return jsonify({
                'capabilities': [b.to_dict() for b in bundles],
                'total': len(bundles),
            })
        except Exception as e:
            print(f"[blueprint_api] list_capabilities error: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/capabilities', methods=['POST'])
    @_require_auth
    def create_capability_api():
        """Create a new capability bundle."""
        try:
            from core.identity.agent_capabilities import create_capability_bundle

            user_id = session['user_id']
            data = request.get_json() or {}

            name = (data.get('name') or '').strip()
            if not name:
                return jsonify({'error': 'Name is required'}), 400

            bundle = create_capability_bundle(
                workspace_id=user_id,
                name=name,
                description=(data.get('description') or '').strip() or None,
                tool_set=data.get('tool_set'),
                model_constraints=data.get('model_constraints'),
                risk_constraints=data.get('risk_constraints'),
            )

            return jsonify({
                'success': True,
                'message': 'Capability bundle created',
                'capability': bundle.to_dict(),
            }), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] create_capability error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/capabilities/<int:bundle_id>', methods=['GET'])
    @_require_auth
    def get_capability_api(bundle_id):
        """Get a single capability bundle."""
        try:
            from core.identity.agent_capabilities import get_capability_bundle

            user_id = session['user_id']
            bundle = get_capability_bundle(bundle_id, user_id)
            if bundle is None:
                return jsonify({'error': 'Capability bundle not found'}), 404

            return jsonify({'capability': bundle.to_dict()})
        except Exception as e:
            print(f"[blueprint_api] get_capability error: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/capabilities/<int:bundle_id>', methods=['POST'])
    @_require_auth
    def update_capability_api(bundle_id):
        """Update a capability bundle."""
        try:
            from core.identity.agent_capabilities import update_capability_bundle

            user_id = session['user_id']
            data = request.get_json() or {}

            fields = {}
            for key in ('name', 'description', 'tool_set', 'model_constraints', 'risk_constraints'):
                if key in data:
                    value = data[key]
                    if key in ('name', 'description') and isinstance(value, str):
                        value = value.strip()
                    fields[key] = value

            if not fields:
                return jsonify({'error': 'No fields to update'}), 400

            bundle = update_capability_bundle(bundle_id, user_id, **fields)

            return jsonify({
                'success': True,
                'message': 'Capability bundle updated',
                'capability': bundle.to_dict(),
            })
        except LookupError as e:
            return jsonify({'error': str(e)}), 404
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] update_capability error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    # ===================================================================
    # Agent Instantiation (extends /api/agents)
    # ===================================================================

    @app.route('/api/agents/<int:agent_id>/instantiate', methods=['POST'])
    @_require_auth
    def instantiate_agent_api(agent_id):
        """Bind an agent to a blueprint version."""
        try:
            from core.identity.agent_instance import instantiate_agent

            user_id = session['user_id']
            data = request.get_json() or {}

            blueprint_id = data.get('blueprint_id')
            if not blueprint_id:
                return jsonify({'error': 'blueprint_id is required'}), 400

            version = data.get('version')
            if version is None:
                return jsonify({'error': 'version is required'}), 400

            overrides = data.get('overrides')

            instance = instantiate_agent(
                agent_id=agent_id,
                blueprint_id=blueprint_id,
                version=int(version),
                workspace_id=user_id,
                instantiated_by=user_id,
                overrides=overrides,
            )

            return jsonify({
                'success': True,
                'message': 'Agent instantiated from blueprint',
                'instance': instance.to_dict(),
            }), 201
        except LookupError as e:
            return jsonify({'error': str(e)}), 404
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] instantiate_agent error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/<int:agent_id>/instance', methods=['GET'])
    @_require_auth
    def get_agent_instance_api(agent_id):
        """Get an agent's blueprint instance binding."""
        try:
            from models import Agent
            from core.identity.agent_instance import get_agent_instance

            user_id = session['user_id']

            # Verify agent belongs to this workspace
            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if agent is None:
                return jsonify({'error': 'Agent not found'}), 404

            instance = get_agent_instance(agent_id)
            if instance is None:
                return jsonify({
                    'instance': None,
                    'is_legacy': True,
                    'message': 'Agent has no blueprint binding (legacy mode)',
                })

            return jsonify({
                'instance': instance.to_dict(),
                'is_legacy': False,
            })
        except Exception as e:
            print(f"[blueprint_api] get_agent_instance error: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/<int:agent_id>/instance/refresh', methods=['POST'])
    @_require_auth
    def refresh_instance_api(agent_id):
        """Refresh an agent instance's policy snapshot, optionally upgrading version."""
        try:
            from core.identity.agent_instance import refresh_instance_policy

            user_id = session['user_id']
            data = request.get_json() or {}

            new_version = data.get('version')
            if new_version is not None:
                new_version = int(new_version)
            new_overrides = data.get('overrides')

            instance = refresh_instance_policy(
                agent_id=agent_id,
                workspace_id=user_id,
                new_version=new_version,
                new_overrides=new_overrides,
            )

            return jsonify({
                'success': True,
                'message': 'Instance policy refreshed',
                'instance': instance.to_dict(),
            })
        except LookupError as e:
            return jsonify({'error': str(e)}), 404
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] refresh_instance error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/agents/<int:agent_id>/instance', methods=['DELETE'])
    @_require_auth
    def remove_instance_api(agent_id):
        """Remove an agent's blueprint binding, returning to legacy mode."""
        try:
            from core.identity.agent_instance import remove_agent_instance

            user_id = session['user_id']
            removed = remove_agent_instance(agent_id, user_id)

            if not removed:
                return jsonify({'error': 'No instance binding found for this agent'}), 404

            return jsonify({
                'success': True,
                'message': 'Instance removed — agent returned to legacy mode',
            })
        except Exception as e:
            print(f"[blueprint_api] remove_instance error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    # ===================================================================
    # Backward Compatibility — Legacy Agent Migration
    # ===================================================================

    @app.route('/api/agents/<int:agent_id>/convert-to-blueprint', methods=['POST'])
    @_require_auth
    def convert_agent_api(agent_id):
        """Convert a legacy agent to blueprint-managed by generating an implicit blueprint."""
        try:
            from models import Agent
            from core.identity.backward_compat import generate_implicit_blueprint

            user_id = session['user_id']

            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if agent is None:
                return jsonify({'error': 'Agent not found'}), 404

            bp, ver, instance = generate_implicit_blueprint(agent, created_by=user_id)

            return jsonify({
                'success': True,
                'message': f'Agent "{agent.name}" converted to blueprint-managed',
                'blueprint': bp.to_dict(),
                'version': ver.to_dict(),
                'instance': instance.to_dict(),
            }), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            print(f"[blueprint_api] convert_agent error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/blueprints/migrate-workspace', methods=['POST'])
    @_require_auth
    def migrate_workspace_api():
        """Convert all legacy agents in the workspace to blueprint-managed."""
        try:
            from core.identity.backward_compat import migrate_workspace_agents

            user_id = session['user_id']
            results = migrate_workspace_agents(user_id, created_by=user_id)

            converted = sum(1 for r in results if r['status'] == 'converted')
            skipped = sum(1 for r in results if r['status'] == 'skipped')
            errors = sum(1 for r in results if r['status'] == 'error')

            return jsonify({
                'success': True,
                'message': f'Migration complete: {converted} converted, {skipped} skipped, {errors} errors',
                'results': results,
                'summary': {
                    'converted': converted,
                    'skipped': skipped,
                    'errors': errors,
                    'total': len(results),
                },
            })
        except Exception as e:
            print(f"[blueprint_api] migrate_workspace error: {e}")
            db.session.rollback()
            return jsonify({'error': 'An internal error occurred'}), 500
