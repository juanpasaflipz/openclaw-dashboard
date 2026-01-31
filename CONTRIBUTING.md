# Contributing to OpenClaw Dashboard

Thank you for your interest in contributing! This document provides guidelines for contributing to the OpenClaw Dashboard project.

## 🤝 How to Contribute

### Reporting Bugs

If you find a bug:

1. Check if the issue already exists in [GitHub Issues](../../issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots if applicable
   - Your environment (OS, Python version, browser)

### Suggesting Features

We welcome feature suggestions! Please:

1. Check existing issues and discussions
2. Create a new issue with the `enhancement` label
3. Describe the feature and its use case
4. Explain why it would benefit the community

### Pull Requests

1. **Fork the repository**
   ```bash
   git clone https://github.com/yourusername/openclaw-dashboard.git
   cd openclaw-dashboard
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow the existing code style
   - Add comments for complex logic
   - Test your changes thoroughly

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "Add: Brief description of your changes"
   ```

   Commit message format:
   - `Add:` for new features
   - `Fix:` for bug fixes
   - `Update:` for improvements to existing features
   - `Docs:` for documentation changes
   - `Style:` for formatting changes

5. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request**
   - Provide a clear description of the changes
   - Reference any related issues
   - Include screenshots for UI changes

## 🎨 Code Style

### Python (server.py)
- Follow PEP 8 guidelines
- Use meaningful variable names
- Add docstrings to functions
- Keep functions focused and small

### HTML/CSS/JavaScript (dashboard.html)
- Use consistent indentation (4 spaces)
- Comment complex CSS or JavaScript logic
- Keep JavaScript functions modular
- Use semantic HTML elements

## 🧪 Testing

Before submitting a PR:

1. Test the dashboard in multiple browsers
2. Verify all forms save correctly
3. Check responsive design on mobile
4. Test with and without the server running
5. Ensure no console errors

## 📝 Documentation

When adding features:

- Update README.md if needed
- Add comments to explain complex code
- Update DASHBOARD_SETUP.md for setup changes
- Include example usage in PR description

## 🔒 Security

**Never commit sensitive data:**
- API keys
- Personal information
- Credentials

If you accidentally commit sensitive data:
1. Remove it immediately
2. Rotate any exposed credentials
3. Notify the maintainers

## 💡 Development Tips

### Running in Development

```bash
# Enable Flask debug mode (auto-reload)
export FLASK_ENV=development
python3 server.py
```

### Testing the Dashboard

1. Clear browser cache and localStorage
2. Test the full configuration flow
3. Verify file saves work correctly
4. Check error handling

### Adding New LLM Providers

To add a new provider:

1. Add to `PROVIDER_MODELS` object in `dashboard.html`
2. Add provider card in the HTML
3. Update documentation

## 🌟 Good First Issues

Look for issues labeled `good first issue` - these are great starting points for new contributors!

## 📬 Questions?

Feel free to:
- Open a discussion on GitHub
- Comment on existing issues
- Reach out to maintainers

## 🙏 Thank You!

Every contribution, big or small, is appreciated. Thank you for helping make OpenClaw Dashboard better!
