# 🦅 OpenClaw Dashboard

A beautiful, modern web dashboard for configuring your personalized AI agent. OpenClaw is a framework for creating AI agents with persistent memory, customized behavior, and LLM connectivity.

![Dashboard Preview](https://via.placeholder.com/1200x600/667eea/ffffff?text=OpenClaw+Dashboard)

## ✨ Features

- 🎨 **Modern UI** - Sleek design with glassmorphism effects and smooth animations
- 🔌 **LLM Connection** - Connect to Anthropic Claude, OpenAI, OpenRouter, Ollama, or custom providers
- 🤖 **AI Identity Configuration** - Define your AI's name, personality, and behavior
- 👤 **User Profile Management** - Store information about yourself for personalized interactions
- 💜 **Soul & Behavior** - Customize core behavioral guidelines
- 🛠️ **Tools Setup** - Configure environment-specific settings
- 🔒 **Security & Safety** - Optional guardrails for privacy protection and action confirmations
- 💾 **Auto-Save** - All configurations saved to markdown files
- 📱 **Responsive** - Works on desktop, tablet, and mobile

## 🚀 Quick Start

### Prerequisites

- Python 3.7+
- pip

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/openclaw-dashboard.git
cd openclaw-dashboard
```

2. **Install dependencies**
```bash
pip3 install --user -r requirements.txt
```

Or install manually:
```bash
pip3 install --user Flask flask-cors
```

3. **Start the server**
```bash
./start-dashboard.sh
```

Or manually:
```bash
python3 server.py
```

4. **Open your browser**

Navigate to **http://localhost:5000**

## 📖 Usage Guide

### 1. Configure LLM Connection

Choose your AI provider and configure your API credentials:

- **Anthropic Claude** - For advanced reasoning and long context
- **OpenAI** - GPT-4, GPT-3.5 Turbo
- **OpenRouter** - Access multiple providers through one API
- **Ollama** - Run models locally
- **Custom** - Any OpenAI-compatible API

### 2. Set AI Identity

Define your AI agent's personality:
- **Name** - What to call your AI
- **Creature Type** - AI assistant, digital familiar, etc.
- **Vibe** - Personality traits (warm, witty, professional)
- **Emoji** - Signature emoji
- **Avatar** - Optional image

### 3. Add User Information

Tell your AI about yourself:
- Name and preferred nickname
- Pronouns and timezone
- Interests and preferences
- Context about your work

### 4. Customize Behavior

Edit the Soul & Behavior guidelines to define how your AI should act. The defaults are thoughtfully crafted, but you can customize them to your needs.

### 5. Configure Tools

Add environment-specific notes:
- Camera names and locations
- SSH hosts and aliases
- Preferred TTS voices
- Device nicknames

### 6. Set Security & Safety Guardrails

Configure optional safety settings to protect your privacy:
- **Session Isolation** - Separate sessions per contact to prevent context leakage
- **Action Confirmations** - Require approval before sending emails, posts, or messages
- **Tool Restrictions** - Limit web browsing, file operations, or code execution
- **Data Privacy** - Prevent external logging and API key exposure
- **Model Safety** - Set minimum model sizes and enable sandboxing
- **Group Chat Safety** - Protect private data in group contexts

## 📁 Configuration Files

All settings are saved as markdown files in your directory:

- `LLM_CONFIG.md` - AI provider and API credentials
- `IDENTITY.md` - AI personality and identity
- `USER.md` - Your information and preferences
- `SOUL.md` - Behavioral guidelines
- `TOOLS.md` - Environment-specific settings
- `SECURITY.md` - Safety guardrails and privacy settings

## 🔒 Security

**Important:** Never commit sensitive files to version control!

The `.gitignore` file excludes:
- `LLM_CONFIG.md` (contains API keys)
- `USER.md` (personal information)
- Any `*.env` files

### Security Features

The dashboard includes optional safety guardrails:

- **Session Isolation** - Prevent context leakage between different conversations
- **External Action Confirmations** - Require approval before emails, posts, or API calls
- **Tool Restrictions** - Sandbox or disable potentially risky operations
- **Privacy Protection** - Prevent logging and credential exposure
- **Model Safety Warnings** - Alert when using small models without sandboxing

Based on [OpenClaw security best practices](https://docs.openclaw.ai/cli/security)

Always keep your API keys secure and never share them publicly.

## 🛠️ Development

### Project Structure

```
openclaw-dashboard/
├── dashboard.html          # Main UI dashboard
├── server.py              # Flask backend server
├── start-dashboard.sh     # Launch script
├── requirements.txt       # Python dependencies
├── DASHBOARD_SETUP.md     # Detailed setup guide
├── IDENTITY.md           # AI identity (template)
├── USER.md               # User info (template)
├── SOUL.md               # Behavior guidelines
├── TOOLS.md              # Tools configuration
├── AGENTS.md             # Agent instructions
├── BOOTSTRAP.md          # Initial setup guide
└── HEARTBEAT.md          # Proactive check-ins
```

### API Endpoints

- `GET /` - Serve dashboard
- `GET /api/config/<filename>` - Read configuration file
- `POST /api/config/<filename>` - Save configuration file

### Customization

You can customize the dashboard by editing:
- `dashboard.html` - UI and styling
- `server.py` - Backend logic and endpoints

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Flask](https://flask.palletsprojects.com/)
- UI inspired by modern design trends
- Part of the OpenClaw framework for personalized AI agents

## 💬 Support

If you encounter any issues or have questions:

- Open an issue on GitHub
- Check the [DASHBOARD_SETUP.md](DASHBOARD_SETUP.md) for detailed instructions
- Review existing issues for solutions

## 🗺️ Roadmap

- [ ] Live connection testing for LLM providers
- [ ] Dark mode toggle
- [ ] Export/import configuration bundles
- [ ] Chat interface for testing your configured agent
- [ ] Integration with messaging platforms (WhatsApp, Telegram)
- [ ] Multi-agent support

## ⭐ Star History

If you find this project useful, please consider giving it a star on GitHub!

---

**Made with ❤️ for the AI community**
