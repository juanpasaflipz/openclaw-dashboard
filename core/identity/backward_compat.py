"""
Backward compatibility — implicit blueprint generation for legacy agents.

A legacy agent is one with no AgentInstance binding. These agents operate
unrestricted (no capability boundaries). This module provides opt-in
migration that wraps a legacy agent in a blueprint without changing its
runtime behavior:

    - allowed_tools = ["*"]  (unrestricted)
    - allowed_models = ["*"] (unrestricted)
    - override_policy = {"allowed_overrides": ["*"]}  (fully open)
    - default_risk_profile = {} (no risk seeding — existing policies preserved)
    - hierarchy_defaults mirrors existing AgentRole if present

Migration is NEVER automatic. It is triggered by explicit user action via
the API or by a workspace-wide migration script.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from models import (
    db, Agent, AgentBlueprint, AgentBlueprintVersion,
    AgentInstance, AgentRole,
    BLUEPRINT_ROLE_TYPES,
)
from core.identity.agent_capabilities import resolve_capabilities


# ---------------------------------------------------------------------------
# Role inference
# ---------------------------------------------------------------------------

# Maps AgentRole.role → blueprint role_type
_COLLAB_ROLE_TO_BLUEPRINT = {
    'supervisor': 'supervisor',
    'worker': 'worker',
    'specialist': 'researcher',
}


def _infer_role_type(agent: Agent) -> str:
    """Infer a blueprint role_type from the agent's current state.

    Priority:
    1. Existing AgentRole → map to blueprint role_type.
    2. identity_config.role if it matches BLUEPRINT_ROLE_TYPES.
    3. Default to 'worker'.
    """
    # Check existing collaboration role
    existing_role = AgentRole.query.filter_by(
        workspace_id=agent.user_id, agent_id=agent.id,
    ).first()
    if existing_role:
        mapped = _COLLAB_ROLE_TO_BLUEPRINT.get(existing_role.role)
        if mapped and mapped in BLUEPRINT_ROLE_TYPES:
            return mapped

    # Check identity_config
    identity = agent.identity_config or {}
    if isinstance(identity, dict):
        config_role = identity.get('role', '')
        if config_role in BLUEPRINT_ROLE_TYPES:
            return config_role

    return 'worker'


def _capture_hierarchy_defaults(agent: Agent) -> dict | None:
    """Capture the agent's current AgentRole as hierarchy_defaults.

    Returns None if the agent has no role assignment, so that
    _seed_agent_role will not overwrite anything.
    """
    existing_role = AgentRole.query.filter_by(
        workspace_id=agent.user_id, agent_id=agent.id,
    ).first()
    if existing_role is None:
        return None

    return {
        'role': existing_role.role,
        'can_assign_to_peers': existing_role.can_assign_to_peers,
        'can_escalate_to_supervisor': existing_role.can_escalate_to_supervisor,
    }


# ---------------------------------------------------------------------------
# Single agent conversion
# ---------------------------------------------------------------------------

def generate_implicit_blueprint(
    agent: Agent,
    created_by: int | None = None,
) -> tuple[AgentBlueprint, AgentBlueprintVersion, AgentInstance]:
    """Generate an implicit blueprint for a legacy agent.

    Creates a published blueprint with unrestricted capabilities that
    exactly preserves the agent's current runtime behavior. Existing
    risk policies and collaboration roles are NOT modified.

    Args:
        agent: The legacy agent to convert.
        created_by: The user performing the conversion. Defaults to agent owner.

    Returns:
        (blueprint, version, instance) tuple.

    Raises:
        ValueError: If the agent already has an instance binding.
    """
    actor = created_by or agent.user_id

    # Guard: already managed
    existing = AgentInstance.query.filter_by(agent_id=agent.id).first()
    if existing is not None:
        raise ValueError(
            f'Agent {agent.id} already has a blueprint binding '
            f'(blueprint={existing.blueprint_id} v{existing.blueprint_version}). '
            f'Cannot generate implicit blueprint.'
        )

    role_type = _infer_role_type(agent)
    hierarchy = _capture_hierarchy_defaults(agent)

    # 1. Create blueprint (directly published — skip draft)
    bp = AgentBlueprint(
        id=str(uuid.uuid4()),
        workspace_id=agent.user_id,
        name=f'{agent.name} (Auto)',
        description=f'Auto-generated blueprint for legacy agent "{agent.name}"',
        role_type=role_type,
        status='published',
        created_at=datetime.utcnow(),
        created_by=actor,
    )
    db.session.add(bp)

    # 2. Create version 1 — wildcards preserve unrestricted behavior
    ver = AgentBlueprintVersion(
        blueprint_id=bp.id,
        version=1,
        allowed_models=['*'],
        allowed_tools=['*'],
        default_risk_profile={},
        hierarchy_defaults=hierarchy,
        llm_defaults=agent.llm_config or {},
        identity_defaults=agent.identity_config or {},
        override_policy={'allowed_overrides': ['*']},
        published_at=datetime.utcnow(),
        published_by=actor,
        changelog='Auto-generated from legacy agent configuration',
    )
    db.session.add(ver)
    # Flush so resolve_capabilities can read the version
    db.session.flush()

    # 3. Resolve capabilities (will produce ["*"] wildcards)
    snapshot = resolve_capabilities(ver)

    # 4. Create instance binding — directly, without instantiate_agent()
    #    to avoid risk policy re-seeding and role overwriting.
    instance = AgentInstance(
        agent_id=agent.id,
        blueprint_id=bp.id,
        blueprint_version=1,
        workspace_id=agent.user_id,
        overrides=None,
        policy_snapshot=snapshot,
        instantiated_at=datetime.utcnow(),
        instantiated_by=actor,
    )
    db.session.add(instance)

    # 5. Governance audit trail
    try:
        from core.governance.governance_audit import log_governance_event
        log_governance_event(
            workspace_id=agent.user_id,
            event_type='instance_created',
            details={
                'blueprint_id': bp.id,
                'blueprint_version': 1,
                'implicit': True,
                'source': 'backward_compat',
                'agent_name': agent.name,
            },
            agent_id=agent.id,
            actor_id=actor,
        )
    except Exception:
        pass

    db.session.commit()
    return bp, ver, instance


# ---------------------------------------------------------------------------
# Workspace-wide migration
# ---------------------------------------------------------------------------

def migrate_workspace_agents(
    workspace_id: int,
    created_by: int | None = None,
) -> list[dict]:
    """Convert all legacy agents in a workspace to blueprint-managed.

    Agents that already have an AgentInstance binding are skipped.

    Args:
        workspace_id: The workspace to migrate.
        created_by: The user performing the migration. Defaults to workspace owner.

    Returns:
        List of dicts with migration results per agent:
        [{'agent_id': int, 'agent_name': str, 'blueprint_id': str, 'status': 'converted'|'skipped'|'error', ...}]
    """
    actor = created_by or workspace_id
    agents = Agent.query.filter_by(user_id=workspace_id).all()

    results = []
    for agent in agents:
        existing = AgentInstance.query.filter_by(agent_id=agent.id).first()
        if existing is not None:
            results.append({
                'agent_id': agent.id,
                'agent_name': agent.name,
                'status': 'skipped',
                'reason': 'already blueprint-managed',
                'blueprint_id': existing.blueprint_id,
            })
            continue

        try:
            bp, ver, instance = generate_implicit_blueprint(agent, actor)
            results.append({
                'agent_id': agent.id,
                'agent_name': agent.name,
                'status': 'converted',
                'blueprint_id': bp.id,
            })
        except Exception as e:
            results.append({
                'agent_id': agent.id,
                'agent_name': agent.name,
                'status': 'error',
                'error': str(e)[:300],
            })

    return results
