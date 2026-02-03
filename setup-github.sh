#!/bin/bash

echo "🦞 OpenClaw Dashboard - GitHub Setup"
echo "======================================"
echo ""

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "Initializing git repository..."
    git init
fi

# Remove lock file if it exists
if [ -f ".git/index.lock" ]; then
    echo "Removing git lock file..."
    rm -f .git/index.lock
fi

# Stage all files
echo "Staging files..."
git add .

# Show what will be committed
echo ""
echo "Files to be committed:"
git status --short

echo ""
echo "Ready to commit! Run these commands:"
echo ""
echo "  git commit -m 'Initial commit: OpenClaw Dashboard'"
echo "  git branch -M main"
echo "  git remote add origin https://github.com/YOUR_USERNAME/openclaw-dashboard.git"
echo "  git push -u origin main"
echo ""
echo "Don't forget to:"
echo "  1. Create a new repository on GitHub first"
echo "  2. Replace YOUR_USERNAME with your GitHub username"
echo "  3. Make sure USER.md and LLM_CONFIG.md are NOT being committed (they're in .gitignore)"
echo ""
