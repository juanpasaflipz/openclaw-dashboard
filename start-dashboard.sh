#!/bin/bash

# OpenClaw Dashboard Launcher
# This script starts the configuration dashboard

echo "🦅 Starting OpenClaw Dashboard..."
echo ""

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "❌ Flask is not installed!"
    echo ""
    echo "Installing dependencies..."
    pip3 install --user Flask flask-cors
    echo ""
fi

# Add local bin to PATH if needed
export PATH="$HOME/.local/bin:$PATH"

# Start the server
cd "$(dirname "$0")"
echo "✅ Server starting on http://localhost:5000"
echo "📝 Press Ctrl+C to stop the server"
echo ""

python3 server.py
