# 🤖 AI Agent Actions - Setup Guide

## What We Built

An **approval queue system** that lets AI agents propose actions (like sending emails) that require your approval before executing. This gives you control while letting AI handle the heavy lifting!

---

## 🎯 Features

### 1. **Inbox Analysis** 📊
- AI reads your recent emails
- Identifies urgent items
- Suggests actions to take
- Powered by Claude Sonnet 4.5

### 2. **Email Reply Drafting** ✍️
- AI drafts professional replies
- Queued for your approval
- You review, edit, approve
- Only sends when you say so

### 3. **Approval Queue** ✅
- See all pending actions
- View AI reasoning
- Approve or reject with one click
- Track execution results

---

## 📦 What Was Created

### Backend Files:

1. **models.py** - Added `AgentAction` model
   - Stores pending actions
   - Tracks status (pending/approved/rejected/executed)
   - Stores AI reasoning and confidence

2. **agent_actions_routes.py** (NEW)
   - `/api/agent-actions/analyze-inbox` - AI inbox analysis
   - `/api/agent-actions/draft-reply` - Draft email replies
   - `/api/agent-actions/pending` - Get approval queue
   - `/api/agent-actions/<id>/approve` - Approve action
   - `/api/agent-actions/<id>/reject` - Reject action

3. **alembic/versions/004_add_agent_actions.py**
   - Database migration for agent_actions table

4. **004_add_agent_actions.sql**
   - SQL migration for Neon database

### Frontend Files:

5. **dashboard.html** - Added Actions tab
   - Approval queue UI
   - Test buttons for AI features
   - Real-time action status

6. **static/js/dashboard-main.js** - Added JavaScript functions
   - `analyzeInbox()` - Trigger inbox analysis
   - `loadPendingActions()` - Load approval queue
   - `approveAction()` - Approve and execute
   - `rejectAction()` - Reject action

---

## 🚀 Setup Instructions

### Step 1: Run Database Migration

Go to [Neon SQL Editor](https://console.neon.tech/) and run:

[View SQL migration](computer:///sessions/focused-keen-keller/mnt/clawd/004_add_agent_actions.sql)

```sql
-- Copy and paste the SQL from the file above
```

### Step 2: Get Anthropic API Key

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Create an API key
3. Copy it (starts with `sk-ant-...`)

### Step 3: Add API Key to Vercel

```bash
# In your terminal:
vercel env add ANTHROPIC_API_KEY

# When prompted:
# - Value: <paste your API key>
# - Environments: Production, Preview, Development
```

**Or** add it via Vercel Dashboard:
1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Select your project
3. Settings → Environment Variables
4. Add: `ANTHROPIC_API_KEY` = `sk-ant-your-key-here`

### Step 4: Commit and Deploy

```bash
cd /Users/juanmac/Public/clawd
git add .
git commit -m "Add AI Agent Actions with approval queue"
git push
```

Vercel will auto-deploy in ~2 minutes!

---

## 🧪 Testing the Features

### 1. Test Inbox Analysis

1. Go to https://www.greenmonkey.dev
2. Click the **✅ Actions** tab
3. Click **📊 Analyze Inbox**
4. Wait ~5 seconds for AI analysis
5. See insights about your emails!

### 2. Test Draft Reply (Coming Soon)

This feature will let you:
- Select an email from your inbox
- Click "Draft Reply"
- AI generates a professional response
- You review and approve
- Email sends only after approval

---

## 💡 How It Works

```
1. User clicks "Analyze Inbox"
   ↓
2. Backend fetches recent emails from Gmail API
   ↓
3. Sends emails to Claude API for analysis
   ↓
4. Claude analyzes and returns insights
   ↓
5. Results displayed in dashboard
```

For draft replies:
```
1. User requests draft reply
   ↓
2. AI generates reply using Claude
   ↓
3. Action added to approval queue (status: pending)
   ↓
4. User reviews in Actions tab
   ↓
5. User approves → Email sends via Gmail API
   OR
   User rejects → Action canceled
```

---

## 🔒 Security Features

✅ **Approval Required** - Agents can't send emails without your approval
✅ **AI Reasoning** - See why AI wants to take an action
✅ **Audit Trail** - All actions logged in database
✅ **Status Tracking** - Know what was approved, rejected, executed

---

## 📊 Database Schema

```sql
agent_actions table:
- id: Action ID
- user_id: Who owns this action
- agent_id: Which agent proposed it
- action_type: 'send_email', 'categorize', etc.
- service_type: 'gmail', 'calendar', etc.
- status: 'pending', 'approved', 'rejected', 'executed', 'failed'
- action_data: JSON with action parameters
- ai_reasoning: Why AI wants to do this
- ai_confidence: 0-1 confidence score
- result_data: Execution results
- created_at, approved_at, executed_at: Timestamps
```

---

## 🎨 Next Steps

### Phase 2: More AI Actions

1. **Email Categorization** 📁
   - AI auto-categorizes emails
   - Suggests folder/label assignments
   - Bulk operations with approval

2. **Smart Replies** 💬
   - Context-aware responses
   - Learns from your writing style
   - Handles common requests automatically

3. **Calendar Integration** 📅
   - Extract meeting times from emails
   - Auto-schedule with approval
   - Send calendar invites

4. **Workflow Automation** ⚡
   - If/then rules
   - Multi-step automations
   - Smart triggers

---

## 🐛 Troubleshooting

### "No module named 'anthropic'"
```bash
pip install anthropic
# OR add to requirements.txt
```

### "ANTHROPIC_API_KEY not set"
Make sure you added it to Vercel environment variables and redeployed.

### "column agent_actions does not exist"
Run the SQL migration in Neon SQL Editor (Step 1 above).

---

## 🎉 You're All Set!

Your AI agents can now:
- ✅ Analyze your inbox
- ✅ Draft professional replies
- ✅ Propose actions for approval
- ✅ Execute approved actions

**This is just the beginning!** 🚀

The approval queue system is the foundation for all future AI automations. Now you can safely let AI help with email, calendar, tasks, and more - all with your explicit approval.
