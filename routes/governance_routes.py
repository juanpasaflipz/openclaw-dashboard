"""
Governance routes — Policy change request, approval, delegation, and audit endpoints.

Phase 1:
    POST /api/governance/request             — Agent submits a policy change request
    GET  /api/governance/requests            — List requests for the workspace
Phase 2:
    POST /api/governance/approve/<id>        — Human approves a request
    POST /api/governance/deny/<id>           — Human denies a request
Phase 3:
    POST /api/governance/delegate/apply      — Agent applies change via delegation grant
    GET  /api/governance/delegations         — List active delegation grants
    POST /api/governance/delegations/<id>/revoke — Human revokes a grant
    POST /api/governance/internal/expire     — Cron: expire requests and grants
Phase 4:
    POST /api/governance/rollback/<audit_id> — Human rolls back a policy change
    GET  /api/governance/audit              — Query governance audit trail
Phase 5:
    GET  /api/governance/pending            — List pending requests (UI convenience)
"""
import os
from flask import jsonify, request, session


def register_governance_routes(app):

    @app.route('/api/governance/request', methods=['POST'])
    def governance_submit_request():
        """Agent submits a policy change request.

        Body:
            agent_id (int): The requesting agent's ID.
            requested_changes (dict): {policy_id, field, current_value, requested_value}
            reason (str): Justification for the change.
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        agent_id = data.get('agent_id')
        requested_changes = data.get('requested_changes')
        reason = data.get('reason')

        if agent_id is None:
            return jsonify({'error': 'agent_id is required'}), 400
        if requested_changes is None:
            return jsonify({'error': 'requested_changes is required'}), 400
        if not reason or not str(reason).strip():
            return jsonify({'error': 'reason is required'}), 400

        from core.governance.requests import create_request

        pcr, error = create_request(
            workspace_id=user_id,
            agent_id=agent_id,
            requested_changes=requested_changes,
            reason=str(reason).strip(),
        )

        if error:
            return jsonify({'error': error}), 400

        return jsonify({
            'success': True,
            'request': pcr.to_dict(),
        }), 201

    @app.route('/api/governance/requests', methods=['GET'])
    def governance_list_requests():
        """List policy change requests for the workspace.

        Query params:
            status (str, optional): Filter by status.
            agent_id (int, optional): Filter by agent.
            limit (int, optional): Max results (default 50).
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        status_filter = request.args.get('status')
        agent_id_filter = request.args.get('agent_id', type=int)
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(limit, 1), 200)

        from core.governance.requests import get_requests

        results = get_requests(
            workspace_id=user_id,
            status=status_filter,
            agent_id=agent_id_filter,
            limit=limit,
        )

        return jsonify({
            'requests': [r.to_dict() for r in results],
            'count': len(results),
        })

    @app.route('/api/governance/pending', methods=['GET'])
    def governance_pending_requests():
        """List pending policy change requests for the workspace.

        Convenience endpoint for the approval UI.

        Query params:
            agent_id (int, optional): Filter by agent.
            limit (int, optional): Max results (default 50).
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        agent_id_filter = request.args.get('agent_id', type=int)
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(limit, 1), 200)

        from core.governance.requests import get_requests

        results = get_requests(
            workspace_id=user_id,
            status='pending',
            agent_id=agent_id_filter,
            limit=limit,
        )

        return jsonify({
            'requests': [r.to_dict() for r in results],
            'count': len(results),
        })

    # ------------------------------------------------------------------
    # Phase 2: Approval / Denial
    # ------------------------------------------------------------------

    @app.route('/api/governance/approve/<int:request_id>', methods=['POST'])
    def governance_approve_request(request_id):
        """Human approves a pending policy change request.

        Body:
            mode (str): 'one_time' or 'delegate'.
            delegation_params (dict, optional): Required when mode='delegate'.
                duration_minutes (int): Grant duration.
                max_spend_delta (str, optional): Max threshold increase.
                allowed_changes (dict, optional): Custom envelope.
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        mode = data.get('mode')
        if not mode:
            return jsonify({'error': 'mode is required (one_time or delegate)'}), 400

        delegation_params = data.get('delegation_params')

        from core.governance.approvals import approve_request

        result, error = approve_request(
            request_id=request_id,
            workspace_id=user_id,
            approver_id=user_id,
            mode=mode,
            delegation_params=delegation_params,
        )

        if error:
            # Distinguish boundary violations (403) from other errors (400)
            status_code = 403 if 'Boundary violation' in error else 400
            return jsonify({'error': error}), status_code

        return jsonify({'success': True, **result})

    @app.route('/api/governance/deny/<int:request_id>', methods=['POST'])
    def governance_deny_request(request_id):
        """Human denies a pending policy change request.

        Body:
            reason (str, optional): Denial reason.
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        reason = data.get('reason')

        from core.governance.approvals import deny_request

        result, error = deny_request(
            request_id=request_id,
            workspace_id=user_id,
            approver_id=user_id,
            reason=reason,
        )

        if error:
            return jsonify({'error': error}), 400

        return jsonify({'success': True, **result})

    # ------------------------------------------------------------------
    # Phase 3: Delegation Enforcement
    # ------------------------------------------------------------------

    @app.route('/api/governance/delegate/apply', methods=['POST'])
    def governance_delegate_apply():
        """Agent applies a policy change using a delegation grant.

        Body:
            grant_id (int): The delegation grant to use.
            agent_id (int): The agent applying the change.
            requested_change (dict): {policy_id, field, new_value}
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        grant_id = data.get('grant_id')
        agent_id = data.get('agent_id')
        requested_change = data.get('requested_change')

        if grant_id is None:
            return jsonify({'error': 'grant_id is required'}), 400
        if agent_id is None:
            return jsonify({'error': 'agent_id is required'}), 400
        if requested_change is None:
            return jsonify({'error': 'requested_change is required'}), 400

        from core.governance.delegation import apply_delegated_change

        result, error = apply_delegated_change(
            grant_id=grant_id,
            workspace_id=user_id,
            agent_id=agent_id,
            requested_change=requested_change,
        )

        if error:
            status_code = 403 if 'violation' in error.lower() else 400
            return jsonify({'error': error}), status_code

        return jsonify({'success': True, **result})

    @app.route('/api/governance/delegations', methods=['GET'])
    def governance_list_delegations():
        """List active delegation grants for the workspace.

        Query params:
            agent_id (int, optional): Filter by agent.
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        agent_id_filter = request.args.get('agent_id', type=int)

        from core.governance.delegation import get_active_grants

        grants = get_active_grants(
            workspace_id=user_id,
            agent_id=agent_id_filter,
        )

        return jsonify({
            'delegations': [g.to_dict() for g in grants],
            'count': len(grants),
        })

    @app.route('/api/governance/delegations/<int:grant_id>/revoke',
               methods=['POST'])
    def governance_revoke_delegation(grant_id):
        """Human revokes an active delegation grant."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        from core.governance.delegation import revoke_grant

        result, error = revoke_grant(
            grant_id=grant_id,
            workspace_id=user_id,
            revoker_id=user_id,
        )

        if error:
            return jsonify({'error': error}), 400

        return jsonify({'success': True, **result})

    @app.route('/api/governance/internal/expire', methods=['POST'])
    def governance_internal_expire():
        """Cron endpoint: expire stale requests and delegation grants."""
        # Auth: CRON_SECRET or ADMIN_PASSWORD
        auth_header = request.headers.get('Authorization', '')
        body = request.get_json(silent=True) or {}
        cron_secret = os.environ.get('CRON_SECRET', '')
        admin_password = os.environ.get('ADMIN_PASSWORD', '')

        authorized = False
        if cron_secret and auth_header == f'Bearer {cron_secret}':
            authorized = True
        elif admin_password and body.get('password') == admin_password:
            authorized = True

        if not authorized:
            return jsonify({'error': 'Unauthorized'}), 401

        from core.governance.requests import expire_stale_requests
        from core.governance.delegation import expire_grants

        requests_expired = expire_stale_requests()
        grants_expired = expire_grants()

        return jsonify({
            'success': True,
            'requests_expired': requests_expired,
            'grants_expired': grants_expired,
        })

    # ------------------------------------------------------------------
    # Phase 4: Rollback & Audit Query
    # ------------------------------------------------------------------

    @app.route('/api/governance/rollback/<int:audit_id>', methods=['POST'])
    def governance_rollback(audit_id):
        """Human rolls back a policy change to its pre-change state.

        The audit_id must reference a change_applied or change_rolled_back
        event. The policy is restored to the policy_before snapshot stored
        in that audit entry.
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        from core.governance.rollback import rollback_change

        result, error = rollback_change(
            audit_entry_id=audit_id,
            workspace_id=user_id,
            actor_id=user_id,
        )

        if error:
            status_code = 403 if 'boundary' in error.lower() else 400
            return jsonify({'error': error}), status_code

        return jsonify({'success': True, **result})

    @app.route('/api/governance/audit', methods=['GET'])
    def governance_audit_trail():
        """Query the governance audit trail for the workspace.

        Query params:
            event_type (str, optional): Filter by event type.
            agent_id (int, optional): Filter by agent.
            limit (int, optional): Max results (default 100).
        """
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        event_type = request.args.get('event_type')
        agent_id_filter = request.args.get('agent_id', type=int)
        limit = request.args.get('limit', 100, type=int)
        limit = min(max(limit, 1), 500)

        from core.governance.governance_audit import get_governance_trail

        entries = get_governance_trail(
            workspace_id=user_id,
            event_type=event_type,
            agent_id=agent_id_filter,
            limit=limit,
        )

        return jsonify({
            'audit_trail': [e.to_dict() for e in entries],
            'count': len(entries),
        })
