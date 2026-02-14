# Target Folder Layout

> Phase 0 — proposal only. No code changes.

## Current → Target Mapping

### Current layout (flat)

```
/
├── server.py                          # app entry + admin endpoints + misc routes
├── models.py                          # all 39 models in one file
├── llm_service.py                     # LLM provider abstraction
├── binance_service.py                 # Binance API wrapper
├── memory_service.py                  # Semantic memory
├── context_manager.py                 # Context window mgmt
├── agent_tools.py                     # Agent tool definitions
├── observability_service.py           # shim → core/observability
├── rate_limiter.py                    # Flask-Limiter setup
│
├── auth_routes.py                     # 33 route files at root level
├── gmail_routes.py
├── governance_routes.py
├── collaboration_tasks_routes.py
├── ...all other *_routes.py
│
├── core/
│   ├── observability/                 # 11 files
│   ├── risk_engine/                   # 5 files
│   ├── governance/                    # 6 files
│   └── collaboration/                 # 1 file (governance_hooks.py)
│
├── static/
│   ├── js/dashboard-main.js
│   └── css/
├── dashboard.html
├── tests/
└── docs/
```

### Target layout

```
/
├── server.py                          # app factory + blueprint registration ONLY
│
├── core/                              # ── CONTROL PLANE ──
│   ├── identity/
│   │   ├── __init__.py
│   │   ├── auth.py                    # magic link, session, login/logout logic
│   │   ├── users.py                   # user lifecycle, tier checks, credit ops
│   │   └── subscriptions.py           # Stripe integration logic (from stripe_routes)
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── registry.py                # agent CRUD, config management
│   │   ├── actions.py                 # approval queue state machine
│   │   ├── llm_service.py             # ← from root llm_service.py
│   │   ├── tools.py                   # ← from root agent_tools.py
│   │   ├── memory.py                  # ← from root memory_service.py
│   │   └── context.py                 # ← from root context_manager.py
│   │
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── engine.py                  # task state machine, transitions
│   │   ├── assignment.py              # role-based assignment, hierarchy checks
│   │   └── messaging.py               # agent-to-agent messaging
│   │
│   ├── governance/                    # ← from core/governance/ (already exists)
│   │   ├── __init__.py
│   │   ├── requests.py
│   │   ├── approvals.py
│   │   ├── delegation.py
│   │   ├── rollback.py
│   │   ├── boundaries.py
│   │   └── governance_audit.py
│   │
│   ├── risk/                          # ← from core/risk_engine/
│   │   ├── __init__.py
│   │   ├── policy.py
│   │   ├── evaluator.py
│   │   ├── interventions.py
│   │   ├── enforcement_worker.py
│   │   └── audit_log.py
│   │
│   ├── observability/                 # ← from core/observability/ (already exists)
│   │   ├── __init__.py
│   │   ├── ingestion.py
│   │   ├── run_tracker.py
│   │   ├── cost_engine.py
│   │   ├── metrics.py
│   │   ├── alert_engine.py
│   │   ├── health_score.py
│   │   ├── tier_enforcement.py
│   │   ├── workspace.py
│   │   ├── retention.py
│   │   ├── notifications.py
│   │   └── constants.py
│   │
│   ├── audit/
│   │   ├── __init__.py
│   │   └── query.py                   # unified read interface across all audit logs
│   │
│   └── team/
│       ├── __init__.py
│       ├── roles.py                   # AgentRole CRUD
│       └── rules.py                   # TeamRule workspace config
│
├── adapters/                          # ── INTEGRATION ADAPTERS ──
│   ├── __init__.py
│   ├── gmail/
│   │   ├── __init__.py
│   │   └── client.py                  # Gmail API wrapper + token refresh
│   ├── calendar/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── drive/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── notion/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── github/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── binance/
│   │   ├── __init__.py
│   │   ├── client.py                  # ← from binance_service.py
│   │   └── actions.py                 # binance-specific action execution
│   ├── spotify/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── todoist/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── dropbox/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── slack/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── discord/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── client.py
│   └── oauth/
│       ├── __init__.py
│       └── flow.py                    # shared OAuth token exchange logic
│
├── api/                               # ── THIN ROUTING LAYER ──
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py                    # /api/auth/*
│   │   ├── agents.py                  # /api/agents/*
│   │   ├── actions.py                 # /api/agent-actions/*
│   │   ├── chat.py                    # /api/chat/*
│   │   ├── models.py                  # /api/model-config/*
│   │   ├── providers.py               # /api/llm-providers/*
│   │   ├── superpowers.py             # /api/superpowers/* (connect/disconnect)
│   │   ├── gmail.py                   # /api/gmail/*
│   │   ├── calendar.py                # /api/calendar/*
│   │   ├── drive.py                   # /api/drive/*
│   │   ├── notion.py                  # /api/notion/*
│   │   ├── github.py                  # /api/github/*
│   │   ├── binance.py                 # /api/binance/*
│   │   ├── spotify.py                 # /api/spotify/*
│   │   ├── todoist.py                 # /api/todoist/*
│   │   ├── dropbox.py                 # /api/dropbox/*
│   │   ├── channels.py                # /api/channels/* (unified webhook hub)
│   │   ├── slack.py                   # /api/slack/*
│   │   ├── discord.py                 # /api/discord/*
│   │   ├── telegram.py                # /api/telegram/*
│   │   ├── observability.py           # /api/obs/*
│   │   ├── governance.py              # /api/governance/*
│   │   ├── risk.py                    # /api/risk/* (if exposed)
│   │   ├── tasks.py                   # /api/tasks/*
│   │   ├── messages.py                # /api/messages/*
│   │   ├── team.py                    # /api/team/*
│   │   ├── moltbook.py                # /api/moltbook/*
│   │   ├── analytics.py               # /api/analytics/*
│   │   ├── stripe.py                  # /api/stripe/*
│   │   ├── setup.py                   # /api/setup/*
│   │   ├── memory.py                  # /api/memory/*
│   │   ├── web_browsing.py            # /api/web-browsing/*
│   │   ├── utility.py                 # /api/utility/*
│   │   └── admin.py                   # /api/admin/* (init-db, migrations)
│   └── middleware/
│       ├── __init__.py
│       ├── auth_guard.py              # session check decorator
│       └── rate_limit.py              # ← from rate_limiter.py
│
├── models/                            # ── DATA LAYER ──
│   ├── __init__.py                    # re-exports all models + db instance
│   ├── base.py                        # db = SQLAlchemy(), common mixins
│   ├── identity.py                    # User, MagicLink, CreditTransaction, SubscriptionPlan, CreditPackage
│   ├── agents.py                      # Agent, AgentAction
│   ├── superpowers.py                 # Superpower, ConfigFile
│   ├── workbench.py                   # UserModelConfig, ChatConversation, ChatMessage, MemoryEmbedding, WebBrowsingResult
│   ├── observability.py               # Obs* models, WorkspaceTier
│   ├── risk.py                        # RiskPolicy, RiskEvent, RiskAuditLog
│   ├── governance.py                  # PolicyChangeRequest, DelegationGrant, GovernanceAuditLog
│   ├── collaboration.py               # CollaborationTask, TaskEvent, AgentMessage, AgentRole, TeamRule
│   └── moltbook.py                    # MoltbookFeedCache, UserUpvote, AnalyticsSnapshot, PostAnalytics, PostHistory
│
├── static/                            # ── UI (REFERENCE CLIENT) ──
│   ├── js/
│   │   └── dashboard-main.js
│   └── css/
├── dashboard.html
│
├── tests/                             # mirrors core/ + adapters/ + api/
│   ├── conftest.py
│   ├── core/
│   │   ├── test_identity.py
│   │   ├── test_tasks.py
│   │   ├── test_governance.py
│   │   ├── test_risk.py
│   │   ├── test_observability.py
│   │   └── test_collaboration_e2e.py
│   ├── adapters/
│   │   └── ...
│   └── api/
│       └── ...
│
├── scripts/                           # CLI utilities, migration scripts
├── alembic/                           # DB migrations
├── docs/                              # documentation site
└── requirements.txt
```

---

## Migration Sequence (Future Phases)

These phases preserve behavior at every step. Each phase results in passing tests.

| Phase | What moves | Risk | Verification |
|---|---|---|---|
| **1** | Split `models.py` → `models/*.py` with re-export `__init__` | Low — import paths unchanged via re-export | All tests pass |
| **2** | Move root `*_service.py` files into `core/agents/` | Low — update imports | All tests pass |
| **3** | Move existing `core/risk_engine/` → `core/risk/` | Low — rename only | All tests pass |
| **4** | Extract business logic from route files into `core/` modules | Medium — largest change | All tests pass + manual smoke test |
| **5** | Move route files into `api/routes/`, convert to thin wrappers | Medium — many file moves | All tests pass |
| **6** | Extract adapter logic from route files into `adapters/` | Medium — adapter + route split | All tests pass |
| **7** | Move `rate_limiter.py` → `api/middleware/`, extract auth guard | Low | All tests pass |
| **8** | Restructure `tests/` to mirror new layout | Low — test content unchanged | All tests pass |

---

## Key Decisions

**Q: Why not a `services/` layer between core and routes?**
A: The current codebase already has `core/` modules that serve this purpose. Adding `services/` would create a fourth layer with unclear boundaries. Core modules *are* the service layer.

**Q: Why keep `dashboard.html` at root instead of `ui/`?**
A: Vercel deployment expects static assets at specific paths. Moving it requires `vercel.json` changes. Deferred to a UI-focused phase.

**Q: Why `models/` as a separate top-level directory instead of inside `core/`?**
A: Models are shared across core, adapters, and routes. Placing them in `core/` would force adapters to import from core, violating the rule that adapters don't depend on core internals. Models are the shared foundation that all layers depend on.

**Q: Why `adapters/oauth/` as a separate adapter?**
A: OAuth token exchange is shared across Gmail, Calendar, Drive, Notion, and GitHub. Extracting it avoids duplicating the flow in each adapter.
