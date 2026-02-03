#!/usr/bin/env python3
"""
OpenClaw Dashboard Server
A simple Flask server to manage OpenClaw configuration files
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import os
from pathlib import Path
import requests

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
        allowed_files = ['IDENTITY.md', 'USER.md', 'SOUL.md', 'TOOLS.md', 'HEARTBEAT.md', 'LLM_CONFIG.md', 'SECURITY.md', 'MOLTBOOK_CONFIG.md']

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
        allowed_files = ['IDENTITY.md', 'USER.md', 'SOUL.md', 'TOOLS.md', 'HEARTBEAT.md', 'LLM_CONFIG.md', 'SECURITY.md', 'MOLTBOOK_CONFIG.md']

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

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test LLM connection"""
    try:
        data = request.get_json()
        provider = data.get('provider')
        base_url = data.get('baseUrl')
        model = data.get('model')
        api_key = data.get('apiKey')

        if provider == 'ollama':
            # Test Ollama connection
            url = base_url or 'http://localhost:11434'

            try:
                # Check if Ollama is running
                response = requests.get(f'{url}/api/tags', timeout=5)

                if response.status_code == 200:
                    tags_data = response.json()
                    models = [m['name'] for m in tags_data.get('models', [])]

                    # Check if the specific model exists
                    if model and model in models:
                        return jsonify({
                            'success': True,
                            'message': f'✅ Connected! Found model: {model}',
                            'models': models
                        })
                    elif model:
                        return jsonify({
                            'success': False,
                            'message': f'❌ Ollama is running, but model "{model}" not found. Available: {", ".join(models[:3])}...',
                            'models': models
                        })
                    else:
                        return jsonify({
                            'success': True,
                            'message': f'✅ Ollama is running! Found {len(models)} models.',
                            'models': models
                        })
                else:
                    return jsonify({
                        'success': False,
                        'message': f'❌ Ollama responded with error: {response.status_code}'
                    })

            except requests.exceptions.ConnectionError:
                return jsonify({
                    'success': False,
                    'message': f'❌ Cannot connect to Ollama at {url}. Is it running? Try: ollama serve'
                })
            except requests.exceptions.Timeout:
                return jsonify({
                    'success': False,
                    'message': '❌ Connection timeout. Ollama might be starting up...'
                })

        elif provider == 'anthropic':
            # Test Anthropic API
            if not api_key:
                return jsonify({'success': False, 'message': '❌ API key required for Anthropic'})

            try:
                # Simple ping to check API key validity
                headers = {
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                }
                # We won't actually call the API to avoid costs, just validate format
                if api_key.startswith('sk-ant-'):
                    return jsonify({
                        'success': True,
                        'message': '✅ API key format looks valid! (Not verified with Anthropic to avoid costs)'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '❌ API key should start with "sk-ant-"'
                    })
            except Exception as e:
                return jsonify({'success': False, 'message': f'❌ Error: {str(e)}'})

        elif provider == 'openai':
            # Test OpenAI API
            if not api_key:
                return jsonify({'success': False, 'message': '❌ API key required for OpenAI'})

            # Validate key format
            if api_key.startswith('sk-'):
                return jsonify({
                    'success': True,
                    'message': '✅ API key format looks valid! (Not verified with OpenAI to avoid costs)'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '❌ API key should start with "sk-"'
                })

        else:
            return jsonify({
                'success': True,
                'message': f'✅ Configuration saved for {provider}. Cannot test connection for this provider yet.'
            })

    except Exception as e:
        return jsonify({'success': False, 'message': f'❌ Error: {str(e)}'})

@app.route('/api/moltbook/register', methods=['POST'])
def moltbook_register():
    """Register an agent with Moltbook"""
    try:
        data = request.get_json()
        api_key = data.get('api_key', '')
        agent_name = data.get('agent_name')
        bio = data.get('bio')

        if not api_key:
            return jsonify({'success': False, 'message': 'Moltbook API key is required'}), 400

        if not agent_name or not bio:
            return jsonify({'success': False, 'message': 'Agent name and description are required'}), 400

        # Call REAL Moltbook API to register agent
        moltbook_api = 'https://www.moltbook.com/api/v1/agents/register'

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'name': agent_name,
            'description': bio
        }

        response = requests.post(moltbook_api, json=payload, headers=headers, timeout=10)

        if response.status_code == 200 or response.status_code == 201:
            result = response.json()

            # Save to MOLTBOOK_CONFIG.md
            config_content = f"""# MOLTBOOK_CONFIG.md - Moltbook Agent Configuration

- **API Key:** {api_key[:20]}...{api_key[-10:] if len(api_key) > 30 else api_key}
- **Agent Name:** {agent_name}
- **Agent ID:** {result.get('id') or result.get('agent_id') or 'N/A'}
- **Description:** {bio[:100]}{'...' if len(bio) > 100 else ''}
- **Registered:** {result.get('created_at') or 'N/A'}

---

This file stores your Moltbook agent credentials.
Keep this file secure and do not share publicly.

API Response: {result}
"""

            filepath = BASE_DIR / 'MOLTBOOK_CONFIG.md'
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(config_content)

            # Prepare data for frontend
            response_data = {
                'agent_id': result.get('id') or result.get('agent_id'),
                'agent_name': agent_name,
                'bio': bio,
                'api_key': api_key,
                'registered_at': result.get('created_at'),
                'is_claimed': True  # Moltbook API registers agents directly
            }

            return jsonify({
                'success': True,
                'message': '🎉 Agent registered successfully on Moltbook!',
                'data': response_data
            })
        else:
            error_msg = f'Moltbook API error ({response.status_code})'
            try:
                error_detail = response.json()
                error_msg = f"{error_msg}: {error_detail.get('error') or error_detail.get('message') or str(error_detail)}"
            except:
                error_msg = f"{error_msg}: {response.text[:200]}"

            return jsonify({
                'success': False,
                'message': error_msg
            }), response.status_code

    except requests.exceptions.ConnectionError:
        return jsonify({
            'success': False,
            'message': 'Cannot connect to Moltbook API. Please check your internet connection.'
        }), 503
    except requests.exceptions.Timeout:
        return jsonify({
            'success': False,
            'message': 'Moltbook API request timed out.'
        }), 504
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/moltbook/status', methods=['GET'])
def moltbook_status():
    """Check agent claim status"""
    try:
        agent_id = request.args.get('agent_id')

        if not agent_id:
            return jsonify({'success': False, 'message': 'Agent ID is required'}), 400

        # Call Moltbook API to check status
        moltbook_api = f'https://api.moltbook.com/v1/agents/{agent_id}/status'

        response = requests.get(moltbook_api, timeout=10)

        if response.status_code == 200:
            result = response.json()

            # Update MOLTBOOK_CONFIG.md if claimed
            if result.get('is_claimed'):
                filepath = BASE_DIR / 'MOLTBOOK_CONFIG.md'
                if filepath.exists():
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Update is_claimed status
                    content = content.replace('- **Is Claimed:** False', '- **Is Claimed:** True')

                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)

            return jsonify({
                'success': True,
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Moltbook API error: {response.status_code}'
            }), response.status_code

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/moltbook/profile', methods=['GET'])
def moltbook_profile():
    """Get agent profile"""
    try:
        agent_id = request.args.get('agent_id')

        if not agent_id:
            return jsonify({'success': False, 'message': 'Agent ID is required'}), 400

        # Call Moltbook API to get profile
        moltbook_api = f'https://api.moltbook.com/v1/agents/{agent_id}'

        response = requests.get(moltbook_api, timeout=10)

        if response.status_code == 200:
            result = response.json()

            return jsonify({
                'success': True,
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Moltbook API error: {response.status_code}'
            }), response.status_code

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/moltbook/post', methods=['POST'])
def moltbook_post():
    """Create a post on Moltbook"""
    try:
        data = request.get_json()
        agent_id = data.get('agent_id')
        content = data.get('content')

        if not agent_id or not content:
            return jsonify({'success': False, 'message': 'Agent ID and content are required'}), 400

        # Call Moltbook API to create post
        moltbook_api = 'https://api.moltbook.com/v1/posts'

        payload = {
            'agent_id': agent_id,
            'content': content
        }

        response = requests.post(moltbook_api, json=payload, timeout=10)

        if response.status_code == 200 or response.status_code == 201:
            result = response.json()

            return jsonify({
                'success': True,
                'message': 'Post created successfully!',
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Moltbook API error: {response.status_code}'
            }), response.status_code

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🦞 OpenClaw Dashboard Server")
    print("=" * 60)
    print(f"Base directory: {BASE_DIR}")
    print("Server starting on http://localhost:5000")
    print("Open your browser and navigate to: http://localhost:5000")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=True)
