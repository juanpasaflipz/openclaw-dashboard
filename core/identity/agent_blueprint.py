"""
Blueprint CRUD, versioning, publishing, and cloning.

Blueprints follow a strict lifecycle: draft -> published -> archived.
Published blueprint versions are immutable — no UPDATE is ever issued.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from models import (
    db, AgentBlueprint, AgentBlueprintVersion, CapabilityBundle,
    blueprint_capabilities, BLUEPRINT_ROLE_TYPES, BLUEPRINT_STATUSES,
)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_blueprint(
    workspace_id: int,
    name: str,
    created_by: int,
    *,
    description: str | None = None,
    role_type: str = 'worker',
) -> AgentBlueprint:
    """Create a new blueprint in draft status.

    Args:
        workspace_id: The owning workspace (user_id).
        name: Human-readable blueprint name.
        created_by: The user creating this blueprint.
        description: Optional description.
        role_type: One of BLUEPRINT_ROLE_TYPES. Defaults to 'worker'.

    Returns:
        The created AgentBlueprint.

    Raises:
        ValueError: If role_type is invalid.
    """
    if role_type not in BLUEPRINT_ROLE_TYPES:
        raise ValueError(
            f'Invalid role_type {role_type!r}. '
            f'Must be one of: {sorted(BLUEPRINT_ROLE_TYPES)}'
        )

    bp = AgentBlueprint(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=name,
        description=description,
        role_type=role_type,
        status='draft',
        created_at=datetime.utcnow(),
        created_by=created_by,
    )
    db.session.add(bp)
    db.session.commit()
    return bp


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_blueprint(blueprint_id: str, workspace_id: int) -> AgentBlueprint | None:
    """Fetch a blueprint by ID, scoped to a workspace.

    Returns None if not found or if it belongs to a different workspace.
    """
    return AgentBlueprint.query.filter_by(
        id=blueprint_id, workspace_id=workspace_id,
    ).first()


def get_blueprint_version(
    blueprint_id: str,
    version: int,
    workspace_id: int | None = None,
) -> AgentBlueprintVersion | None:
    """Fetch a specific version of a blueprint.

    If workspace_id is provided, also validates workspace ownership.
    """
    q = AgentBlueprintVersion.query.filter_by(
        blueprint_id=blueprint_id, version=version,
    )
    if workspace_id is not None:
        q = q.join(AgentBlueprint).filter(
            AgentBlueprint.workspace_id == workspace_id,
        )
    return q.first()


# ---------------------------------------------------------------------------
# Update (draft only)
# ---------------------------------------------------------------------------

def update_draft_blueprint(
    blueprint_id: str,
    workspace_id: int,
    **fields,
) -> AgentBlueprint:
    """Update a draft blueprint's metadata.

    Only name, description, and role_type can be changed, and only while
    the blueprint is in draft status.

    Raises:
        ValueError: If blueprint is not in draft status or field is invalid.
        LookupError: If blueprint not found.
    """
    bp = get_blueprint(blueprint_id, workspace_id)
    if bp is None:
        raise LookupError(f'Blueprint {blueprint_id} not found in workspace {workspace_id}')
    if bp.status != 'draft':
        raise ValueError(f'Cannot update blueprint in {bp.status!r} status. Only drafts are mutable.')

    allowed_fields = {'name', 'description', 'role_type'}
    for key, value in fields.items():
        if key not in allowed_fields:
            raise ValueError(f'Cannot update field {key!r}. Allowed: {sorted(allowed_fields)}')
        if key == 'role_type' and value not in BLUEPRINT_ROLE_TYPES:
            raise ValueError(
                f'Invalid role_type {value!r}. '
                f'Must be one of: {sorted(BLUEPRINT_ROLE_TYPES)}'
            )
        setattr(bp, key, value)

    db.session.commit()
    return bp


# ---------------------------------------------------------------------------
# Publish (draft -> published, creates a new version)
# ---------------------------------------------------------------------------

def publish_blueprint(
    blueprint_id: str,
    workspace_id: int,
    published_by: int,
    *,
    allowed_models: list | None = None,
    allowed_tools: list | None = None,
    default_risk_profile: dict | None = None,
    hierarchy_defaults: dict | None = None,
    memory_strategy: dict | None = None,
    escalation_rules: dict | None = None,
    llm_defaults: dict | None = None,
    identity_defaults: dict | None = None,
    override_policy: dict | None = None,
    changelog: str | None = None,
    capability_ids: list[int] | None = None,
) -> AgentBlueprintVersion:
    """Publish a new immutable version of the blueprint.

    If the blueprint is in draft status, it transitions to published.
    If already published, a new version is appended (the blueprint stays published).

    Args:
        blueprint_id: The blueprint to publish.
        workspace_id: Workspace scope.
        published_by: The user publishing this version.
        allowed_models: List of allowed model identifiers.
        allowed_tools: List of allowed tool names.
        default_risk_profile: Risk policy defaults for instantiated agents.
        hierarchy_defaults: Role/hierarchy defaults.
        memory_strategy: Memory configuration.
        escalation_rules: Escalation behavior.
        llm_defaults: Default LLM configuration.
        identity_defaults: Default identity/personality config.
        override_policy: Which fields can be overridden at instance level.
        changelog: Human-readable description of changes.
        capability_ids: IDs of CapabilityBundles to attach.

    Returns:
        The newly created AgentBlueprintVersion.

    Raises:
        LookupError: If blueprint not found.
        ValueError: If blueprint is archived, or capability not found.
    """
    bp = get_blueprint(blueprint_id, workspace_id)
    if bp is None:
        raise LookupError(f'Blueprint {blueprint_id} not found in workspace {workspace_id}')
    if bp.status == 'archived':
        raise ValueError('Cannot publish an archived blueprint')

    next_version = bp.latest_version + 1

    ver = AgentBlueprintVersion(
        blueprint_id=blueprint_id,
        version=next_version,
        allowed_models=allowed_models,
        allowed_tools=allowed_tools,
        default_risk_profile=default_risk_profile,
        hierarchy_defaults=hierarchy_defaults,
        memory_strategy=memory_strategy,
        escalation_rules=escalation_rules,
        llm_defaults=llm_defaults,
        identity_defaults=identity_defaults,
        override_policy=override_policy,
        published_at=datetime.utcnow(),
        published_by=published_by,
        changelog=changelog,
    )
    db.session.add(ver)

    # Attach capability bundles if specified
    if capability_ids:
        for cap_id in capability_ids:
            cap = CapabilityBundle.query.filter_by(
                id=cap_id, workspace_id=workspace_id,
            ).first()
            if cap is None:
                db.session.rollback()
                raise ValueError(
                    f'CapabilityBundle {cap_id} not found in workspace {workspace_id}'
                )
            ver.capabilities.append(cap)

    # Transition draft -> published
    if bp.status == 'draft':
        bp.status = 'published'

    # Governance audit trail
    try:
        from core.governance.governance_audit import log_governance_event
        log_governance_event(
            workspace_id=workspace_id,
            event_type='blueprint_published',
            details={
                'blueprint_id': blueprint_id,
                'blueprint_name': bp.name,
                'version': next_version,
                'role_type': bp.role_type,
                'has_risk_profile': bool(default_risk_profile),
                'capability_count': len(capability_ids) if capability_ids else 0,
            },
            actor_id=published_by,
        )
    except Exception:
        pass  # never block publish on audit failures

    db.session.commit()
    return ver


# ---------------------------------------------------------------------------
# Archive (published -> archived)
# ---------------------------------------------------------------------------

def archive_blueprint(blueprint_id: str, workspace_id: int) -> AgentBlueprint:
    """Archive a blueprint. Existing instances are unaffected.

    Raises:
        LookupError: If blueprint not found.
        ValueError: If blueprint is in draft status (must publish first or delete).
    """
    bp = get_blueprint(blueprint_id, workspace_id)
    if bp is None:
        raise LookupError(f'Blueprint {blueprint_id} not found in workspace {workspace_id}')
    if bp.status == 'draft':
        raise ValueError('Cannot archive a draft blueprint. Publish it first or delete it.')
    if bp.status == 'archived':
        return bp  # idempotent

    bp.status = 'archived'
    db.session.commit()
    return bp


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

def clone_blueprint(
    source_blueprint_id: str,
    source_version: int,
    workspace_id: int,
    created_by: int,
    *,
    name: str | None = None,
) -> AgentBlueprint:
    """Clone a blueprint version into a new draft blueprint.

    The new blueprint gets a fresh ID and starts in draft status with no versions.
    All configuration from the source version is returned for use in the first
    publish of the clone.

    Args:
        source_blueprint_id: The blueprint to clone from.
        source_version: Which version to clone.
        workspace_id: Must match the source blueprint's workspace.
        created_by: The user creating the clone.
        name: Optional name override. Defaults to "{source_name} (Clone)".

    Returns:
        The new draft AgentBlueprint.

    Raises:
        LookupError: If source blueprint or version not found.
    """
    source_bp = get_blueprint(source_blueprint_id, workspace_id)
    if source_bp is None:
        raise LookupError(
            f'Blueprint {source_blueprint_id} not found in workspace {workspace_id}'
        )

    source_ver = get_blueprint_version(source_blueprint_id, source_version, workspace_id)
    if source_ver is None:
        raise LookupError(
            f'Version {source_version} not found for blueprint {source_blueprint_id}'
        )

    clone_name = name or f'{source_bp.name} (Clone)'

    new_bp = AgentBlueprint(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=clone_name,
        description=source_bp.description,
        role_type=source_bp.role_type,
        status='draft',
        created_at=datetime.utcnow(),
        created_by=created_by,
    )
    db.session.add(new_bp)
    db.session.commit()

    return new_bp
