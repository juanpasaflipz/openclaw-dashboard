#!/bin/bash

echo "🔄 Switching to dchosenjuan1 GitHub Account"
echo "==========================================="
echo ""

# Set git config for this repository only
echo "Setting git configuration for this repository..."
git config user.name "dchosenjuan1"
git config user.email "d.chosen.juan.1@gmail.com"

echo "✅ Git user configured:"
echo "   Name: $(git config user.name)"
echo "   Email: $(git config user.email)"
echo ""

# Show current remote
echo "Current remote URL:"
git remote -v
echo ""

echo "To push with the correct account, you may need to:"
echo "1. Update the remote URL to use your username:"
echo "   git remote set-url origin https://github.com/dchosenjuan1/openclaw-dashboard.git"
echo ""
echo "2. Clear cached credentials (if git remembers the wrong account):"
echo "   macOS: Run in terminal outside this session:"
echo "     git credential-osxkeychain erase"
echo "     host=github.com"
echo "     protocol=https"
echo "     [Press Enter twice]"
echo ""
echo "   Or use GitHub CLI:"
echo "     gh auth login"
echo ""
echo "3. When you push, use:"
echo "   git push -u origin main"
echo ""
