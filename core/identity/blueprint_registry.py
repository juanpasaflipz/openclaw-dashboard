"""
Blueprint registry — query interface for listing and searching blueprints.

All queries are workspace-scoped.
"""
from __future__ import annotations

from models import AgentBlueprint, AgentBlueprintVersion


def list_blueprints(
    workspace_id: int,
    *,
    status: str | None = None,
    role_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentBlueprint]:
    """List blueprints for a workspace with optional filtering.

    Args:
        workspace_id: The workspace scope.
        status: Filter by status (draft, published, archived).
        role_type: Filter by role_type.
        limit: Max results. Default 50.
        offset: Pagination offset. Default 0.

    Returns:
        List of AgentBlueprint instances.
    """
    q = AgentBlueprint.query.filter_by(workspace_id=workspace_id)

    if status is not None:
        q = q.filter(AgentBlueprint.status == status)
    if role_type is not None:
        q = q.filter(AgentBlueprint.role_type == role_type)

    return (
        q.order_by(AgentBlueprint.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def list_blueprint_versions(
    blueprint_id: str,
    workspace_id: int,
    *,
    limit: int = 50,
) -> list[AgentBlueprintVersion]:
    """List all versions of a blueprint, ordered by version number.

    Args:
        blueprint_id: The blueprint to list versions for.
        workspace_id: Workspace scope.
        limit: Max results. Default 50.

    Returns:
        List of AgentBlueprintVersion instances.
    """
    return (
        AgentBlueprintVersion.query
        .join(AgentBlueprint)
        .filter(
            AgentBlueprintVersion.blueprint_id == blueprint_id,
            AgentBlueprint.workspace_id == workspace_id,
        )
        .order_by(AgentBlueprintVersion.version.desc())
        .limit(limit)
        .all()
    )


def count_blueprints(workspace_id: int, *, status: str | None = None) -> int:
    """Count blueprints in a workspace.

    Args:
        workspace_id: The workspace scope.
        status: Optional status filter.

    Returns:
        Count of matching blueprints.
    """
    q = AgentBlueprint.query.filter_by(workspace_id=workspace_id)
    if status is not None:
        q = q.filter(AgentBlueprint.status == status)
    return q.count()
