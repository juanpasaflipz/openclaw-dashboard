#!/usr/bin/env python3
"""
OpenClaw Dashboard Server
A simple Flask server to manage OpenClaw configuration files
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import os
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Base directory for OpenClaw files
BASE_DIR = Path(__file__).parent

@app.route('/')
def index():
    """Serve the dashboard"""
    return send_file('dashboard.html')

@app.route('/api/config/<filename>', methods=['GET'])
def get_config(filename):
    """Read a configuration file"""
    try:
        # Only allow specific files for security
        allowed_files = ['IDENTITY.md', 'USER.md', 'SOUL.md', 'TOOLS.md', 'HEARTBEAT.md', 'LLM_CONFIG.md']

        if filename not in allowed_files:
            return jsonify({'error': 'File not allowed'}), 403

        filepath = BASE_DIR / filename

        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({'content': content, 'exists': True})
        else:
            return jsonify({'content': '', 'exists': False})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/<filename>', methods=['POST'])
def save_config(filename):
    """Save a configuration file"""
    try:
        # Only allow specific files for security
        allowed_files = ['IDENTITY.md', 'USER.md', 'SOUL.md', 'TOOLS.md', 'HEARTBEAT.md', 'LLM_CONFIG.md']

        if filename not in allowed_files:
            return jsonify({'error': 'File not allowed'}), 403

        data = request.get_json()
        content = data.get('content', '')

        filepath = BASE_DIR / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return jsonify({'success': True, 'message': f'{filename} saved successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get configuration status"""
    try:
        files = ['IDENTITY.md', 'USER.md', 'SOUL.md', 'TOOLS.md']
        status = {}

        for filename in files:
            filepath = BASE_DIR / filename

            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Simple heuristic: file is configured if it has more than template content
                    is_configured = len(content) > 200 and not content.startswith('# IDENTITY.md - Who Am I?\n\n*Fill this in')
                    status[filename] = {
                        'exists': True,
                        'configured': is_configured,
                        'size': len(content)
                    }
            else:
                status[filename] = {
                    'exists': False,
                    'configured': False,
                    'size': 0
                }

        return jsonify(status)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🦅 OpenClaw Dashboard Server")
    print("=" * 60)
    print(f"Base directory: {BASE_DIR}")
    print("Server starting on http://localhost:5000")
    print("Open your browser and navigate to: http://localhost:5000")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=True)
