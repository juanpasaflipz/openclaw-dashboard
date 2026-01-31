# OpenClaw Dashboard Setup Guide

## What is the Dashboard?

The OpenClaw Dashboard is a user-friendly web interface that makes it easy to configure your personalized AI agent without manually editing markdown files.

## Quick Start

### 1. Install Dependencies

Install the required Python packages:

```bash
pip3 install --user Flask flask-cors
```

Or using the requirements file:

```bash
pip3 install --user -r requirements.txt
```

**Note**: If you see a PATH warning, add this to your shell profile:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 2. Start the Server

Run the dashboard server:

```bash
python3 server.py
```

You should see:
```
============================================================
🦅 OpenClaw Dashboard Server
============================================================
Base directory: /path/to/openclaw
Server starting on http://localhost:5000
Open your browser and navigate to: http://localhost:5000
============================================================
```

### 3. Open in Browser

Navigate to **http://localhost:5000** in your web browser.

## Using the Dashboard

The dashboard has several tabs:

### 📊 Overview
- See your configuration progress
- Quick access to start setup

### 🦅 Identity
Configure your AI's personality:
- **Name**: What should your AI be called?
- **Creature**: What kind of being is it?
- **Vibe**: Personality traits (warm, witty, professional, etc.)
- **Emoji**: A signature emoji
- **Avatar**: Optional image URL or path

### 👤 User Info
Tell your AI about yourself:
- Your name and preferred name
- Pronouns
- Timezone
- Notes about your preferences and interests

### 💜 Soul & Behavior
Edit the core behavioral guidelines that define how your AI acts. The defaults are well-crafted, but you can customize them to your needs.

### 🛠️ Tools & Setup
Add environment-specific notes like:
- Camera names and locations
- SSH hosts
- Preferred voices for text-to-speech
- Device nicknames

### 📤 Export Config
Preview all your generated configuration files.

## What Gets Created?

The dashboard manages these files in your OpenClaw directory:
- `IDENTITY.md` - Your AI's identity
- `USER.md` - Information about you
- `SOUL.md` - Behavioral guidelines
- `TOOLS.md` - Environment-specific settings

## Troubleshooting

### Port 5000 Already in Use

If port 5000 is already in use, you can change it in `server.py`:

```python
app.run(host='0.0.0.0', port=8000, debug=True)  # Change 5000 to 8000
```

### Server Not Accessible

Make sure your firewall allows connections on port 5000.

### Changes Not Saving

Check that you have write permissions in the OpenClaw directory.

## Next Steps

After configuring your OpenClaw setup:

1. Review the generated markdown files
2. Delete `BOOTSTRAP.md` (you don't need it anymore)
3. Follow the platform-specific integration guide from the OpenClaw documentation
4. Connect your AI to your preferred messaging platform (WhatsApp, Telegram, etc.)

---

**Need help?** Check the official OpenClaw documentation at https://docs.openclaw.ai
