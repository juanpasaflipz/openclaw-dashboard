"""
Workspace isolation — query scoping helpers.

In v1, workspace_id == user_id. This module provides a single place
to enforce isolation, making future multi-tenant refactoring trivial.

Tier enforcement is delegated to tier_enforcement.py but re-exported here
for convenience.
"""


def get_workspace_id(user_id):
    """Map user_id to workspace_id. In v1, they are the same."""
    return user_id


def scope_query(query, model_class, user_id):
    """
    Apply workspace scoping to a SQLAlchemy query.
    Requires model_class to have a user_id column.
    """
    workspace_id = get_workspace_id(user_id)
    return query.filter(model_class.user_id == workspace_id)


def verify_agent_ownership(agent_id, user_id):
    """Verify that an agent belongs to the user's workspace. Returns Agent or None."""
    from models import Agent
    workspace_id = get_workspace_id(user_id)
    return Agent.query.filter_by(id=agent_id, user_id=workspace_id).first()


def verify_api_key_ownership(api_key_id, user_id):
    """Verify that an API key belongs to the user's workspace. Returns ObsApiKey or None."""
    from models import ObsApiKey
    workspace_id = get_workspace_id(user_id)
    return ObsApiKey.query.filter_by(id=api_key_id, user_id=workspace_id).first()


# Re-export tier helpers for convenience (canonical impl in tier_enforcement.py)
from core.observability.tier_enforcement import (  # noqa: E402, F401
    get_workspace_tier,
    invalidate_tier_cache,
    verify_workspace_limits,
)
