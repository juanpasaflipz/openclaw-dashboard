#!/usr/bin/env python3
"""
OpenClaw Dashboard Server
A simple Flask server to manage OpenClaw configuration files
"""

from flask import Flask, jsonify, request, send_file, session
from flask_cors import CORS
import os
from pathlib import Path
import requests
from datetime import datetime
import secrets

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Secret key for sessions (generate a secure one for production)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Database configuration
database_url = os.environ.get('DATABASE_URL', f'sqlite:///{Path(__file__).parent}/openclaw.db')

# Fix Heroku/Vercel's postgres:// scheme (should be postgresql://)
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

# Fix for Neon PostgreSQL SSL issues
if database_url and database_url.startswith('postgresql://'):
    # Add SSL parameters for Neon
    if '?' not in database_url:
        database_url += '?sslmode=require'
    elif 'sslmode' not in database_url:
        database_url += '&sslmode=require'

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# PostgreSQL-specific connection pool settings
if database_url and database_url.startswith('postgresql://'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 5,
        'max_overflow': 10,
        'pool_recycle': 300,  # Recycle connections after 5 minutes
        'pool_pre_ping': True,  # Test connections before using them (fixes SSL drops)
        'pool_timeout': 30,
        'connect_args': {
            'connect_timeout': 10,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5
        }
    }
else:
    # SQLite settings (for local dev)
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True
    }

# Import and initialize database
from models import db, User, MagicLink, CreditTransaction, PostHistory, CreditPackage, ConfigFile, SubscriptionPlan, Agent, MoltbookFeedCache, UserUpvote, AnalyticsSnapshot, PostAnalytics, Superpower, AgentAction
db.init_app(app)

# Initialize rate limiter
from rate_limiter import init_limiter
limiter = init_limiter(app)

# Register authentication routes
from auth_routes import register_auth_routes
register_auth_routes(app)

# Register Stripe/payment routes
from stripe_routes import register_stripe_routes
register_stripe_routes(app)

# Register Phase 1 routes (Feed + Analytics)
from moltbook_routes import moltbook_bp
from analytics_routes import analytics_bp
app.register_blueprint(moltbook_bp)
app.register_blueprint(analytics_bp)

# Register agent management routes
from agent_routes import register_agent_routes
register_agent_routes(app)

# Register setup wizard routes
from setup_routes import register_setup_routes
register_setup_routes(app)

# Register chat channels routes
from channels_routes import register_channels_routes
register_channels_routes(app)

# Register LLM providers routes
from llm_providers_routes import register_llm_providers_routes
register_llm_providers_routes(app)

# Register OAuth routes for superpowers
from oauth_routes import register_oauth_routes
register_oauth_routes(app)

# Register Gmail routes
from gmail_routes import register_gmail_routes
register_gmail_routes(app)

# Register AI Agent Actions routes
from agent_actions_routes import register_agent_actions_routes
register_agent_actions_routes(app)

# LLM API proxy routes (to avoid CORS issues)
@app.route('/api/generate-post', methods=['POST'])
def generate_post():
    """
    Proxy endpoint for generating posts via LLM
    Avoids CORS issues by calling LLM APIs from backend
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        suggestions = data.get('suggestions', '').strip()
        llm_config = data.get('llm_config', {})
        personality = data.get('personality', 'You are a helpful AI agent')

        if not suggestions:
            return jsonify({'error': 'Suggestions are required'}), 400

        if not llm_config.get('provider') or not llm_config.get('apiKey'):
            return jsonify({'error': 'LLM configuration is required'}), 400

        # Build prompt
        prompt = f"""{personality}

You are creating a post for Moltbook (a social network for AI agents). Based on these topic suggestions from your human guide:

{suggestions}

Generate a compelling post that:
1. Addresses one or more of the suggested topics
2. Reflects your personality and voice
3. Is engaging and authentic
4. Is 200-500 words long
5. Includes a catchy title

Format your response EXACTLY as JSON:
{{
  "title": "Your catchy title here (max 100 chars)",
  "body": "Your post content here",
  "submolt": "general"
}}

Remember: Be creative and authentic. This is YOUR voice, not just following instructions."""

        # Call appropriate LLM
        provider = llm_config.get('provider')

        if provider == 'anthropic':
            result = call_anthropic_api(prompt, llm_config)
        elif provider == 'openai':
            result = call_openai_api(prompt, llm_config)
        else:
            return jsonify({'error': f'Unsupported LLM provider: {provider}'}), 400

        return jsonify(result)

    except Exception as e:
        print(f"❌ Error generating post: {e}")
        return jsonify({'error': str(e)}), 500

def call_anthropic_api(prompt, llm_config):
    """Call Anthropic API"""
    import requests

    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'Content-Type': 'application/json',
            'x-api-key': llm_config['apiKey'],
            'anthropic-version': '2023-06-01'
        },
        json={
            'model': llm_config.get('model', 'claude-3-5-sonnet-20241022'),
            'max_tokens': 1024,
            'messages': [{
                'role': 'user',
                'content': prompt
            }]
        },
        timeout=30
    )

    if not response.ok:
        raise Exception(f'Anthropic API error: {response.text}')

    data = response.json()
    content = data['content'][0]['text']

    # Extract JSON from response
    import re
    json_match = re.search(r'\{[\s\S]*\}', content)
    if not json_match:
        raise Exception('LLM did not return valid JSON')

    import json
    return json.loads(json_match.group(0))

def call_openai_api(prompt, llm_config):
    """Call OpenAI API"""
    import requests

    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {llm_config["apiKey"]}'
        },
        json={
            'model': llm_config.get('model', 'gpt-4'),
            'messages': [{
                'role': 'user',
                'content': prompt
            }],
            'temperature': llm_config.get('temperature', 0.7)
        },
        timeout=30
    )

    if not response.ok:
        raise Exception(f'OpenAI API error: {response.text}')

    data = response.json()
    content = data['choices'][0]['message']['content']

    # Extract JSON from response
    import re
    json_match = re.search(r'\{[\s\S]*\}', content)
    if not json_match:
        raise Exception('LLM did not return valid JSON')

    import json
    return json.loads(json_match.group(0))

# Base directory for OpenClaw files
BASE_DIR = Path(__file__).parent

@app.route('/')
def index():
    """Serve the dashboard"""
    return send_file('dashboard.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify database connection"""
    try:
        # Test database connection
        db.session.execute(db.text('SELECT 1'))
        db.session.commit()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503

@app.route('/api/config/<filename>', methods=['GET'])
def get_config(filename):
    """Read a configuration file from database"""
    try:
        # Only allow specific files for security
        allowed_files = ['IDENTITY.md', 'USER.md', 'SOUL.md', 'TOOLS.md', 'HEARTBEAT.md', 'LLM_CONFIG.md', 'SECURITY.md', 'MOLTBOOK_CONFIG.md']

        if filename not in allowed_files:
            return jsonify({'error': 'File not allowed'}), 403

        # Get user_id from session (or use default user for backward compatibility)
        user_id = session.get('user_id', 1)  # Default to user 1 if not logged in

        # Try to get from database first
        config = ConfigFile.query.filter_by(user_id=user_id, filename=filename).first()

        if config:
            return jsonify({'content': config.content, 'exists': True})

        # Fallback: try to read from filesystem (for local development / migration)
        filepath = BASE_DIR / filename
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({'content': content, 'exists': True})

        # File doesn't exist in DB or filesystem
        return jsonify({'content': '', 'exists': False})

    except Exception as e:
        print(f"❌ Error in get_config: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/<filename>', methods=['POST'])
def save_config(filename):
    """Save a configuration file to database"""
    try:
        # Only allow specific files for security
        allowed_files = ['IDENTITY.md', 'USER.md', 'SOUL.md', 'TOOLS.md', 'HEARTBEAT.md', 'LLM_CONFIG.md', 'SECURITY.md', 'MOLTBOOK_CONFIG.md']

        if filename not in allowed_files:
            return jsonify({'error': 'File not allowed'}), 403

        data = request.get_json()
        content = data.get('content', '')

        # Get user_id from session (or use default user)
        user_id = session.get('user_id')

        if not user_id:
            # If not logged in, create a default user or return error
            # For now, create/use default user with ID 1
            user = User.query.get(1)
            if not user:
                user = User(id=1, email='default@openclaw.local', credit_balance=0)
                db.session.add(user)
                db.session.commit()
            user_id = 1

        # Find existing config or create new one
        config = ConfigFile.query.filter_by(user_id=user_id, filename=filename).first()

        if config:
            config.content = content
            config.updated_at = datetime.utcnow()
        else:
            config = ConfigFile(user_id=user_id, filename=filename, content=content)
            db.session.add(config)

        db.session.commit()

        print(f"✅ Saved {filename} to database for user {user_id}")
        return jsonify({'success': True, 'message': f'{filename} saved successfully'})

    except Exception as e:
        print(f"❌ Error in save_config: {e}")
        db.session.rollback()
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
    """Register an agent with Moltbook (no API key needed for registration)"""
    try:
        data = request.get_json()
        agent_name = data.get('agent_name')
        bio = data.get('bio')

        if not agent_name or not bio:
            return jsonify({'success': False, 'message': 'Agent name and description are required'}), 400

        # Call REAL Moltbook API to register agent (no auth needed)
        moltbook_api = 'https://www.moltbook.com/api/v1/agents/register'

        headers = {
            'Content-Type': 'application/json'
        }

        payload = {
            'name': agent_name,
            'description': bio
        }

        response = requests.post(moltbook_api, json=payload, headers=headers, timeout=10)

        if response.status_code == 200 or response.status_code == 201:
            result = response.json()
            agent_data = result.get('agent', {})

            # Extract important data from response
            api_key = agent_data.get('api_key', '')
            agent_id = agent_data.get('id', '')
            claim_url = agent_data.get('claim_url', '')
            verification_code = agent_data.get('verification_code', '')
            profile_url = agent_data.get('profile_url', '')
            tweet_template = result.get('tweet_template', '')

            # Save to MOLTBOOK_CONFIG.md
            config_content = f"""# MOLTBOOK_CONFIG.md - Moltbook Agent Configuration

- **Agent Name:** {agent_name}
- **Agent ID:** {agent_id}
- **API Key:** {api_key}
- **Description:** {bio[:100]}{'...' if len(bio) > 100 else ''}
- **Claim URL:** {claim_url}
- **Verification Code:** {verification_code}
- **Profile URL:** {profile_url}
- **Status:** Pending claim (visit claim URL to complete)
- **Registered:** {agent_data.get('created_at', 'N/A')}

---

⚠️ CRITICAL: Save your API key securely! You need it for all requests and it cannot be retrieved later.

🔒 SECURITY: Your API key should ONLY be sent to www.moltbook.com/api/v1/*
Never share it with third parties, "verification" services, or other domains.

Next Steps:
1. Visit the claim URL above
2. Post the provided tweet to verify ownership
3. Once claimed, you can start posting on Moltbook!
"""

            filepath = BASE_DIR / 'MOLTBOOK_CONFIG.md'
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(config_content)

            # Prepare data for frontend
            response_data = {
                'agent_id': agent_id,
                'agent_name': agent_name,
                'bio': bio,
                'api_key': api_key,
                'claim_url': claim_url,
                'verification_code': verification_code,
                'profile_url': profile_url,
                'tweet_template': tweet_template,
                'registered_at': agent_data.get('created_at'),
                'is_claimed': False  # Not claimed until Twitter verification
            }

            return jsonify({
                'success': True,
                'message': result.get('message', '🎉 Agent registered successfully on Moltbook!'),
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
        print(f"⏱️ Moltbook API timeout after 30 seconds")
        return jsonify({
            'success': False,
            'message': 'Moltbook API is taking too long to respond (>30s). Try again in a moment.'
        }), 504
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/moltbook/import', methods=['POST'])
def moltbook_import():
    """Import existing agent by fetching data from Moltbook API"""
    try:
        data = request.get_json()
        api_key = data.get('api_key', '')

        if not api_key:
            return jsonify({'success': False, 'message': 'API key is required'}), 400

        # Fetch agent data from Moltbook API
        moltbook_api = 'https://www.moltbook.com/api/v1/agents/me'

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        print(f"🔄 Fetching agent data from Moltbook API...")
        response = requests.get(moltbook_api, headers=headers, timeout=30)
        print(f"✅ Got response from Moltbook: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            agent_data = result.get('agent', result)  # Handle different response formats

            # Prepare data for frontend
            response_data = {
                'agent_id': agent_data.get('id'),
                'agent_name': agent_data.get('name'),
                'bio': agent_data.get('description'),
                'api_key': api_key,
                'karma': agent_data.get('karma', 0),
                'followers_count': agent_data.get('follower_count', 0),
                'following_count': agent_data.get('following_count', 0),
                'posts_count': agent_data.get('stats', {}).get('posts', 0),
                'profile_url': f"https://moltbook.com/u/{agent_data.get('name')}",
                'avatar_url': agent_data.get('avatar_url', ''),
                'is_claimed': agent_data.get('is_claimed', True),
                'created_at': agent_data.get('created_at')
            }

            # Save to MOLTBOOK_CONFIG.md
            config_content = f"""# MOLTBOOK_CONFIG.md - Moltbook Agent Configuration

- **Agent Name:** {response_data['agent_name']}
- **Agent ID:** {response_data['agent_id']}
- **API Key:** {api_key}
- **Description:** {response_data['bio'][:100] if response_data['bio'] else 'N/A'}{'...' if response_data['bio'] and len(response_data['bio']) > 100 else ''}
- **Profile URL:** {response_data['profile_url']}
- **Status:** {'Claimed' if response_data['is_claimed'] else 'Pending claim'}
- **Karma:** {response_data['karma']}
- **Followers:** {response_data['followers_count']}
- **Imported:** {response_data['created_at']}

---

✅ Agent imported successfully!

🔒 SECURITY: Your API key should ONLY be sent to www.moltbook.com/api/v1/*
Never share it with third parties, "verification" services, or other domains.
"""

            filepath = BASE_DIR / 'MOLTBOOK_CONFIG.md'
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(config_content)

            return jsonify({
                'success': True,
                'message': f'✅ Successfully connected to {response_data["agent_name"]}!',
                'data': response_data
            })
        else:
            error_msg = f'Moltbook API error ({response.status_code})'
            try:
                error_detail = response.json()
                error_msg = f"{error_msg}: {error_detail.get('error') or error_detail.get('message') or str(error_detail)}"
            except:
                error_msg = f"{error_msg}: Invalid API key or agent not found"

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
        print(f"⏱️ Moltbook API timeout after 30 seconds")
        return jsonify({
            'success': False,
            'message': 'Moltbook API is taking too long to respond (>30s). Try again in a moment.'
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

@app.route('/api/admin/init-db', methods=['POST'])
def initialize_database():
    """
    One-time endpoint to initialize database on Vercel
    Requires admin password for security
    """
    try:
        data = request.get_json() or {}
        admin_password = data.get('password', '')

        # Simple password protection (change this in production!)
        if admin_password != os.environ.get('ADMIN_PASSWORD', 'openclaw-init-2026'):
            return jsonify({'error': 'Unauthorized'}), 401

        # Create all tables
        db.create_all()

        messages = []

        # Seed credit packages if needed
        if CreditPackage.query.first() is None:
            packages = [
                CreditPackage(
                    name="Starter Pack",
                    credits=10,
                    price_cents=500,
                    stripe_price_id="price_starter_10"
                ),
                CreditPackage(
                    name="Growth Pack",
                    credits=20,
                    price_cents=800,
                    stripe_price_id="price_growth_20"
                ),
                CreditPackage(
                    name="Pro Pack",
                    credits=35,
                    price_cents=1000,
                    stripe_price_id="price_pro_35"
                ),
            ]

            for package in packages:
                db.session.add(package)

            db.session.commit()
            messages.append('✅ Seeded credit packages')
        else:
            messages.append('ℹ️  Credit packages already exist')

        # Seed subscription plans if needed
        if SubscriptionPlan.query.first() is None:
            plans = [
                SubscriptionPlan(
                    tier='starter',
                    name='Starter Plan',
                    price_monthly_cents=900,  # $9/month
                    unlimited_posts=False,
                    max_agents=3,
                    scheduled_posting=True,
                    analytics=True,
                    api_access=False,
                    team_members=1,
                    priority_support=False
                ),
                SubscriptionPlan(
                    tier='pro',
                    name='Pro Plan',
                    price_monthly_cents=2900,  # $29/month
                    unlimited_posts=True,  # Note: Moltbook has 30-min limit for all users
                    max_agents=5,
                    scheduled_posting=True,
                    analytics=True,
                    api_access=True,
                    team_members=1,
                    priority_support=True
                ),
                SubscriptionPlan(
                    tier='team',
                    name='Team Plan',
                    price_monthly_cents=4900,  # $49/month
                    unlimited_posts=True,
                    max_agents=10,  # 10 agents for $49
                    scheduled_posting=True,
                    analytics=True,
                    api_access=True,
                    team_members=3,  # 3 team members
                    priority_support=True
                )
            ]

            for plan in plans:
                db.session.add(plan)

            db.session.commit()
            messages.append('✅ Seeded subscription plans')
        else:
            messages.append('ℹ️  Subscription plans already exist')

        return jsonify({
            'success': True,
            'message': 'Database initialization complete',
            'details': messages
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/migrate-subscription-columns', methods=['POST'])
def migrate_subscription_columns():
    """
    Migration endpoint to add subscription columns to existing users table
    Run this once to add the new subscription fields
    """
    try:
        data = request.get_json() or {}
        admin_password = data.get('password', '')

        if admin_password != os.environ.get('ADMIN_PASSWORD', 'openclaw-init-2026'):
            return jsonify({'error': 'Unauthorized'}), 401

        # Run raw SQL to add columns if they don't exist
        migration_sql = """
        DO $$
        BEGIN
            -- Add subscription_tier column if it doesn't exist
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name='users' AND column_name='subscription_tier') THEN
                ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(50) DEFAULT 'free';
                CREATE INDEX IF NOT EXISTS idx_users_subscription_tier ON users(subscription_tier);
            END IF;

            -- Add subscription_status column if it doesn't exist
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name='users' AND column_name='subscription_status') THEN
                ALTER TABLE users ADD COLUMN subscription_status VARCHAR(50) DEFAULT 'inactive';
            END IF;

            -- Add stripe_subscription_id column if it doesn't exist
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name='users' AND column_name='stripe_subscription_id') THEN
                ALTER TABLE users ADD COLUMN stripe_subscription_id VARCHAR(255) UNIQUE;
                CREATE INDEX IF NOT EXISTS idx_users_stripe_subscription_id ON users(stripe_subscription_id);
            END IF;

            -- Add subscription_expires_at column if it doesn't exist
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name='users' AND column_name='subscription_expires_at') THEN
                ALTER TABLE users ADD COLUMN subscription_expires_at TIMESTAMP;
            END IF;

            -- Add subscription_started_at column if it doesn't exist
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name='users' AND column_name='subscription_started_at') THEN
                ALTER TABLE users ADD COLUMN subscription_started_at TIMESTAMP;
            END IF;
        END $$;
        """

        # Execute the migration
        db.session.execute(db.text(migration_sql))
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Subscription columns added successfully',
            'note': 'Users table has been migrated with subscription fields'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/update-pricing', methods=['POST'])
def update_pricing():
    """
    Update subscription plan pricing in database
    Use this when changing pricing tiers
    """
    try:
        data = request.get_json() or {}
        admin_password = data.get('password', '')

        if admin_password != os.environ.get('ADMIN_PASSWORD', 'openclaw-init-2026'):
            return jsonify({'error': 'Unauthorized'}), 401

        # Update Team plan pricing from $79 to $49
        team_plan = SubscriptionPlan.query.filter_by(tier='team').first()
        if team_plan:
            team_plan.price_monthly_cents = 4900  # $49/month
            team_plan.max_agents = 10
            team_plan.team_members = 3
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Pricing updated successfully',
                'updated': {
                    'tier': 'team',
                    'old_price': '$79/month',
                    'new_price': '$49/month',
                    'max_agents': 10,
                    'team_members': 3
                }
            })
        else:
            return jsonify({'error': 'Team plan not found'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/update-stripe-ids', methods=['POST'])
def update_stripe_ids():
    """
    Update Stripe product and price IDs in subscription plans
    Use this after creating products in Stripe dashboard
    """
    try:
        data = request.get_json() or {}
        admin_password = data.get('password', '')

        if admin_password != os.environ.get('ADMIN_PASSWORD', 'openclaw-init-2026'):
            return jsonify({'error': 'Unauthorized'}), 401

        updates = []

        # Update Starter plan
        if 'starter_price_id' in data:
            starter = SubscriptionPlan.query.filter_by(tier='starter').first()
            if starter:
                starter.stripe_price_id = data['starter_price_id']
                if 'starter_product_id' in data:
                    starter.stripe_product_id = data['starter_product_id']
                updates.append('Starter')

        # Update Pro plan
        if 'pro_price_id' in data:
            pro = SubscriptionPlan.query.filter_by(tier='pro').first()
            if pro:
                pro.stripe_price_id = data['pro_price_id']
                if 'pro_product_id' in data:
                    pro.stripe_product_id = data['pro_product_id']
                updates.append('Pro')

        # Update Team plan
        if 'team_price_id' in data:
            team = SubscriptionPlan.query.filter_by(tier='team').first()
            if team:
                team.stripe_price_id = data['team_price_id']
                if 'team_product_id' in data:
                    team.stripe_product_id = data['team_product_id']
                updates.append('Team')

        if updates:
            db.session.commit()
            return jsonify({
                'success': True,
                'message': f'Updated Stripe IDs for: {", ".join(updates)}',
                'updated_plans': updates
            })
        else:
            return jsonify({'error': 'No price IDs provided'}), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/run-migrations', methods=['POST'])
def run_migrations():
    """
    Run database migrations remotely via API
    Adds is_admin column and creates agents table if needed
    """
    try:
        data = request.get_json() or {}
        admin_password = data.get('password', '')

        if admin_password != os.environ.get('ADMIN_PASSWORD', 'openclaw-init-2026'):
            return jsonify({'error': 'Unauthorized'}), 401

        migrations_run = []

        # Check and add is_admin column
        try:
            result = db.session.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='users' AND column_name='is_admin'"
            )

            if not result.fetchone():
                print("📝 Adding is_admin column to users table...")
                db.session.execute(
                    "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"
                )
                db.session.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin)"
                )
                migrations_run.append('Added is_admin column')

                # Promote owner email to admin
                owner_email = os.environ.get('OWNER_EMAIL', '').strip().lower()
                if owner_email:
                    db.session.execute(
                        "UPDATE users SET is_admin = TRUE WHERE email = :email",
                        {'email': owner_email}
                    )
                    migrations_run.append(f'Promoted {owner_email} to admin')
            else:
                migrations_run.append('is_admin column already exists')
        except Exception as e:
            print(f"⚠️ is_admin migration: {e}")

        # Create agents table if it doesn't exist
        try:
            from models import Agent
            db.create_all()  # This only creates missing tables
            migrations_run.append('Ensured agents table exists')
        except Exception as e:
            print(f"⚠️ agents table migration: {e}")

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Migrations completed',
            'migrations_run': migrations_run
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Migration error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🦞 OpenClaw Dashboard Server")
    print("=" * 60)
    print(f"Base directory: {BASE_DIR}")
    print("Server starting on http://localhost:5000")
    print("Open your browser and navigate to: http://localhost:5000")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=True)
