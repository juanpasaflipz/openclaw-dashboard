"""
core.identity — Agent Blueprint & Capability system.

Public API:
    agent_blueprint    — Blueprint CRUD, versioning, publishing, cloning
    agent_capabilities — CapabilityBundle CRUD, capability resolution
    agent_instance     — Instantiation, override validation, policy snapshot
    blueprint_registry — Query interface for listing/searching blueprints
    backward_compat    — Implicit blueprint generation for legacy agents
"""

from core.identity.agent_blueprint import (
    create_blueprint,
    get_blueprint,
    update_draft_blueprint,
    publish_blueprint,
    archive_blueprint,
    clone_blueprint,
    get_blueprint_version,
)
from core.identity.agent_capabilities import (
    create_capability_bundle,
    get_capability_bundle,
    resolve_capabilities,
    attach_capabilities,
)
from core.identity.agent_instance import (
    instantiate_agent,
    get_agent_instance,
    refresh_instance_policy,
    validate_overrides,
)
from core.identity.blueprint_registry import (
    list_blueprints,
    list_blueprint_versions,
)
from core.identity.backward_compat import (
    generate_implicit_blueprint,
    migrate_workspace_agents,
)

__all__ = [
    'create_blueprint',
    'get_blueprint',
    'update_draft_blueprint',
    'publish_blueprint',
    'archive_blueprint',
    'clone_blueprint',
    'get_blueprint_version',
    'create_capability_bundle',
    'get_capability_bundle',
    'resolve_capabilities',
    'attach_capabilities',
    'instantiate_agent',
    'get_agent_instance',
    'refresh_instance_policy',
    'validate_overrides',
    'list_blueprints',
    'list_blueprint_versions',
    'generate_implicit_blueprint',
    'migrate_workspace_agents',
]
