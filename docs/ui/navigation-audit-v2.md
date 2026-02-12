# Navigation Audit v2

> Generated: 2026-02-12
> Scope: dashboard.html, static/js/dashboard-main.js, all route modules

---

## 1. Current Navigation Topology

### Top-Level Structure

| # | Nav Element | Type | data-group | Items |
|---|------------|------|------------|-------|
| 0 | Overview | Standalone button | — | 1 (self) |
| 1 | Agents | Dropdown | `agents` | 7 |
| 2 | Workbench | Dropdown | `workbench` | 9 |
| 3 | Integrations | Dropdown | `integrations` | 4 |
| 4 | Social | Dropdown | `social` | 3 |
| 5 | Account | Dropdown | `account` | 3 (1 hidden) |
| 6 | Docs | External link | — | — |

**Total unique tabs: 26** (+ 1 external link)

---

## 2. Complete Tab Inventory

### Group: (standalone)
| data-tab | Label | Icon | Init Function | Notes |
|----------|-------|------|---------------|-------|
| `overview` | Overview | — | — | Default active tab |

### Group: agents
| data-tab | Label | Icon | Init Function | Notes |
|----------|-------|------|---------------|-------|
| `ext-agents` | Nautilus AI | `🐙` | `initExtAgentsTab()` | "NEW" badge |
| `agents` | My Agents | `🤖` | `loadAgents()` | |
| `identity` | Identity | `👤` | — | Uses `/api/config/*` |
| `user` | User Info | `📝` | — | Uses `/api/config/*` |
| `soul` | Soul & Behavior | `✨` | — | Uses `/api/config/*` |
| `tools` | Tools | `🛠️` | — | Uses `/api/config/*` |
| `security` | Security | `🔒` | — | Uses `/api/config/*` |

### Group: workbench
| data-tab | Label | Icon | Init Function | Notes |
|----------|-------|------|---------------|-------|
| `chatbot` | Chat Bot | `💬` | `initChatTab()` | |
| `web-browse` | Web Browse | `🌐` | `initWebBrowseTab()` | |
| `utility` | Utility | `🧰` | `initUtilityTab()` | |
| `model-config` | Model Config | `⚙️` | `initModelConfigTab()` | |
| `llm` | LLM Connection | `🔌` | — | Legacy config |
| `observability` | Observability | `📡` | `initObservabilityTab()` | |
| `governance` | Governance | `🛡️` | `initGovernanceTab()` | Pending badge |
| `collab-tasks` | Tasks | `📋` | `initCollabTasksTab()` | |
| `collab-team` | Team | `👥` | `initCollabTeamTab()` | |

### Group: integrations
| data-tab | Label | Icon | Init Function | Notes |
|----------|-------|------|---------------|-------|
| `connect` | Connect | `🔌` | — | OAuth services |
| `channels` | Channels | `💬` | — | Messaging channels |
| `actions` | Actions | `✅` | — | Pending badge |
| `providers` | Providers | `🤖` | — | LLM providers |

### Group: social
| data-tab | Label | Icon | Init Function | Notes |
|----------|-------|------|---------------|-------|
| `moltbook` | Moltbook | `🦞` | `loadMoltbookState()` | |
| `feed` | Feed | `📖` | `initFeedTab()` | Pro-gated |
| `analytics` | Analytics | `📊` | `initAnalyticsTab()` | Pro-gated |

### Group: account
| data-tab | Label | Icon | Init Function | Notes |
|----------|-------|------|---------------|-------|
| `subscription` | Subscription | `💎` | — | |
| `export` | Export | `💾` | `loadPreviews()` | |
| `admin` | Admin | `🔐` | — | Hidden by default |

---

## 3. TAB_GROUP_MAP (dashboard-main.js:38-66)

```javascript
const TAB_GROUP_MAP = {
    'overview': null,
    'ext-agents': 'agents',
    'agents': 'agents',
    'identity': 'agents',
    'user': 'agents',
    'soul': 'agents',
    'tools': 'agents',
    'security': 'agents',
    'chatbot': 'workbench',
    'web-browse': 'workbench',
    'utility': 'workbench',
    'model-config': 'workbench',
    'llm': 'workbench',
    'observability': 'workbench',
    'governance': 'workbench',
    'collab-tasks': 'workbench',
    'collab-team': 'workbench',
    'connect': 'integrations',
    'channels': 'integrations',
    'actions': 'integrations',
    'providers': 'integrations',
    'moltbook': 'social',
    'feed': 'social',
    'analytics': 'social',
    'subscription': 'account',
    'export': 'account',
    'admin': 'account'
};
```

---

## 4. Route File to Tab Mapping

| Route Module | Primary Tab(s) | API Prefix |
|-------------|---------------|------------|
| `auth_routes.py` | All (session) | `/api/auth/*` |
| `agent_routes.py` | `agents` | `/api/agents` |
| `agent_actions_routes.py` | `actions` | `/api/agent-actions/*` |
| `analytics_routes.py` | `analytics` | Blueprint `analytics_bp` |
| `binance_routes.py` | `connect` | `/api/binance/*` |
| `binance_actions_routes.py` | `actions` | `/api/agent-actions/propose-trade` |
| `calendar_routes.py` | `connect` | `/api/calendar/*` |
| `channels_routes.py` | `channels` | `/api/channels/*` |
| `chatbot_routes.py` | `chatbot` | `/api/chat/*` |
| `collaboration_messages_routes.py` | `collab-tasks` | `/api/messages` |
| `collaboration_tasks_routes.py` | `collab-tasks` | `/api/tasks/*` |
| `collaboration_team_routes.py` | `collab-team` | `/api/team/*` |
| `discord_routes.py` | `connect` | `/api/discord/*` |
| `drive_routes.py` | `connect` | `/api/drive/*` |
| `dropbox_routes.py` | `connect` | `/api/dropbox/*` |
| `external_agents_routes.py` | `ext-agents` | `/api/external-agents/*` |
| `github_routes.py` | `connect` | `/api/github/*` |
| `gmail_routes.py` | `connect` | `/api/gmail/*` |
| `governance_routes.py` | `governance` | `/api/governance/*` |
| `llm_providers_routes.py` | `providers` | `/api/providers/*` |
| `model_config_routes.py` | `model-config` | `/api/model-config/*` |
| `moltbook_routes.py` | `moltbook`, `feed` | Blueprint `moltbook_bp` |
| `notion_routes.py` | `connect` | `/api/notion/*` |
| `oauth_routes.py` | `connect` | `/api/oauth/*`, `/api/superpowers/*` |
| `observability_routes.py` | `observability` | Blueprint `obs_bp` |
| `setup_routes.py` | `identity`, `user`, `soul`, `tools`, `security`, `llm`, `export` | `/api/setup/*`, `/api/config/*` |
| `slack_routes.py` | `connect` | `/api/slack/*` |
| `spotify_routes.py` | `connect` | `/api/spotify/*` |
| `stripe_routes.py` | `subscription` | `/api/credits/*`, `/api/subscriptions/*` |
| `telegram_routes.py` | `connect`, `channels` | `/api/telegram/*` |
| `todoist_routes.py` | `connect` | `/api/todoist/*` |
| `utility_routes.py` | `utility` | `/api/utility/*` |
| `web_browsing_routes.py` | `web-browse` | `/api/browse/*` |

---

## 5. Cross-References (switchTab calls in JS)

| Location | Target Tab | Context |
|----------|-----------|---------|
| Overview hero CTA | `ext-agents` | "Try Nautilus" button |
| Overview setup CTA | `llm` | "Configure LLM" |
| Model config banner | `model-config` | Internal redirect |
| `showSubscriptionTab()` | `subscription` | Upgrade button |
| Channel/Provider login gate | `overview` | "Go to Login" |
| Post-login redirect | (any) | `sessionStorage.redirectAfterLogin` |
| URL param `?tab=connect` | `connect` | OAuth callback |

---

## 6. Identified Overlaps & Redundancies

### A. LLM Configuration Fragmentation
- **`llm`** (Workbench) — Legacy single-provider connection form
- **`model-config`** (Workbench) — New per-feature model configuration
- **`providers`** (Integrations) — Provider directory with connection UI

Three tabs serve overlapping purposes around LLM provider management.

### B. Governance Buried Under Workbench
- **`governance`** contains: Risk Policies, Delegation, Approval workflow, Audit log
- **`actions`** (Integrations) contains: Agent action approval queue

Both are approval/governance workflows living in different nav groups.

### C. Tasks & Team Buried Under Workbench
- **`collab-tasks`** — Task queue, delegation chains
- **`collab-team`** — Team hierarchy, agent roles

These are core orchestration primitives hidden inside a catch-all "Workbench" group.

### D. Observability Isolated
- **`observability`** is the only monitoring tab
- **`analytics`** (Social) also provides operational insights

Monitoring/metrics split across unrelated groups.

### E. Workbench is a Junk Drawer
9 items spanning: chat tools, LLM config, observability, governance, task orchestration. No coherent theme.

---

## 7. Conditional/Dynamic Elements

| Element | Condition | Mechanism |
|---------|----------|-----------|
| Admin tab | Admin user | `style="display: none"` toggled by JS |
| Governance badge | Pending policies > 0 | `#governance-pending-badge` |
| Actions badge | Pending actions > 0 | `#pending-actions-badge` |
| Nautilus "NEW" badge | Always shown | Static badge |
| Feed/Analytics | Pro tier | Shows upgrade prompt for Free |

---

## 8. Summary Statistics

- **Total tabs:** 26
- **Dropdown groups:** 5
- **Route modules:** 34
- **Init functions:** 14
- **Tabs with dynamic badges:** 2
- **Pro-gated tabs:** 2
- **Hidden tabs:** 1 (admin)
- **External links:** 1 (docs)
