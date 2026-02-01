#!/bin/bash

echo "🚀 Updating GitHub Repository"
echo "=============================="
echo ""

# Remove lock file if it exists
if [ -f ".git/index.lock" ]; then
    echo "Removing git lock file..."
    rm -f .git/index.lock
fi

# Check git status
echo "Current status:"
git status --short
echo ""

# Stage all changes
echo "Staging all changes..."
git add .

# Show what will be committed
echo ""
echo "Files to be committed:"
git status --short
echo ""

# Verify sensitive files are NOT being committed
echo "⚠️  Verifying sensitive files are excluded..."
if git status --short | grep -E "(USER.md|LLM_CONFIG.md|SECURITY.md)$"; then
    echo "❌ ERROR: Sensitive files detected!"
    echo "   USER.md, LLM_CONFIG.md, and SECURITY.md should NOT be committed"
    echo "   Check your .gitignore file"
    exit 1
else
    echo "✅ Sensitive files properly excluded"
fi
echo ""

# Create commit
echo "Creating commit..."
git commit -m "Add Security & Safety features with optional guardrails

- Added Security & Safety tab to dashboard
- Session isolation controls (per-peer, per-account)
- External action confirmations (emails, posts, messages)
- Tool restrictions (web, files, code execution)
- Privacy controls (no external logging, API key protection)
- Model safety settings (minimum size, sandboxing)
- Group chat safety features
- Updated documentation and examples
- Modern UI improvements"

# Push to GitHub
echo ""
echo "Pushing to GitHub..."
git push origin main

echo ""
echo "✅ Done! Your repository is updated."
echo ""
echo "View it at: https://github.com/dchosenjuan1/openclaw-dashboard"
echo ""
