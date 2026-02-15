"""
Agent instantiation from blueprints.

Creates the binding between an Agent and a specific blueprint version,
validates overrides, snapshots the resolved capability set, and seeds
runtime artefacts (risk policies, collaboration roles, governance audit).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from models import db, Agent, AgentBlueprint, AgentBlueprintVersion, AgentInstance
from core.identity.agent_blueprint import get_blueprint, get_blueprint_version
from core.identity.agent_capabilities import resolve_capabilities


# ---------------------------------------------------------------------------
# Override validation
# ---------------------------------------------------------------------------

def validate_overrides(
    overrides: dict | None,
    override_policy: dict | None,
) -> tuple[bool, str | None]:
    """Validate that proposed overrides are allowed by the override policy.

    Args:
        overrides: The override dict to validate. Keys are field names.
        override_policy: The blueprint version's override_policy.
            Expected shape: {allowed_overrides: [...], denied_overrides: [...]}

    Returns:
        (True, None) if valid.
        (False, error_message) if any override is denied.
    """
    if not overrides:
        return True, None

    if not override_policy:
        # No override policy means no overrides allowed
        return False, 'No override policy defined — overrides are not permitted'

    allowed = set(override_policy.get('allowed_overrides', []))
    denied = set(override_policy.get('denied_overrides', []))

    # Wildcard: allow everything
    if '*' in allowed:
        # Still check denied list
        for key in overrides:
            if key in denied:
                return False, f'Override for {key!r} is explicitly denied'
        return True, None

    # Check each override key
    for key in overrides:
        if key in denied:
            return False, f'Override for {key!r} is explicitly denied'
        if key not in allowed:
            return False, (
                f'Override for {key!r} is not in allowed_overrides. '
                f'Allowed: {sorted(allowed)}'
            )

    return True, None


# ---------------------------------------------------------------------------
# Runtime artefact seeding (risk policies, collaboration roles)
# ---------------------------------------------------------------------------

# Maps blueprint role_type -> AgentRole.role
_ROLE_TYPE_TO_COLLAB_ROLE = {
    'supervisor': 'supervisor',
    'researcher': 'specialist',
    'executor': 'worker',
    'worker': 'worker',
    'autonomous': 'worker',
}


def _seed_risk_policies(
    workspace_id: int,
    agent_id: int,
    risk_profile: dict | None,
) -> list:
    """Create RiskPolicy rows from a blueprint's default_risk_profile.

    Uses INSERT-or-UPDATE semantics: if a policy for the same
    (workspace, agent, policy_type) already exists it is updated.

    Returns the list of RiskPolicy objects created or updated.
    """
    if not risk_profile:
        return []

    from models import RiskPolicy

    seeded = []
    for policy_type in ('daily_spend_cap', 'error_rate_cap', 'token_rate_cap'):
        threshold = risk_profile.get(policy_type)
        if threshold is None:
            continue

        action_type = risk_profile.get('action_type', 'alert_only')
        if action_type not in RiskPolicy.VALID_ACTION_TYPES:
            action_type = 'alert_only'

        cooldown = risk_profile.get('cooldown_minutes', 360)

        existing = RiskPolicy.query.filter_by(
            workspace_id=workspace_id,
            agent_id=agent_id,
            policy_type=policy_type,
        ).first()

        if existing:
            existing.threshold_value = Decimal(str(threshold))
            existing.action_type = action_type
            existing.cooldown_minutes = cooldown
            existing.is_enabled = True
            seeded.append(existing)
        else:
            policy = RiskPolicy(
                workspace_id=workspace_id,
                agent_id=agent_id,
                policy_type=policy_type,
                threshold_value=Decimal(str(threshold)),
                action_type=action_type,
                cooldown_minutes=cooldown,
                is_enabled=True,
            )
            db.session.add(policy)
            seeded.append(policy)

    return seeded


def _seed_agent_role(
    workspace_id: int,
    agent_id: int,
    hierarchy_defaults: dict | None,
    blueprint_role_type: str,
) -> None:
    """Create or update an AgentRole from blueprint hierarchy defaults.

    The role is determined by:
    1. hierarchy_defaults.role (explicit), or
    2. mapping from blueprint role_type via _ROLE_TYPE_TO_COLLAB_ROLE.
    """
    from models import AgentRole

    if hierarchy_defaults:
        role = hierarchy_defaults.get('role')
        can_assign = hierarchy_defaults.get('can_assign_to_peers', False)
        can_escalate = hierarchy_defaults.get('can_escalate_to_supervisor', True)
    else:
        role = None
        can_assign = False
        can_escalate = True

    # Fall back to mapping from blueprint role_type
    if not role or role not in AgentRole.VALID_ROLES:
        role = _ROLE_TYPE_TO_COLLAB_ROLE.get(blueprint_role_type, 'worker')

    existing = AgentRole.query.filter_by(
        workspace_id=workspace_id,
        agent_id=agent_id,
    ).first()

    if existing:
        existing.role = role
        existing.can_assign_to_peers = can_assign
        existing.can_escalate_to_supervisor = can_escalate
    else:
        agent_role = AgentRole(
            workspace_id=workspace_id,
            agent_id=agent_id,
            role=role,
            can_assign_to_peers=can_assign,
            can_escalate_to_supervisor=can_escalate,
        )
        db.session.add(agent_role)


def _log_instance_event(
    workspace_id: int,
    agent_id: int,
    event_type: str,
    details: dict,
    actor_id: int | None = None,
) -> None:
    """Best-effort governance audit log for blueprint instance events."""
    try:
        from core.governance.governance_audit import log_governance_event
        log_governance_event(
            workspace_id=workspace_id,
            event_type=event_type,
            details=details,
            agent_id=agent_id,
            actor_id=actor_id,
        )
    except Exception:
        pass  # never block instantiation on audit failures


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

def instantiate_agent(
    agent_id: int,
    blueprint_id: str,
    version: int,
    workspace_id: int,
    instantiated_by: int,
    *,
    overrides: dict | None = None,
) -> AgentInstance:
    """Create an AgentInstance binding an Agent to a blueprint version.

    This:
    1. Validates the blueprint exists and is published.
    2. Validates the version exists.
    3. Validates overrides against the version's override_policy.
    4. Resolves capabilities and stores as policy_snapshot.
    5. Creates the AgentInstance row.

    Args:
        agent_id: The agent to bind.
        blueprint_id: The blueprint to bind to.
        version: The specific version to pin.
        workspace_id: Workspace scope (must match all entities).
        instantiated_by: The user performing the instantiation.
        overrides: Optional constrained overrides.

    Returns:
        The created AgentInstance.

    Raises:
        LookupError: If agent, blueprint, or version not found.
        ValueError: If blueprint not published, workspace mismatch,
            agent already has an instance, or overrides are invalid.
    """
    # Validate agent
    agent = Agent.query.filter_by(id=agent_id, user_id=workspace_id).first()
    if agent is None:
        raise LookupError(f'Agent {agent_id} not found in workspace {workspace_id}')

    # Check for existing instance
    existing = AgentInstance.query.filter_by(agent_id=agent_id).first()
    if existing is not None:
        raise ValueError(
            f'Agent {agent_id} already has an instance binding '
            f'(blueprint={existing.blueprint_id} v{existing.blueprint_version}). '
            f'Remove the existing instance first.'
        )

    # Validate blueprint
    bp = get_blueprint(blueprint_id, workspace_id)
    if bp is None:
        raise LookupError(f'Blueprint {blueprint_id} not found in workspace {workspace_id}')
    if bp.status != 'published':
        raise ValueError(
            f'Blueprint {blueprint_id} is in {bp.status!r} status. '
            f'Only published blueprints can be instantiated.'
        )

    # Validate version
    ver = get_blueprint_version(blueprint_id, version, workspace_id)
    if ver is None:
        raise LookupError(
            f'Version {version} not found for blueprint {blueprint_id}'
        )

    # Validate overrides
    if overrides:
        valid, error = validate_overrides(overrides, ver.override_policy)
        if not valid:
            raise ValueError(f'Override validation failed: {error}')

    # Resolve capabilities and create snapshot
    snapshot = resolve_capabilities(ver)

    instance = AgentInstance(
        agent_id=agent_id,
        blueprint_id=blueprint_id,
        blueprint_version=version,
        workspace_id=workspace_id,
        overrides=overrides,
        policy_snapshot=snapshot,
        instantiated_at=datetime.utcnow(),
        instantiated_by=instantiated_by,
    )
    db.session.add(instance)

    # Seed runtime artefacts from blueprint defaults
    _seed_risk_policies(workspace_id, agent_id, ver.default_risk_profile)
    _seed_agent_role(workspace_id, agent_id, ver.hierarchy_defaults, bp.role_type)

    # Governance audit trail
    _log_instance_event(
        workspace_id=workspace_id,
        agent_id=agent_id,
        event_type='instance_created',
        details={
            'blueprint_id': blueprint_id,
            'blueprint_version': version,
            'has_overrides': bool(overrides),
            'risk_policies_seeded': bool(ver.default_risk_profile),
            'role_seeded': True,
        },
        actor_id=instantiated_by,
    )

    db.session.commit()
    return instance


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_agent_instance(agent_id: int) -> AgentInstance | None:
    """Fetch the instance binding for an agent, or None if legacy."""
    return AgentInstance.query.filter_by(agent_id=agent_id).first()


# ---------------------------------------------------------------------------
# Refresh policy snapshot
# ---------------------------------------------------------------------------

def refresh_instance_policy(
    agent_id: int,
    workspace_id: int,
    *,
    new_version: int | None = None,
    new_overrides: dict | None = None,
) -> AgentInstance:
    """Refresh an agent instance's policy snapshot.

    Optionally upgrade to a new blueprint version and/or update overrides.

    Args:
        agent_id: The agent whose instance to refresh.
        workspace_id: Workspace scope.
        new_version: If provided, upgrade to this version.
        new_overrides: If provided, replace overrides (validated).

    Returns:
        The updated AgentInstance.

    Raises:
        LookupError: If instance, blueprint, or version not found.
        ValueError: If overrides are invalid.
    """
    instance = AgentInstance.query.filter_by(
        agent_id=agent_id, workspace_id=workspace_id,
    ).first()
    if instance is None:
        raise LookupError(f'No instance found for agent {agent_id} in workspace {workspace_id}')

    target_version = new_version or instance.blueprint_version

    ver = get_blueprint_version(instance.blueprint_id, target_version, workspace_id)
    if ver is None:
        raise LookupError(
            f'Version {target_version} not found for blueprint {instance.blueprint_id}'
        )

    # Validate overrides
    overrides = new_overrides if new_overrides is not None else instance.overrides
    if overrides:
        valid, error = validate_overrides(overrides, ver.override_policy)
        if not valid:
            raise ValueError(f'Override validation failed: {error}')

    # Re-resolve and snapshot
    snapshot = resolve_capabilities(ver)

    instance.blueprint_version = target_version
    instance.overrides = overrides
    instance.policy_snapshot = snapshot
    instance.last_policy_refresh = datetime.utcnow()

    # Re-seed risk policies and role from the (possibly new) version
    bp = get_blueprint(instance.blueprint_id, workspace_id)
    _seed_risk_policies(workspace_id, instance.agent_id, ver.default_risk_profile)
    if bp:
        _seed_agent_role(
            workspace_id, instance.agent_id,
            ver.hierarchy_defaults, bp.role_type,
        )

    _log_instance_event(
        workspace_id=workspace_id,
        agent_id=instance.agent_id,
        event_type='instance_refreshed',
        details={
            'blueprint_id': instance.blueprint_id,
            'blueprint_version': target_version,
            'has_overrides': bool(overrides),
            'version_changed': new_version is not None,
        },
    )

    db.session.commit()
    return instance


# ---------------------------------------------------------------------------
# Remove instance binding
# ---------------------------------------------------------------------------

def remove_agent_instance(agent_id: int, workspace_id: int) -> bool:
    """Remove an agent's instance binding, returning it to legacy mode.

    Returns True if an instance was removed, False if none existed.
    """
    instance = AgentInstance.query.filter_by(
        agent_id=agent_id, workspace_id=workspace_id,
    ).first()
    if instance is None:
        return False

    _log_instance_event(
        workspace_id=workspace_id,
        agent_id=agent_id,
        event_type='instance_removed',
        details={
            'blueprint_id': instance.blueprint_id,
            'blueprint_version': instance.blueprint_version,
        },
    )

    db.session.delete(instance)
    db.session.commit()
    return True
