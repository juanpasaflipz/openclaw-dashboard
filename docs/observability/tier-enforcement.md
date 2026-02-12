# Tier Enforcement — Technical Reference

**Last updated:** 2026-02-11

---

## Architecture

All tier enforcement lives in a single module: `core/observability/tier_enforcement.py`. Route handlers call enforcement functions before performing gated operations. Every function reads from the `workspace_tiers` DB table via `get_workspace_tier()`, which caches results in-memory with a 60-second TTL.

```
Request
  → Route handler (routes/observability_routes.py)
    → Enforcement function (core/observability/tier_enforcement.py)
      → get_workspace_tier() — cached DB lookup
        → WorkspaceTier row or FREE defaults
    → 403 with upgrade_required: true (if denied)
    → Continue to business logic (if allowed)
```

---

## Caching

### In-Memory TTL Cache

```python
_tier_cache = {}       # {workspace_id: (tier_dict, timestamp)}
_TIER_CACHE_TTL = 60   # seconds
```

- **Lookup:** `get_workspace_tier(workspace_id)` checks the cache first. If the entry is < 60s old, it's returned without a DB query.
- **Invalidation:** `invalidate_tier_cache(workspace_id)` clears a specific entry. `invalidate_tier_cache()` (no args) clears all entries.
- **Automatic invalidation:** The admin tier update endpoint and billing webhook both call `invalidate_tier_cache(workspace_id)` after writing.

### When Cache Matters

- Normal request flow: tier is read from cache (sub-millisecond).
- After admin tier change: cache is explicitly invalidated; next request re-fetches from DB.
- Worst case: a tier change takes up to 60s to propagate if cache isn't manually invalidated (e.g., direct DB update bypassing the API).

---

## Enforcement Functions

### `get_workspace_tier(workspace_id) → dict`

Returns the full tier config as a dict. Falls back to `WorkspaceTier.TIER_DEFAULTS['free']` if no DB row exists. This is the foundation — all other functions call it.

### `invalidate_tier_cache(workspace_id=None)`

Clears cached tier data. Pass a specific ID or `None` to clear all entries.

### `check_agent_limit(workspace_id) → (bool, str|None)`

Counts distinct `agent_id` values in `ObsEvent` for the workspace. Returns `(False, message)` if at or over `agent_limit`.

### `check_agent_allowed(workspace_id, agent_id) → (bool, str|None)`

Smart check: if the agent already has events (known agent), always allowed. If it's a new agent, delegates to `check_agent_limit()`. This prevents existing agents from being locked out after a downgrade.

### `check_alert_rule_limit(workspace_id) → (bool, str|None)`

Counts `ObsAlertRule` rows for the workspace. Returns `(False, message)` if at or over `alert_rule_limit`. When the limit is 0 (free tier), the error message explicitly says alerts are not available.

### `get_retention_cutoff(workspace_id) → datetime`

Returns `utcnow() - retention_days` as a datetime. Used to filter event queries.

### `clamp_date_range(workspace_id, from_date, to_date) → (date, date)`

Clamps a date range to the retention window. If `from_date` is before the cutoff, it's moved forward. If `to_date` is None, it defaults to today (UTC).

### `get_health_history_cutoff(workspace_id) → date`

Returns the earliest allowed date for health score queries. `health_history_days=0` means today only.

### `check_anomaly_detection(workspace_id) → bool`

Returns `True` if anomaly detection is enabled for the workspace.

### `check_slack_notifications(workspace_id) → bool`

Returns `True` if Slack notifications are enabled.

### `check_api_key_limit(workspace_id) → (bool, str|None)`

Counts active `ObsApiKey` rows. Returns `(False, message)` if at or over `max_api_keys`.

### `get_max_batch_size(workspace_id) → int`

Returns the maximum events per ingestion batch.

### `verify_workspace_limits(workspace_id, check='all') → (bool, str|None)`

Composite check. Accepts:
- `'all'` — runs agent, alert_rule, and api_key checks.
- `'agent'`, `'alert_rule'`, `'api_key'` — runs a specific check.
- An `int` — treated as an `agent_id`, delegates to `check_agent_allowed()`.

---

## Enforcement Points by Endpoint

| Endpoint | Method | Enforcement |
|----------|--------|-------------|
| `/api/obs/ingest/events` | POST | `get_max_batch_size`, `check_agent_allowed` per event |
| `/api/obs/ingest/heartbeat` | POST | `check_agent_allowed` |
| `/api/obs/metrics/agents` | GET | `clamp_date_range` |
| `/api/obs/metrics/agent/<id>` | GET | `clamp_date_range`, `get_retention_cutoff` |
| `/api/obs/metrics/overview` | GET | `get_workspace_tier` (tier info in response) |
| `/api/obs/events` | GET | `get_retention_cutoff` |
| `/api/obs/alerts/rules` | POST | `check_alert_rule_limit` |
| `/api/obs/api-keys` | POST | `check_api_key_limit` |
| `/api/obs/health/agent/<id>` | GET | `get_health_history_cutoff`, `check_anomaly_detection` |
| `/api/obs/health/overview` | GET | `check_anomaly_detection` |

### Alert Engine (Internal)

`core/observability/alert_engine.py` → `_fire_alert()` calls `check_slack_notifications()` before dispatching. Alert events are always recorded in the DB regardless of notification gating.

### Retention Cleanup (Cron)

`core/observability/retention.py` → `cleanup_expired_events()` reads `get_workspace_tier()` per workspace to determine the cleanup cutoff (retention_days + 24h grace).

---

## Error Response Format

All tier enforcement denials return HTTP 403 with a consistent body:

```json
{
  "error": "Agent monitoring limit reached (2). Current tier: free. Upgrade to monitor more agents.",
  "upgrade_required": true
}
```

The `upgrade_required: true` flag enables frontend upgrade prompts without parsing error messages.

---

## Adding a New Gated Feature

1. **Add a column to `WorkspaceTier`** in `models.py` (with a default matching the free tier).
2. **Add the column to `TIER_DEFAULTS`** for all four tiers.
3. **Create an Alembic migration** to add the column.
4. **Add an enforcement function** in `tier_enforcement.py` following the pattern:

```python
def check_new_feature(workspace_id):
    """Check if new_feature is enabled for this workspace."""
    tier = get_workspace_tier(workspace_id)
    return tier['new_feature_enabled']
```

5. **Call the function in the route handler** before the gated operation.
6. **Add tests** in `tests/test_tier_enforcement.py` covering at least: free denied, production allowed (or denied), pro allowed.
7. **Export** from `core/observability/__init__.py` and `__all__`.

---

## Testing

Tests live in `tests/test_tier_enforcement.py` (79 tests across 8 test classes).

### Fixture Pattern

```python
@pytest.fixture
def free_user(self, client):
    """User with no WorkspaceTier row — defaults to free."""
    user = User(email='free@test.com')
    db.session.add(user)
    db.session.commit()
    return user

@pytest.fixture
def production_user(self, client):
    """User with production tier explicitly set."""
    user = User(email='prod@test.com')
    db.session.add(user)
    db.session.flush()
    tier = WorkspaceTier(workspace_id=user.id, tier_name='production',
                         **WorkspaceTier.TIER_DEFAULTS['production'])
    db.session.add(tier)
    db.session.commit()
    return user
```

### Backward Compatibility

Existing tests in `test_observability_v2.py` use an autouse fixture that seeds a production tier for the default test user. This ensures all pre-gating tests continue to pass without modification:

```python
@pytest.fixture(autouse=True)
def _ensure_production_tier(self, client):
    """Give the default test user a production tier so existing tests pass."""
    from models import WorkspaceTier
    user_id = 1  # default test user
    existing = WorkspaceTier.query.filter_by(workspace_id=user_id).first()
    if not existing:
        tier = WorkspaceTier(workspace_id=user_id, tier_name='production',
                             **WorkspaceTier.TIER_DEFAULTS['production'])
        db.session.add(tier)
        db.session.commit()
```

---

## File Map

| File | Role |
|------|------|
| `models.py` → `WorkspaceTier` | Schema + `TIER_DEFAULTS` (source of truth) |
| `core/observability/tier_enforcement.py` | All enforcement functions + cache |
| `core/observability/retention.py` | Cleanup job using tier retention window |
| `core/observability/alert_engine.py` | Slack notification gating |
| `routes/observability_routes.py` | Route-level enforcement calls |
| `tests/test_tier_enforcement.py` | 79 enforcement tests |
| `alembic/versions/011_add_workspace_tiers.py` | Migration |
