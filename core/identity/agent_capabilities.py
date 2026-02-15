"""
CapabilityBundle CRUD and capability resolution.

Capabilities are named permission sets. When attached to a blueprint version,
they define what tools and models an agent can use.

Resolution algorithm:
    - tool_set: union across all bundles (additive)
    - model_constraints.allowed_providers: intersection (restrictive)
    - risk_constraints: minimum values (most conservative)
    - Blueprint-level allowed_tools/allowed_models act as a ceiling
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from models import db, CapabilityBundle, AgentBlueprintVersion


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_capability_bundle(
    workspace_id: int,
    name: str,
    *,
    description: str | None = None,
    tool_set: list[str] | None = None,
    model_constraints: dict | None = None,
    risk_constraints: dict | None = None,
) -> CapabilityBundle:
    """Create a new capability bundle in the workspace.

    Args:
        workspace_id: The owning workspace.
        name: Unique name within the workspace.
        description: Optional description.
        tool_set: List of tool names this capability grants.
        model_constraints: Model access constraints.
        risk_constraints: Risk limit constraints.

    Returns:
        The created CapabilityBundle.

    Raises:
        ValueError: If a bundle with this name already exists in the workspace.
    """
    existing = CapabilityBundle.query.filter_by(
        workspace_id=workspace_id, name=name,
    ).first()
    if existing:
        raise ValueError(
            f'CapabilityBundle {name!r} already exists in workspace {workspace_id}'
        )

    bundle = CapabilityBundle(
        workspace_id=workspace_id,
        name=name,
        description=description,
        tool_set=tool_set,
        model_constraints=model_constraints,
        risk_constraints=risk_constraints,
        created_at=datetime.utcnow(),
    )
    db.session.add(bundle)
    db.session.commit()
    return bundle


def get_capability_bundle(
    bundle_id: int,
    workspace_id: int,
) -> CapabilityBundle | None:
    """Fetch a capability bundle by ID, scoped to a workspace."""
    return CapabilityBundle.query.filter_by(
        id=bundle_id, workspace_id=workspace_id,
    ).first()


def update_capability_bundle(
    bundle_id: int,
    workspace_id: int,
    **fields,
) -> CapabilityBundle:
    """Update a capability bundle.

    System bundles (is_system=True) cannot be modified.

    Raises:
        LookupError: If bundle not found.
        ValueError: If bundle is a system bundle, or field is invalid.
    """
    bundle = get_capability_bundle(bundle_id, workspace_id)
    if bundle is None:
        raise LookupError(f'CapabilityBundle {bundle_id} not found in workspace {workspace_id}')
    if bundle.is_system:
        raise ValueError('Cannot modify a system capability bundle')

    allowed_fields = {'name', 'description', 'tool_set', 'model_constraints', 'risk_constraints'}
    for key, value in fields.items():
        if key not in allowed_fields:
            raise ValueError(f'Cannot update field {key!r}. Allowed: {sorted(allowed_fields)}')
        if key == 'name' and value != bundle.name:
            # Check uniqueness
            existing = CapabilityBundle.query.filter_by(
                workspace_id=workspace_id, name=value,
            ).first()
            if existing:
                raise ValueError(f'CapabilityBundle {value!r} already exists in workspace {workspace_id}')
        setattr(bundle, key, value)

    db.session.commit()
    return bundle


def list_capability_bundles(workspace_id: int) -> list[CapabilityBundle]:
    """List all capability bundles for a workspace."""
    return CapabilityBundle.query.filter_by(
        workspace_id=workspace_id,
    ).order_by(CapabilityBundle.name).all()


# ---------------------------------------------------------------------------
# Attach capabilities to a blueprint version
# ---------------------------------------------------------------------------

def attach_capabilities(
    version_id: int,
    capability_ids: list[int],
    workspace_id: int,
) -> AgentBlueprintVersion:
    """Attach capability bundles to a blueprint version.

    This is typically called during publish_blueprint, but can also be
    used to set up capabilities on an already-created version (before any
    instances reference it).

    Raises:
        LookupError: If version or capability not found.
    """
    ver = AgentBlueprintVersion.query.get(version_id)
    if ver is None:
        raise LookupError(f'BlueprintVersion {version_id} not found')

    for cap_id in capability_ids:
        cap = CapabilityBundle.query.filter_by(
            id=cap_id, workspace_id=workspace_id,
        ).first()
        if cap is None:
            raise LookupError(
                f'CapabilityBundle {cap_id} not found in workspace {workspace_id}'
            )
        if cap not in ver.capabilities:
            ver.capabilities.append(cap)

    db.session.commit()
    return ver


# ---------------------------------------------------------------------------
# Capability resolution
# ---------------------------------------------------------------------------

def resolve_capabilities(version: AgentBlueprintVersion) -> dict:
    """Resolve the effective capability set for a blueprint version.

    Algorithm:
        1. Start with blueprint-level allowed_tools and allowed_models.
        2. For each attached CapabilityBundle:
           - tool_set: union across bundles (additive)
           - model_constraints.allowed_providers: intersection (restrictive)
           - risk_constraints: minimum values (most conservative)
        3. Blueprint-level lists act as a ceiling (cap the union).

    Returns:
        A dict with:
            - allowed_tools: list[str] or ["*"] for unrestricted
            - allowed_models: list[str] or ["*"] for unrestricted
            - risk_profile: dict with merged risk constraints
            - llm_defaults: dict
            - identity_defaults: dict
    """
    bp_tools = version.allowed_tools or []
    bp_models = version.allowed_models or []
    bp_risk = version.default_risk_profile or {}

    bundles = version.capabilities or []

    if not bundles:
        # No capability bundles — use blueprint-level values directly
        return {
            'allowed_tools': bp_tools if bp_tools else ['*'],
            'allowed_models': bp_models if bp_models else ['*'],
            'risk_profile': bp_risk,
            'llm_defaults': version.llm_defaults or {},
            'identity_defaults': version.identity_defaults or {},
        }

    # Resolve tool_set: union across bundles
    resolved_tools: set[str] = set()
    for bundle in bundles:
        if bundle.tool_set:
            resolved_tools.update(bundle.tool_set)

    # Apply blueprint ceiling
    if bp_tools and '*' not in bp_tools:
        bp_tools_set = set(bp_tools)
        resolved_tools = resolved_tools & bp_tools_set
    # If bp_tools is empty or ["*"], the bundle union is the final set

    # Resolve model_constraints.allowed_providers: intersection
    resolved_providers: set[str] | None = None
    for bundle in bundles:
        mc = bundle.model_constraints or {}
        providers = mc.get('allowed_providers')
        if providers:
            provider_set = set(providers)
            if resolved_providers is None:
                resolved_providers = provider_set
            else:
                resolved_providers = resolved_providers & provider_set

    # Apply blueprint ceiling for models
    if resolved_providers is not None and bp_models and '*' not in bp_models:
        bp_models_set = set(bp_models)
        resolved_models = sorted(resolved_providers & bp_models_set)
    elif resolved_providers is not None:
        resolved_models = sorted(resolved_providers)
    elif bp_models:
        resolved_models = bp_models
    else:
        resolved_models = ['*']

    # Resolve risk_constraints: minimum values (most conservative)
    merged_risk = dict(bp_risk)
    for bundle in bundles:
        rc = bundle.risk_constraints or {}
        for key, value in rc.items():
            if key in merged_risk:
                try:
                    merged_risk[key] = float(min(Decimal(str(merged_risk[key])),
                                                  Decimal(str(value))))
                except (TypeError, ValueError):
                    pass  # non-numeric risk constraint, keep blueprint value
            else:
                merged_risk[key] = value

    return {
        'allowed_tools': sorted(resolved_tools) if resolved_tools else ['*'],
        'allowed_models': resolved_models if resolved_models else ['*'],
        'risk_profile': merged_risk,
        'llm_defaults': version.llm_defaults or {},
        'identity_defaults': version.identity_defaults or {},
    }
