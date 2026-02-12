# Navigation Refactor Plan v2

> Generated: 2026-02-12
> Goal: Reorganize navigation to reflect a Backend AI Team Operating System

---

## 1. New Navigation Model

### Target Top-Level Structure

```
Overview (standalone)

1. Agents
   ├── Nautilus AI          (ext-agents)
   ├── My Agents            (agents)
   ├── Identity             (identity)
   ├── User Info            (user)
   ├── Soul & Behavior      (soul)
   ├── Tools                (tools)
   └── Security             (security)

2. Tasks
   ├── Task Queue           (collab-tasks)
   └── Team Hierarchy       (collab-team)

3. Governance
   ├── Risk Policies        (governance)     [badge]
   ├── Approval Queue       (actions)        [badge]
   └── Chatbot              (chatbot)

4. Observability
   ├── Live Activity        (observability)
   └── Analytics            (analytics)

5. Integrations
   ├── Services             (connect)
   ├── Channels             (channels)
   ├── Providers            (providers)
   ├── Model Config         (model-config)
   └── LLM Connection       (llm)

6. Workspace
   ├── Subscription         (subscription)
   ├── Export               (export)
   └── Admin                (admin)          [hidden]

7. Labs
   ├── Moltbook             (moltbook)
   ├── Feed                 (feed)
   ├── Web Browse           (web-browse)
   └── Utility              (utility)

Docs (external link)
```

---

## 2. Old-to-New Mapping

| data-tab | Old Group | New Group | New Label | Rationale |
|----------|-----------|-----------|-----------|-----------|
| `overview` | (standalone) | (standalone) | Overview | Unchanged |
| `ext-agents` | agents | agents | Nautilus AI | Unchanged — core agent interface |
| `agents` | agents | agents | My Agents | Unchanged — agent directory |
| `identity` | agents | agents | Identity | Unchanged — agent identity config |
| `user` | agents | agents | User Info | Unchanged — agent user config |
| `soul` | agents | agents | Soul & Behavior | Unchanged — agent personality |
| `tools` | agents | agents | Tools | Unchanged — agent capabilities |
| `security` | agents | agents | Security | Unchanged — agent safety |
| `collab-tasks` | workbench | tasks | Task Queue | **Elevated** — first-class orchestration pillar |
| `collab-team` | workbench | tasks | Team Hierarchy | **Moved** — organizational structure belongs with tasks |
| `governance` | workbench | governance | Risk Policies | **Elevated** — first-class governance pillar |
| `actions` | integrations | governance | Approval Queue | **Moved** — approval workflow is governance |
| `chatbot` | workbench | governance | Chatbot | **Moved** — agent interaction channel for oversight |
| `observability` | workbench | observability | Live Activity | **Elevated** — first-class observability pillar |
| `analytics` | social | observability | Analytics | **Moved** — operational metrics belong in observability |
| `connect` | integrations | integrations | Services | **Renamed** — clearer label |
| `channels` | integrations | integrations | Channels | Unchanged |
| `providers` | integrations | integrations | Providers | Unchanged |
| `model-config` | workbench | integrations | Model Config | **Moved** — configures integration with LLM providers |
| `llm` | workbench | integrations | LLM Connection | **Moved** — legacy LLM integration config |
| `subscription` | account | workspace | Subscription | **Renamed group** — workspace scope |
| `export` | account | workspace | Export | **Renamed group** |
| `admin` | account | workspace | Admin | **Renamed group** |
| `moltbook` | social | labs | Moltbook | **Moved** — experimental social feature |
| `feed` | social | labs | Feed | **Moved** — experimental feature |
| `web-browse` | workbench | labs | Web Browse | **Moved** — experimental tool |
| `utility` | workbench | labs | Utility | **Moved** — experimental tools |

---

## 3. Key Design Decisions

### A. Tasks as First-Class Pillar
Task orchestration (queue + team hierarchy) was buried 7 items deep in Workbench. Elevating it to a top-level group recognizes it as a core platform capability.

### B. Governance as First-Class Pillar
Policy governance and action approvals are both approval/oversight workflows. Grouping them together creates a single control surface for all governance activity. Chatbot is placed here as the primary human-agent interaction channel for oversight purposes.

### C. Observability Consolidation
The `observability` tab and `analytics` tab both provide monitoring/metrics. Grouping them under a single Observability pillar eliminates the split across unrelated groups.

### D. Integrations Absorbs LLM Config
`model-config`, `llm`, `providers`, `connect`, and `channels` all configure external service connections. Grouping them under Integrations creates a unified external connection surface.

### E. Labs for Experimental Features
Moltbook, Feed, Web Browse, and Utility are experimental or social features. Grouping them under Labs clearly signals their status and keeps the primary navigation focused on core platform pillars.

### F. Workspace Replaces Account
"Account" implies personal settings. "Workspace" better reflects the team-scoped administrative surface (subscription, export, admin).

---

## 4. Files Impacted

| File | Changes | Risk |
|------|---------|------|
| `dashboard.html` | Reorder nav dropdown groups and items (lines 42-158) | Medium — structural HTML change |
| `static/js/dashboard-main.js` | Update `TAB_GROUP_MAP` (lines 38-66) | Low — data mapping only |

### No Changes Required
- **Route files** — No API endpoint changes
- **Tab content panels** — All `<div class="tab-content" id="...">` unchanged
- **Init functions** — All `switchTab()` init mappings unchanged
- **CSS** — No style changes needed
- **data-tab attributes** — All preserved exactly

---

## 5. Route Aliasing

**None required.** All `data-tab` IDs are preserved identically. The only change is which `data-group` attribute wraps each dropdown item. The `switchTab()` function resolves tabs by `data-tab` (not by group), so no routing changes are needed.

---

## 6. Backward Compatibility

| Concern | Status |
|---------|--------|
| `data-tab` IDs | All 26 preserved |
| `switchTab()` calls in HTML | All still valid |
| `?tab=connect` URL param | Still works |
| `sessionStorage.redirectAfterLogin` | Still works |
| Badge elements (`#governance-pending-badge`, `#pending-actions-badge`) | Preserved |
| Admin tab visibility logic | Preserved |
| Pro tier gating | Preserved |
| Mobile hamburger menu | Works — same class structure |
