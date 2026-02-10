# Green Monkey

**Autonomous AI agents that actually do work — safely.**

Green Monkey is a control plane for autonomous AI agents that can:

- **Observe** systems (Gmail, Google Calendar, Drive, Notion, Binance, GitHub)
- **Reason** about tasks using any LLM provider
- **Execute** approved actions through a human-in-the-loop queue
- **Report** back transparently with full audit trails

No black boxes. No runaway agents. No prompt spaghetti.

**[Live Dashboard](https://app.greenmonkey.dev)** | **[Docs](https://docs.greenmonkey.dev)**

---

## Who Is This For?

Green Monkey is built for:

- **Developers & founders** who want AI agents to *do things*, not just chat
- **AI-first teams** automating code, ops, research, or content workflows
- **Power users** tired of fragile Zapier/Make chains that break silently
- **Builders** experimenting with autonomous systems — responsibly

If you've ever thought *"this could be automated, but I don't trust AI alone"* — this is for you.

---

## What Makes Green Monkey Different?

Most AI tools generate text, require constant supervision, and break silently.

Green Monkey agents:

- Follow structured plans
- Execute **approved actions only** (human-in-the-loop by default)
- Connect to real services (Gmail, Calendar, Drive, Notion, Binance, and more)
- Leave auditable trails for every decision and action

Think: **GitHub Actions + LLM reasoning + guardrails.**

---

## Quick Start (5 Minutes)

```bash
git clone https://github.com/juanpasaflipz/openclaw-dashboard.git
cd openclaw-dashboard
cp .env.example .env
pip install -r requirements.txt
python server.py
```

Open **http://localhost:5000**

1. Sign in with your email (magic link auth)
2. Create your first agent — give it a name, personality, and goal
3. Connect a superpower (Gmail, Notion, Google Calendar, etc.)
4. Assign a task and approve its action plan
5. Watch it execute and report back

You now have a working autonomous agent.

---

## Example Use Cases

- **Email triage** — Agent reads Gmail, drafts replies, flags urgent items for approval
- **Research pipelines** — Agent browses the web, compiles findings, writes summaries
- **Calendar management** — Agent monitors events, sends reminders, reschedules conflicts
- **Crypto trading** — Agent watches Binance markets, proposes trades, executes on approval
- **Content workflows** — Agent researches topics, drafts content, manages publishing
- **Notion automation** — Agent keeps databases in sync, creates pages from templates

---

## How It Works

```
You define a goal
    → Agent reasons about it (using your chosen LLM)
    → Agent proposes actions
    → You approve or reject each action
    → Agent executes approved actions via connected services
    → Results are logged and reported back
```

### Superpowers (Connected Services)

Agents gain capabilities by connecting to external services:

| Service | What Agents Can Do |
|---------|-------------------|
| Gmail | Read, draft, send, label emails |
| Google Calendar | Read, create, update events |
| Google Drive | Read, search, organize files |
| Notion | Read, create, update pages & databases |
| Binance | Monitor markets, execute trades |
| Web Browsing | Research, extract content, summarize |

### LLM Providers

Bring your own LLM. Green Monkey supports:

- **Anthropic Claude** — Advanced reasoning
- **OpenAI** — GPT-4 and beyond
- **Google Gemini** — Multimodal capabilities
- **xAI Grok** — Real-time knowledge
- **OpenRouter** — Access 100+ models through one API
- **Ollama** — Run models locally, fully private
- **Groq, Cerebras, Cohere** — And more

---

## Architecture (For Builders)

Single-page Flask app. No frontend build step. Vanilla JS.

```
server.py                    # App entry point, route registration
models.py                    # SQLAlchemy models
dashboard.html               # Entire frontend UI
static/js/dashboard-main.js  # All frontend logic

*_routes.py                  # Feature route modules (auth, gmail, calendar,
                             #   drive, notion, binance, chatbot, agents, etc.)
llm_service.py               # LLM provider abstraction layer
```

**Key patterns:**

- **Route registration** — Each feature is a `register_*_routes(app)` function
- **Agent actions** — Approval queue with `pending → approved → executed` lifecycle
- **Superpowers** — OAuth/API-key services stored encrypted, hot-swappable
- **LLM abstraction** — OpenAI-compatible providers share one code path; others get dedicated methods

**Stack:** Flask, SQLAlchemy, vanilla JS. SQLite locally, Neon PostgreSQL in production. Deployed on Vercel.

---

## Philosophy

Green Monkey believes:

- **Autonomy must be earned** — Agents start constrained, gain trust over time
- **Intelligence must be bounded** — Every action goes through an approval queue
- **Power must be observable** — Full audit trails, no hidden decisions

Agents should be capable — but accountable.

---

## Status

Green Monkey is under active development. The core platform is stable and used in production, but the API surface is still evolving.

Best suited for builders comfortable with early-stage tools.

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Open a Pull Request

---

## License

MIT — see [LICENSE](LICENSE) for details.
