"""
Phase 4 API tests — Blueprint REST endpoints via Flask test client.

Covers all endpoints in routes/blueprint_routes.py:
    - Blueprint CRUD (list, create, get, update, publish, archive, clone)
    - Version listing and detail
    - Capability bundle CRUD (list, create, get, update)
    - Agent instantiation (instantiate, get instance, refresh, remove)
    - Authentication enforcement (401 on unauthenticated requests)
    - Workspace isolation (404 on cross-workspace access)
"""
import pytest
from datetime import datetime

from models import db, User, Agent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_client(client, user):
    """Authenticated test client."""
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['user_email'] = user.email
    return client


@pytest.fixture
def other_user(app):
    u = User(
        email='other-bp-api@example.com',
        created_at=datetime.utcnow(),
        credit_balance=10,
        subscription_tier='free',
        subscription_status='inactive',
    )
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def other_auth_client(app, other_user):
    """Auth client for another user (separate client for workspace isolation)."""
    other_client = app.test_client()
    with other_client.session_transaction() as sess:
        sess['user_id'] = other_user.id
        sess['user_email'] = other_user.email
    return other_client


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

class TestAuthEnforcement:

    def test_blueprints_list_requires_auth(self, client):
        resp = client.get('/api/blueprints')
        assert resp.status_code == 401

    def test_blueprints_create_requires_auth(self, client):
        resp = client.post('/api/blueprints', json={'name': 'X'})
        assert resp.status_code == 401

    def test_capabilities_list_requires_auth(self, client):
        resp = client.get('/api/capabilities')
        assert resp.status_code == 401

    def test_instantiate_requires_auth(self, client):
        resp = client.post('/api/agents/1/instantiate', json={})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Blueprint CRUD
# ---------------------------------------------------------------------------

class TestBlueprintAPI:

    def test_create_blueprint(self, auth_client):
        resp = auth_client.post('/api/blueprints', json={
            'name': 'API Blueprint',
            'description': 'Created via API',
            'role_type': 'researcher',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        bp = data['blueprint']
        assert bp['name'] == 'API Blueprint'
        assert bp['role_type'] == 'researcher'
        assert bp['status'] == 'draft'

    def test_create_blueprint_name_required(self, auth_client):
        resp = auth_client.post('/api/blueprints', json={})
        assert resp.status_code == 400
        assert 'Name is required' in resp.get_json()['error']

    def test_create_blueprint_invalid_role(self, auth_client):
        resp = auth_client.post('/api/blueprints', json={
            'name': 'Bad Role',
            'role_type': 'invalid',
        })
        assert resp.status_code == 400

    def test_list_blueprints_empty(self, auth_client):
        resp = auth_client.get('/api/blueprints')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['blueprints'] == []
        assert data['total'] == 0

    def test_list_blueprints_with_data(self, auth_client):
        auth_client.post('/api/blueprints', json={'name': 'BP-A'})
        auth_client.post('/api/blueprints', json={'name': 'BP-B'})

        resp = auth_client.get('/api/blueprints')
        data = resp.get_json()
        assert data['total'] == 2
        assert len(data['blueprints']) == 2

    def test_list_blueprints_filter_by_status(self, auth_client):
        auth_client.post('/api/blueprints', json={'name': 'Draft One'})

        resp = auth_client.get('/api/blueprints?status=draft')
        assert resp.get_json()['total'] == 1

        resp = auth_client.get('/api/blueprints?status=published')
        assert resp.get_json()['total'] == 0

    def test_get_blueprint(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={
            'name': 'Detail BP',
        })
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = auth_client.get(f'/api/blueprints/{bp_id}')
        assert resp.status_code == 200
        bp = resp.get_json()['blueprint']
        assert bp['name'] == 'Detail BP'
        assert bp['instance_count'] == 0

    def test_get_blueprint_not_found(self, auth_client):
        resp = auth_client.get('/api/blueprints/nonexistent-id')
        assert resp.status_code == 404

    def test_update_draft_blueprint(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={
            'name': 'Original Name',
        })
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = auth_client.post(f'/api/blueprints/{bp_id}', json={
            'name': 'Updated Name',
            'description': 'New desc',
        })
        assert resp.status_code == 200
        assert resp.get_json()['blueprint']['name'] == 'Updated Name'

    def test_update_no_fields(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'X'})
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = auth_client.post(f'/api/blueprints/{bp_id}', json={})
        assert resp.status_code == 400

    def test_publish_blueprint(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={
            'name': 'Publish Me',
        })
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = auth_client.post(f'/api/blueprints/{bp_id}/publish', json={
            'allowed_tools': ['web_search', 'send_email'],
            'allowed_models': ['openai'],
            'changelog': 'Initial release',
        })
        assert resp.status_code == 201
        ver = resp.get_json()['version']
        assert ver['version'] == 1
        assert ver['allowed_tools'] == ['web_search', 'send_email']
        assert ver['changelog'] == 'Initial release'

    def test_publish_increments_version(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'Multi-V'})
        bp_id = create_resp.get_json()['blueprint']['id']

        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={'changelog': 'v1'})
        resp = auth_client.post(f'/api/blueprints/{bp_id}/publish', json={'changelog': 'v2'})
        assert resp.get_json()['version']['version'] == 2

    def test_archive_blueprint(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'Archive Me'})
        bp_id = create_resp.get_json()['blueprint']['id']
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={})

        resp = auth_client.post(f'/api/blueprints/{bp_id}/archive')
        assert resp.status_code == 200
        assert resp.get_json()['blueprint']['status'] == 'archived'

    def test_archive_draft_fails(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'Still Draft'})
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = auth_client.post(f'/api/blueprints/{bp_id}/archive')
        assert resp.status_code == 400

    def test_clone_blueprint(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'Source'})
        bp_id = create_resp.get_json()['blueprint']['id']
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={
            'allowed_tools': ['tool_a'],
        })

        resp = auth_client.post(f'/api/blueprints/{bp_id}/clone', json={
            'version': 1,
            'name': 'My Clone',
        })
        assert resp.status_code == 201
        clone = resp.get_json()['blueprint']
        assert clone['name'] == 'My Clone'
        assert clone['status'] == 'draft'
        assert clone['id'] != bp_id

    def test_clone_requires_version(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'X'})
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = auth_client.post(f'/api/blueprints/{bp_id}/clone', json={})
        assert resp.status_code == 400
        assert 'version' in resp.get_json()['error']


# ---------------------------------------------------------------------------
# Blueprint Versions
# ---------------------------------------------------------------------------

class TestVersionAPI:

    def test_list_versions(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'Versioned'})
        bp_id = create_resp.get_json()['blueprint']['id']
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={'changelog': 'v1'})
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={'changelog': 'v2'})

        resp = auth_client.get(f'/api/blueprints/{bp_id}/versions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 2

    def test_list_versions_blueprint_not_found(self, auth_client):
        resp = auth_client.get('/api/blueprints/no-such-id/versions')
        assert resp.status_code == 404

    def test_get_version_detail(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'V Detail'})
        bp_id = create_resp.get_json()['blueprint']['id']
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={
            'allowed_tools': ['web_search'],
        })

        resp = auth_client.get(f'/api/blueprints/{bp_id}/versions/1')
        assert resp.status_code == 200
        ver = resp.get_json()['version']
        assert ver['version'] == 1
        assert ver['allowed_tools'] == ['web_search']
        assert 'capabilities' in ver

    def test_get_version_not_found(self, auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'X'})
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = auth_client.get(f'/api/blueprints/{bp_id}/versions/99')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Capability Bundles
# ---------------------------------------------------------------------------

class TestCapabilityAPI:

    def test_create_capability(self, auth_client):
        resp = auth_client.post('/api/capabilities', json={
            'name': 'Gmail Tools',
            'description': 'Email access',
            'tool_set': ['gmail_send', 'gmail_read'],
            'model_constraints': {'allowed_providers': ['openai']},
        })
        assert resp.status_code == 201
        cap = resp.get_json()['capability']
        assert cap['name'] == 'Gmail Tools'
        assert cap['tool_set'] == ['gmail_send', 'gmail_read']

    def test_create_capability_name_required(self, auth_client):
        resp = auth_client.post('/api/capabilities', json={})
        assert resp.status_code == 400

    def test_create_duplicate_name(self, auth_client):
        auth_client.post('/api/capabilities', json={'name': 'Unique'})
        resp = auth_client.post('/api/capabilities', json={'name': 'Unique'})
        assert resp.status_code == 400

    def test_list_capabilities(self, auth_client):
        auth_client.post('/api/capabilities', json={'name': 'Cap-A'})
        auth_client.post('/api/capabilities', json={'name': 'Cap-B'})

        resp = auth_client.get('/api/capabilities')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 2

    def test_get_capability(self, auth_client):
        create_resp = auth_client.post('/api/capabilities', json={
            'name': 'Detail Cap',
        })
        cap_id = create_resp.get_json()['capability']['id']

        resp = auth_client.get(f'/api/capabilities/{cap_id}')
        assert resp.status_code == 200
        assert resp.get_json()['capability']['name'] == 'Detail Cap'

    def test_get_capability_not_found(self, auth_client):
        resp = auth_client.get('/api/capabilities/99999')
        assert resp.status_code == 404

    def test_update_capability(self, auth_client):
        create_resp = auth_client.post('/api/capabilities', json={
            'name': 'Mutable',
            'tool_set': ['a'],
        })
        cap_id = create_resp.get_json()['capability']['id']

        resp = auth_client.post(f'/api/capabilities/{cap_id}', json={
            'tool_set': ['a', 'b', 'c'],
        })
        assert resp.status_code == 200
        assert resp.get_json()['capability']['tool_set'] == ['a', 'b', 'c']

    def test_update_capability_no_fields(self, auth_client):
        create_resp = auth_client.post('/api/capabilities', json={'name': 'X'})
        cap_id = create_resp.get_json()['capability']['id']

        resp = auth_client.post(f'/api/capabilities/{cap_id}', json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Agent Instantiation
# ---------------------------------------------------------------------------

class TestInstantiationAPI:

    def test_instantiate_agent(self, auth_client, user, agent):
        # Create and publish a blueprint
        bp_resp = auth_client.post('/api/blueprints', json={'name': 'Inst BP'})
        bp_id = bp_resp.get_json()['blueprint']['id']
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={
            'allowed_tools': ['web_search'],
        })

        resp = auth_client.post(f'/api/agents/{agent.id}/instantiate', json={
            'blueprint_id': bp_id,
            'version': 1,
        })
        assert resp.status_code == 201
        inst = resp.get_json()['instance']
        assert inst['agent_id'] == agent.id
        assert inst['blueprint_id'] == bp_id
        assert inst['blueprint_version'] == 1
        assert inst['policy_snapshot'] is not None

    def test_instantiate_missing_blueprint_id(self, auth_client, agent):
        resp = auth_client.post(f'/api/agents/{agent.id}/instantiate', json={
            'version': 1,
        })
        assert resp.status_code == 400
        assert 'blueprint_id' in resp.get_json()['error']

    def test_instantiate_missing_version(self, auth_client, agent):
        resp = auth_client.post(f'/api/agents/{agent.id}/instantiate', json={
            'blueprint_id': 'some-id',
        })
        assert resp.status_code == 400
        assert 'version' in resp.get_json()['error']

    def test_instantiate_nonexistent_blueprint(self, auth_client, agent):
        resp = auth_client.post(f'/api/agents/{agent.id}/instantiate', json={
            'blueprint_id': 'nonexistent',
            'version': 1,
        })
        assert resp.status_code == 404

    def test_get_instance_with_binding(self, auth_client, user, agent):
        bp_resp = auth_client.post('/api/blueprints', json={'name': 'Get Inst'})
        bp_id = bp_resp.get_json()['blueprint']['id']
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={})
        auth_client.post(f'/api/agents/{agent.id}/instantiate', json={
            'blueprint_id': bp_id, 'version': 1,
        })

        resp = auth_client.get(f'/api/agents/{agent.id}/instance')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_legacy'] is False
        assert data['instance']['blueprint_id'] == bp_id

    def test_get_instance_legacy_agent(self, auth_client, agent):
        resp = auth_client.get(f'/api/agents/{agent.id}/instance')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_legacy'] is True
        assert data['instance'] is None

    def test_get_instance_agent_not_found(self, auth_client):
        resp = auth_client.get('/api/agents/99999/instance')
        assert resp.status_code == 404

    def test_refresh_instance(self, auth_client, user, agent):
        bp_resp = auth_client.post('/api/blueprints', json={'name': 'Refresh BP'})
        bp_id = bp_resp.get_json()['blueprint']['id']
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={
            'allowed_tools': ['a'],
        })
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={
            'allowed_tools': ['a', 'b'],
        })
        auth_client.post(f'/api/agents/{agent.id}/instantiate', json={
            'blueprint_id': bp_id, 'version': 1,
        })

        resp = auth_client.post(f'/api/agents/{agent.id}/instance/refresh', json={
            'version': 2,
        })
        assert resp.status_code == 200
        assert resp.get_json()['instance']['blueprint_version'] == 2

    def test_refresh_nonexistent_instance(self, auth_client, agent):
        resp = auth_client.post(f'/api/agents/{agent.id}/instance/refresh', json={})
        assert resp.status_code == 404

    def test_remove_instance(self, auth_client, user, agent):
        bp_resp = auth_client.post('/api/blueprints', json={'name': 'Remove BP'})
        bp_id = bp_resp.get_json()['blueprint']['id']
        auth_client.post(f'/api/blueprints/{bp_id}/publish', json={})
        auth_client.post(f'/api/agents/{agent.id}/instantiate', json={
            'blueprint_id': bp_id, 'version': 1,
        })

        resp = auth_client.delete(f'/api/agents/{agent.id}/instance')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        # Verify now legacy
        get_resp = auth_client.get(f'/api/agents/{agent.id}/instance')
        assert get_resp.get_json()['is_legacy'] is True

    def test_remove_nonexistent_instance(self, auth_client, agent):
        resp = auth_client.delete(f'/api/agents/{agent.id}/instance')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:

    def test_cannot_see_other_workspace_blueprints(self, auth_client, other_auth_client):
        """Blueprints created by one user are invisible to another."""
        # User A creates a blueprint
        auth_client.post('/api/blueprints', json={'name': 'Private BP'})

        # User B should see zero blueprints
        resp = other_auth_client.get('/api/blueprints')
        assert resp.get_json()['total'] == 0

    def test_cannot_get_other_workspace_blueprint(self, auth_client, other_auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'Hidden'})
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = other_auth_client.get(f'/api/blueprints/{bp_id}')
        assert resp.status_code == 404

    def test_cannot_publish_other_workspace_blueprint(self, auth_client, other_auth_client):
        create_resp = auth_client.post('/api/blueprints', json={'name': 'X'})
        bp_id = create_resp.get_json()['blueprint']['id']

        resp = other_auth_client.post(f'/api/blueprints/{bp_id}/publish', json={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Publish with capabilities
# ---------------------------------------------------------------------------

class TestPublishWithCapabilities:

    def test_publish_with_capability_ids(self, auth_client):
        # Create capability
        cap_resp = auth_client.post('/api/capabilities', json={
            'name': 'Email Cap',
            'tool_set': ['gmail_send'],
        })
        cap_id = cap_resp.get_json()['capability']['id']

        # Create and publish blueprint with capability
        bp_resp = auth_client.post('/api/blueprints', json={'name': 'Capped BP'})
        bp_id = bp_resp.get_json()['blueprint']['id']

        pub_resp = auth_client.post(f'/api/blueprints/{bp_id}/publish', json={
            'capability_ids': [cap_id],
            'allowed_tools': ['gmail_send', 'gmail_read'],
        })
        assert pub_resp.status_code == 201

        # Verify version detail includes capabilities
        ver_resp = auth_client.get(f'/api/blueprints/{bp_id}/versions/1')
        ver = ver_resp.get_json()['version']
        assert len(ver['capabilities']) == 1
        assert ver['capabilities'][0]['name'] == 'Email Cap'

    def test_publish_with_invalid_capability_id(self, auth_client):
        bp_resp = auth_client.post('/api/blueprints', json={'name': 'Bad Cap'})
        bp_id = bp_resp.get_json()['blueprint']['id']

        resp = auth_client.post(f'/api/blueprints/{bp_id}/publish', json={
            'capability_ids': [99999],
        })
        assert resp.status_code == 400
