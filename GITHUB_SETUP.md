# 🚀 GitHub Setup Guide

This guide will help you share your OpenClaw Dashboard on GitHub.

## 📋 Prerequisites

- GitHub account ([create one here](https://github.com/join))
- Git installed on your system
- Terminal/command line access

## 🎯 Step-by-Step Instructions

### 1. Create a New Repository on GitHub

1. Go to [github.com/new](https://github.com/new)
2. Repository name: `openclaw-dashboard` (or your preferred name)
3. Description: "A beautiful web dashboard for configuring personalized AI agents"
4. Choose **Public** (to share with others) or **Private**
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click **Create repository**

### 2. Prepare Your Local Repository

Open your terminal and navigate to the project directory:

```bash
cd /path/to/openclaw-dashboard
```

Run the setup script:

```bash
./setup-github.sh
```

Or manually:

```bash
# Remove git lock file if it exists
rm -f .git/index.lock

# Stage all files
git add .

# Check what will be committed
git status
```

**IMPORTANT:** Verify that `USER.md` and `LLM_CONFIG.md` are NOT listed (they should be ignored).

### 3. Create Initial Commit

```bash
git commit -m "Initial commit: OpenClaw Dashboard with modern UI and LLM connection"
```

### 4. Connect to GitHub

Replace `YOUR_USERNAME` with your actual GitHub username:

```bash
# Rename branch to main
git branch -M main

# Add remote origin
git remote add origin https://github.com/YOUR_USERNAME/openclaw-dashboard.git

# Push to GitHub
git push -u origin main
```

### 5. Verify on GitHub

1. Go to your repository: `https://github.com/YOUR_USERNAME/openclaw-dashboard`
2. Verify all files are there
3. **Double-check:** Ensure `USER.md` and `LLM_CONFIG.md` are NOT present
4. Check that README.md displays correctly

## ✅ Post-Upload Checklist

- [ ] README.md displays properly on GitHub
- [ ] No sensitive files (USER.md, LLM_CONFIG.md) are committed
- [ ] License file is present
- [ ] .gitignore is working correctly
- [ ] Start script is executable (`chmod +x start-dashboard.sh`)

## 🎨 Customize Your Repository

### Add Topics/Tags

On your GitHub repository page:
1. Click ⚙️ (settings gear) next to "About"
2. Add topics: `ai`, `dashboard`, `llm`, `python`, `flask`, `anthropic`, `openai`, `claude`
3. Add description and website if you have one
4. Save changes

### Add a Repository Description

In the "About" section, add:
> A beautiful, modern web dashboard for configuring personalized AI agents with LLM connectivity and persistent memory.

### Enable GitHub Pages (Optional)

If you want to host the dashboard on GitHub Pages:
1. Go to Settings → Pages
2. Source: Deploy from branch
3. Branch: main, folder: / (root)
4. Save

**Note:** This will only host the static HTML. Users will still need to run the Python server locally for full functionality.

## 🔄 Updating Your Repository

After making changes:

```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "Add: Description of your changes"

# Push to GitHub
git push
```

## 🌟 Share Your Work

- Share the repository link on social media
- Post on Reddit (r/LocalLLaMA, r/SelfHosted)
- Tweet about it with #AI #OpenSource
- Add to awesome lists

## 🐛 Troubleshooting

### "Permission denied" when removing lock file

```bash
# Try with sudo (macOS/Linux)
sudo rm -f .git/index.lock

# Or delete manually in Finder/File Explorer
```

### "Repository already exists"

The repository name is taken. Choose a different name:
- `openclaw-config-dashboard`
- `ai-agent-dashboard`
- `llm-config-ui`

### Accidentally committed sensitive files

If you accidentally committed USER.md or LLM_CONFIG.md:

1. **Remove from git history:**
```bash
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch USER.md LLM_CONFIG.md" \
  --prune-empty --tag-name-filter cat -- --all
```

2. **Force push:**
```bash
git push origin --force --all
```

3. **Rotate any exposed API keys immediately!**

## 📞 Need Help?

- Check GitHub's [documentation](https://docs.github.com/)
- Open an issue in your repository
- Ask in GitHub Discussions

---

**Good luck sharing your project! 🎉**
