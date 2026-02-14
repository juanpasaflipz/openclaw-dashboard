"""
API routes for the collaboration task system.

Agents coordinate through persisted tasks — no direct agent-to-agent calls.
Every state transition emits a TaskEvent for full auditability.
"""
import uuid
from datetime import datetime
from flask import jsonify, request, session
from functools import wraps
from models import db, Agent, CollaborationTask, TaskEvent, AgentRole, TeamRule
from core.collaboration.governance_hooks import (
    pre_task_start, on_task_started, on_task_completed,
    on_task_failed, on_task_blocked_by_risk,
    on_task_escalated, on_task_reassigned,
)


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def _emit_task_event(task, event_type, agent_id=None, payload=None):
    """Append-only helper — writes a TaskEvent row."""
    evt = TaskEvent(
        task_id=task.id,
        workspace_id=task.workspace_id,
        agent_id=agent_id,
        event_type=event_type,
        payload=payload or {},
        created_at=datetime.utcnow(),
    )
    db.session.add(evt)
    return evt


# Valid status transitions (current_status -> set of allowed next statuses)
_TRANSITIONS = {
    'queued':    {'running', 'canceled'},
    'running':   {'completed', 'failed', 'blocked'},
    'blocked':   {'running', 'canceled'},
    'completed': set(),
    'failed':    set(),
    'canceled':  set(),
}


def _check_assignment_rules(user_id, creator_agent_id, assigned_to_agent_id):
    """Check team rules for role-based assignment enforcement.

    Returns (ok: bool, error_message: str | None).
    When no team rules are configured, assignment is always allowed.
    """
    rules = TeamRule.query.filter_by(workspace_id=user_id).first()
    if not rules:
        return True, None

    # If no hierarchy enforcement is enabled, allow everything
    if not rules.require_supervisor_for_tasks:
        return True, None

    # Human-created tasks (no creator_agent_id) bypass role checks
    if not creator_agent_id:
        return True, None

    creator_role = AgentRole.query.filter_by(
        workspace_id=user_id, agent_id=creator_agent_id,
    ).first()

    target_role = AgentRole.query.filter_by(
        workspace_id=user_id, agent_id=assigned_to_agent_id,
    ).first()

    # Supervisors can assign to anyone
    if creator_role and creator_role.role == 'supervisor':
        return True, None

    # Workers and specialists need permission checks
    if creator_role and creator_role.role in ('worker', 'specialist'):
        # Can assign to self
        if creator_agent_id == assigned_to_agent_id:
            return True, None

        # Can escalate to supervisor if capability is enabled
        if target_role and target_role.role == 'supervisor':
            if creator_role.can_escalate_to_supervisor:
                return True, None
            return False, 'Agent does not have escalation permission'

        # Can assign to peers if workspace allows it AND agent has permission
        if rules.allow_peer_assignment and creator_role.can_assign_to_peers:
            return True, None

        return False, 'Agent does not have permission to assign tasks to peers'

    # Agent without a role in an enforced workspace — treat as worker without permissions
    if target_role and target_role.role == 'supervisor':
        return True, None  # Can always escalate to supervisor by default
    if rules.allow_peer_assignment:
        return True, None  # Peer assignment is open
    return False, 'Agent does not have a role and peer assignment is disabled'


def register_collaboration_tasks_routes(app):
    """Register collaboration task routes with the Flask app."""

    # ------------------------------------------------------------------
    # POST /api/tasks  — create a task
    # ------------------------------------------------------------------
    @app.route('/api/tasks', methods=['POST'])
    @require_auth
    def create_task():
        try:
            user_id = session.get('user_id')
            data = request.get_json(silent=True) or {}

            # Required fields
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'error': 'title is required'}), 400

            assigned_to = data.get('assigned_to_agent_id')
            if not assigned_to:
                return jsonify({'error': 'assigned_to_agent_id is required'}), 400

            # Validate assigned agent belongs to workspace
            agent = Agent.query.filter_by(id=assigned_to, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Assigned agent not found in workspace'}), 404

            # Validate creator agent if provided
            created_by_agent_id = data.get('created_by_agent_id')
            if created_by_agent_id:
                creator = Agent.query.filter_by(id=created_by_agent_id, user_id=user_id).first()
                if not creator:
                    return jsonify({'error': 'Creator agent not found in workspace'}), 404

            # Validate parent task if provided
            parent_task_id = data.get('parent_task_id')
            if parent_task_id:
                parent = CollaborationTask.query.filter_by(
                    id=parent_task_id, workspace_id=user_id,
                ).first()
                if not parent:
                    return jsonify({'error': 'Parent task not found in workspace'}), 404

            # Enforce team hierarchy rules on agent-created tasks
            ok, err = _check_assignment_rules(
                user_id, created_by_agent_id, int(assigned_to),
            )
            if not ok:
                return jsonify({'error': err}), 403

            task_id = str(uuid.uuid4())
            task = CollaborationTask(
                id=task_id,
                workspace_id=user_id,
                created_by_agent_id=created_by_agent_id,
                created_by_user_id=user_id if not created_by_agent_id else None,
                assigned_to_agent_id=int(assigned_to),
                parent_task_id=parent_task_id,
                title=title,
                input=data.get('input'),
                status='queued',
                priority=int(data.get('priority', 0)),
                due_at=_parse_datetime(data.get('due_at')),
            )
            db.session.add(task)

            _emit_task_event(task, 'created', agent_id=created_by_agent_id, payload={
                'title': title,
                'assigned_to_agent_id': int(assigned_to),
                'parent_task_id': parent_task_id,
            })

            db.session.commit()
            return jsonify({'success': True, 'task': task.to_dict()}), 201

        except Exception as e:
            db.session.rollback()
            print(f"Error creating task: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    # ------------------------------------------------------------------
    # GET /api/tasks  — list tasks (filterable)
    # ------------------------------------------------------------------
    @app.route('/api/tasks', methods=['GET'])
    @require_auth
    def list_tasks():
        try:
            user_id = session.get('user_id')
            query = CollaborationTask.query.filter_by(workspace_id=user_id)

            # Optional filters
            status = request.args.get('status')
            if status:
                query = query.filter_by(status=status)

            agent_id = request.args.get('agent_id')
            if agent_id:
                query = query.filter(
                    (CollaborationTask.assigned_to_agent_id == int(agent_id))
                    | (CollaborationTask.created_by_agent_id == int(agent_id))
                )

            assigned_to = request.args.get('assigned_to')
            if assigned_to:
                query = query.filter_by(assigned_to_agent_id=int(assigned_to))

            parent_task_id = request.args.get('parent_task_id')
            if parent_task_id:
                query = query.filter_by(parent_task_id=parent_task_id)

            tasks = query.order_by(
                CollaborationTask.priority.desc(),
                CollaborationTask.created_at.desc(),
            ).limit(100).all()

            return jsonify({
                'success': True,
                'tasks': [t.to_dict() for t in tasks],
                'count': len(tasks),
            })

        except Exception as e:
            print(f"Error listing tasks: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    # ------------------------------------------------------------------
    # GET /api/tasks/<id>  — get single task with events
    # ------------------------------------------------------------------
    @app.route('/api/tasks/<task_id>', methods=['GET'])
    @require_auth
    def get_task(task_id):
        try:
            user_id = session.get('user_id')
            task = CollaborationTask.query.filter_by(
                id=task_id, workspace_id=user_id,
            ).first()
            if not task:
                return jsonify({'error': 'Task not found'}), 404

            events = TaskEvent.query.filter_by(task_id=task_id).order_by(
                TaskEvent.created_at.asc(),
            ).all()

            result = task.to_dict()
            result['events'] = [e.to_dict() for e in events]
            return jsonify({'success': True, 'task': result})

        except Exception as e:
            print(f"Error getting task: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    # ------------------------------------------------------------------
    # POST /api/tasks/<id>/start  — transition queued/blocked -> running
    # ------------------------------------------------------------------
    @app.route('/api/tasks/<task_id>/start', methods=['POST'])
    @require_auth
    def start_task(task_id):
        return _transition_task(task_id, 'running', 'started')

    # ------------------------------------------------------------------
    # POST /api/tasks/<id>/complete  — transition running -> completed
    # ------------------------------------------------------------------
    @app.route('/api/tasks/<task_id>/complete', methods=['POST'])
    @require_auth
    def complete_task(task_id):
        return _transition_task(task_id, 'completed', 'completed')

    # ------------------------------------------------------------------
    # POST /api/tasks/<id>/fail  — transition running -> failed
    # ------------------------------------------------------------------
    @app.route('/api/tasks/<task_id>/fail', methods=['POST'])
    @require_auth
    def fail_task(task_id):
        return _transition_task(task_id, 'failed', 'failed')

    # ------------------------------------------------------------------
    # POST /api/tasks/<id>/cancel  — cancel a queued/blocked task
    # ------------------------------------------------------------------
    @app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
    @require_auth
    def cancel_task(task_id):
        return _transition_task(task_id, 'canceled', 'canceled')

    # ------------------------------------------------------------------
    # POST /api/tasks/<id>/assign  — reassign a task
    # ------------------------------------------------------------------
    @app.route('/api/tasks/<task_id>/assign', methods=['POST'])
    @require_auth
    def reassign_task(task_id):
        try:
            user_id = session.get('user_id')
            data = request.get_json(silent=True) or {}

            task = CollaborationTask.query.filter_by(
                id=task_id, workspace_id=user_id,
            ).first()
            if not task:
                return jsonify({'error': 'Task not found'}), 404

            if task.status in ('completed', 'failed', 'canceled'):
                return jsonify({'error': f'Cannot reassign task in {task.status} status'}), 409

            new_agent_id = data.get('assigned_to_agent_id')
            if not new_agent_id:
                return jsonify({'error': 'assigned_to_agent_id is required'}), 400

            agent = Agent.query.filter_by(id=new_agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Target agent not found in workspace'}), 404

            # Enforce team hierarchy on agent-initiated reassignments
            requesting_agent_id = data.get('agent_id')
            if requesting_agent_id:
                ok, err = _check_assignment_rules(
                    user_id, int(requesting_agent_id), int(new_agent_id),
                )
                if not ok:
                    return jsonify({'error': err}), 403

            old_agent_id = task.assigned_to_agent_id
            task.assigned_to_agent_id = int(new_agent_id)
            task.updated_at = datetime.utcnow()

            # If task was running, reset to queued for the new agent
            if task.status == 'running':
                task.status = 'queued'

            _emit_task_event(task, 'assigned', payload={
                'from_agent_id': old_agent_id,
                'to_agent_id': int(new_agent_id),
            })

            db.session.commit()

            # Governance hooks for reassignment (best-effort)
            on_task_reassigned(task, old_agent_id, int(new_agent_id))

            # Detect escalation: reassignment to a supervisor
            target_role = AgentRole.query.filter_by(
                workspace_id=user_id, agent_id=int(new_agent_id),
            ).first()
            if target_role and target_role.role == 'supervisor':
                on_task_escalated(task, old_agent_id, int(new_agent_id))

            return jsonify({'success': True, 'task': task.to_dict()})

        except Exception as e:
            db.session.rollback()
            print(f"Error reassigning task: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    # ------------------------------------------------------------------
    # Internal helper for state transitions
    # ------------------------------------------------------------------
    def _transition_task(task_id, new_status, event_type):
        try:
            user_id = session.get('user_id')
            data = request.get_json(silent=True) or {}

            task = CollaborationTask.query.filter_by(
                id=task_id, workspace_id=user_id,
            ).first()
            if not task:
                return jsonify({'error': 'Task not found'}), 404

            allowed = _TRANSITIONS.get(task.status, set())
            if new_status not in allowed:
                return jsonify({
                    'error': f'Cannot transition from {task.status} to {new_status}',
                }), 409

            # Governance hook: pre-start risk check
            if new_status == 'running':
                ok, reason = pre_task_start(task)
                if not ok:
                    # Block the task instead of starting it
                    task.status = 'blocked'
                    task.updated_at = datetime.utcnow()
                    _emit_task_event(task, 'blocked', payload={
                        'reason': reason,
                    })
                    db.session.commit()
                    on_task_blocked_by_risk(task, reason)
                    return jsonify({
                        'success': False,
                        'blocked': True,
                        'reason': reason,
                        'task': task.to_dict(),
                    }), 409

            previous_status = task.status
            task.status = new_status
            task.updated_at = datetime.utcnow()

            # Capture output on completion/failure
            if new_status in ('completed', 'failed') and 'output' in data:
                task.output = data['output']

            payload = {'previous_status': previous_status}
            if data.get('reason'):
                payload['reason'] = data['reason']
            if data.get('output'):
                payload['output_summary'] = str(data['output'])[:500]

            _emit_task_event(
                task, event_type,
                agent_id=data.get('agent_id'),
                payload=payload,
            )

            db.session.commit()

            # Post-transition governance hooks (best-effort, never block)
            if new_status == 'running':
                on_task_started(task)
            elif new_status == 'completed':
                on_task_completed(task, output=data.get('output'))
            elif new_status == 'failed':
                on_task_failed(task, reason=data.get('reason'))

            return jsonify({'success': True, 'task': task.to_dict()})

        except Exception as e:
            db.session.rollback()
            print(f"Error transitioning task: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500


def _parse_datetime(value):
    """Parse an ISO 8601 datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None
