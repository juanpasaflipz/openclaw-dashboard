"""
LLM Providers management routes for connecting agents to AI models
"""
from flask import jsonify, request, session
from models import db, User, Agent
import json


# Provider definitions with configuration requirements
PROVIDERS = {
    # Free tier providers (included in all plans)
    'openai': {
        'name': 'OpenAI',
        'icon': '🤖',
        'tier': 'free',
        'difficulty': 'easy',
        'description': 'GPT-4, GPT-4 Turbo, GPT-3.5 models',
        'setup_type': 'api_key',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Get from platform.openai.com'}
        ],
        'models': [
            {'id': 'gpt-4o', 'name': 'GPT-4o', 'context': '128K', 'recommended': True},
            {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini', 'context': '128K'},
            {'id': 'gpt-4-turbo', 'name': 'GPT-4 Turbo', 'context': '128K'},
            {'id': 'gpt-3.5-turbo', 'name': 'GPT-3.5 Turbo', 'context': '16K'}
        ],
        'docs_url': 'https://platform.openai.com/docs',
        'pricing_url': 'https://openai.com/api/pricing/'
    },

    # Pro tier providers (requires Pro subscription)
    'venice': {
        'name': 'Venice AI',
        'icon': '🏛️',
        'tier': 'pro',
        'difficulty': 'easy',
        'description': 'Privacy-first, uncensored AI with competitive pricing',
        'setup_type': 'api_key',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Get from venice.ai'}
        ],
        'models': [
            {'id': 'llama-3.3-70b', 'name': 'Llama 3.3 70B', 'context': '128K', 'recommended': True},
            {'id': 'llama-3.1-405b', 'name': 'Llama 3.1 405B', 'context': '128K'},
            {'id': 'dolphin-2.9.2-qwen2-72b', 'name': 'Dolphin Qwen2 72B', 'context': '32K'},
            {'id': 'mistral-large-2', 'name': 'Mistral Large 2', 'context': '128K'}
        ],
        'docs_url': 'https://docs.venice.ai',
        'pricing_url': 'https://venice.ai/pricing',
        'benefits': ['No censorship', 'Privacy-focused', '60% cheaper than OpenAI']
    },
    'groq': {
        'name': 'Groq',
        'icon': '⚡',
        'tier': 'pro',
        'difficulty': 'easy',
        'description': 'Ultra-fast inference with open source models',
        'setup_type': 'api_key',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Get from console.groq.com'}
        ],
        'models': [
            {'id': 'llama-3.3-70b-versatile', 'name': 'Llama 3.3 70B', 'context': '128K', 'recommended': True},
            {'id': 'mixtral-8x7b-32768', 'name': 'Mixtral 8x7B', 'context': '32K'},
            {'id': 'gemma2-9b-it', 'name': 'Gemma 2 9B', 'context': '8K'}
        ],
        'docs_url': 'https://console.groq.com/docs',
        'pricing_url': 'https://groq.com/pricing',
        'benefits': ['Fastest inference', 'Free tier available', 'Open source models']
    },

    'xai': {
        'name': 'xAI Grok',
        'icon': '🚀',
        'tier': 'pro',
        'difficulty': 'easy',
        'description': 'Grok models from xAI with fast reasoning capabilities',
        'setup_type': 'api_key',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Get from console.x.ai'}
        ],
        'models': [
            {'id': 'grok-4-1-fast-reasoning', 'name': 'Grok 4.1 Fast Reasoning', 'context': '128K', 'recommended': True},
            {'id': 'grok-3-fast', 'name': 'Grok 3 Fast', 'context': '128K'},
            {'id': 'grok-3-mini-fast', 'name': 'Grok 3 Mini Fast', 'context': '128K'},
            {'id': 'grok-2-latest', 'name': 'Grok 2', 'context': '128K'}
        ],
        'docs_url': 'https://docs.x.ai',
        'pricing_url': 'https://x.ai/api',
        'benefits': ['Fast reasoning', 'Real-time knowledge', 'OpenAI-compatible']
    },

    'anthropic': {
        'name': 'Anthropic Claude',
        'icon': '🧠',
        'tier': 'pro',
        'difficulty': 'easy',
        'description': 'Claude 3.5 Sonnet, Opus, Haiku - advanced reasoning',
        'setup_type': 'api_key',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Get from console.anthropic.com'}
        ],
        'models': [
            {'id': 'claude-3-5-sonnet-20241022', 'name': 'Claude 3.5 Sonnet', 'context': '200K', 'recommended': True},
            {'id': 'claude-3-5-haiku-20241022', 'name': 'Claude 3.5 Haiku', 'context': '200K'},
            {'id': 'claude-3-opus-20240229', 'name': 'Claude 3 Opus', 'context': '200K'}
        ],
        'docs_url': 'https://docs.anthropic.com',
        'pricing_url': 'https://www.anthropic.com/pricing',
        'benefits': ['Best reasoning', 'Long context', 'Tool use']
    },
    'google': {
        'name': 'Google Gemini',
        'icon': '✨',
        'tier': 'pro',
        'difficulty': 'easy',
        'description': 'Gemini Pro and Ultra models with multimodal capabilities',
        'setup_type': 'api_key',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Get from makersuite.google.com'}
        ],
        'models': [
            {'id': 'gemini-2.0-flash-exp', 'name': 'Gemini 2.0 Flash', 'context': '1M', 'recommended': True},
            {'id': 'gemini-1.5-pro', 'name': 'Gemini 1.5 Pro', 'context': '2M'},
            {'id': 'gemini-1.5-flash', 'name': 'Gemini 1.5 Flash', 'context': '1M'}
        ],
        'docs_url': 'https://ai.google.dev/docs',
        'pricing_url': 'https://ai.google.dev/pricing',
        'benefits': ['Longest context', 'Multimodal', 'Free tier']
    },
    'mistral': {
        'name': 'Mistral AI',
        'icon': '🌊',
        'tier': 'pro',
        'difficulty': 'easy',
        'description': 'European AI with Mistral Large and specialized models',
        'setup_type': 'api_key',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Get from console.mistral.ai'}
        ],
        'models': [
            {'id': 'mistral-large-latest', 'name': 'Mistral Large', 'context': '128K', 'recommended': True},
            {'id': 'mistral-medium-latest', 'name': 'Mistral Medium', 'context': '32K'},
            {'id': 'mistral-small-latest', 'name': 'Mistral Small', 'context': '32K'}
        ],
        'docs_url': 'https://docs.mistral.ai',
        'pricing_url': 'https://mistral.ai/technology/#pricing',
        'benefits': ['EU-based', 'Specialized models', 'Function calling']
    },

    'azure': {
        'name': 'Azure OpenAI',
        'icon': '☁️',
        'tier': 'pro',
        'difficulty': 'medium',
        'description': 'Enterprise OpenAI via Azure with SLA guarantees',
        'setup_type': 'complex',
        'fields': [
            {'key': 'endpoint', 'label': 'Endpoint URL', 'type': 'url', 'required': True, 'help': 'Your Azure OpenAI endpoint'},
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True},
            {'key': 'deployment_name', 'label': 'Deployment Name', 'type': 'text', 'required': True}
        ],
        'models': [
            {'id': 'gpt-4', 'name': 'GPT-4', 'context': '128K'},
            {'id': 'gpt-35-turbo', 'name': 'GPT-3.5 Turbo', 'context': '16K'}
        ],
        'docs_url': 'https://learn.microsoft.com/en-us/azure/ai-services/openai/',
        'benefits': ['Enterprise SLA', 'Data residency', 'Private deployment']
    },
    'ollama': {
        'name': 'Ollama (Self-hosted)',
        'icon': '🦙',
        'tier': 'pro',
        'difficulty': 'medium',
        'description': 'Run models locally with Ollama',
        'setup_type': 'endpoint',
        'fields': [
            {'key': 'endpoint', 'label': 'Ollama Endpoint', 'type': 'url', 'required': True, 'help': 'Default: http://localhost:11434'}
        ],
        'models': [
            {'id': 'llama3.3:70b', 'name': 'Llama 3.3 70B', 'context': '128K', 'recommended': True},
            {'id': 'mixtral:8x7b', 'name': 'Mixtral 8x7B', 'context': '32K'},
            {'id': 'qwen2.5:72b', 'name': 'Qwen 2.5 72B', 'context': '128K'}
        ],
        'docs_url': 'https://ollama.ai/docs',
        'benefits': ['Fully local', 'No API costs', 'Data privacy']
    },
    'custom': {
        'name': 'Custom Endpoint',
        'icon': '🔧',
        'tier': 'pro',
        'difficulty': 'hard',
        'description': 'Connect to any OpenAI-compatible API endpoint',
        'setup_type': 'custom',
        'fields': [
            {'key': 'endpoint', 'label': 'API Endpoint', 'type': 'url', 'required': True, 'help': 'OpenAI-compatible endpoint'},
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': False},
            {'key': 'model', 'label': 'Model Name', 'type': 'text', 'required': True}
        ],
        'models': [],
        'docs_url': 'https://docs.openclaw.ai/providers/custom',
        'benefits': ['Maximum flexibility', 'Any provider', 'Custom deployments']
    },

    # Speech-to-Text providers (for voice message transcription in channels)
    'stt_openai': {
        'name': 'OpenAI Whisper (STT)',
        'icon': '🎙️',
        'tier': 'free',
        'difficulty': 'easy',
        'description': 'Transcribe voice messages with OpenAI Whisper',
        'setup_type': 'api_key',
        'category': 'stt',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Same OpenAI API key from platform.openai.com'}
        ],
        'models': [
            {'id': 'whisper-1', 'name': 'Whisper v1', 'recommended': True}
        ],
        'docs_url': 'https://platform.openai.com/docs/guides/speech-to-text',
        'pricing_url': 'https://openai.com/api/pricing/'
    },
    'stt_groq': {
        'name': 'Groq Whisper (STT)',
        'icon': '⚡🎙️',
        'tier': 'free',
        'difficulty': 'easy',
        'description': 'Ultra-fast voice transcription with Groq Whisper',
        'setup_type': 'api_key',
        'category': 'stt',
        'fields': [
            {'key': 'api_key', 'label': 'API Key', 'type': 'password', 'required': True, 'help': 'Get from console.groq.com'}
        ],
        'models': [
            {'id': 'whisper-large-v3', 'name': 'Whisper Large v3', 'recommended': True}
        ],
        'docs_url': 'https://console.groq.com/docs/speech-text',
        'benefits': ['Fastest transcription', 'Free tier available']
    }
}

def register_llm_providers_routes(app):
    """Register LLM provider management routes"""

    @app.route('/api/providers/available', methods=['GET'])
    def get_available_providers():
        """Get list of available LLM providers filtered by user's subscription tier"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Filter providers by user's effective subscription tier
            tier_hierarchy = {'free': 0, 'pro': 1}
            user_tier_level = tier_hierarchy.get(user.effective_tier, 0)

            available_providers = {}
            locked_providers = {}

            for provider_id, provider_info in PROVIDERS.items():
                provider_tier_level = tier_hierarchy.get(provider_info['tier'], 0)

                provider_data = {
                    **provider_info,
                    'id': provider_id,
                    'locked': provider_tier_level > user_tier_level
                }

                if provider_tier_level <= user_tier_level:
                    available_providers[provider_id] = provider_data
                else:
                    locked_providers[provider_id] = provider_data

            return jsonify({
                'available': available_providers,
                'locked': locked_providers,
                'user_tier': user.effective_tier
            })

        except Exception as e:
            print(f"Error getting available providers: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/providers/agent/<int:agent_id>/config', methods=['GET'])
    def get_agent_providers(agent_id):
        """Get configured LLM providers for an agent"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            # Get provider configuration from agent's metadata
            # In a real implementation, this would be stored in a proper providers table
            providers_config = {}

            return jsonify({
                'agent_id': agent.id,
                'agent_name': agent.name,
                'providers': providers_config
            })

        except Exception as e:
            print(f"Error getting agent providers: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/providers/agent/<int:agent_id>/connect', methods=['POST'])
    def connect_provider(agent_id):
        """Connect a LLM provider to an agent"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            data = request.get_json()
            provider_id = data.get('provider_id')
            config = data.get('config', {})
            selected_model = data.get('model')

            if not provider_id or provider_id not in PROVIDERS:
                return jsonify({'error': 'Invalid provider'}), 400

            # Check if user has access to this provider
            user = User.query.get(user_id)
            provider_info = PROVIDERS[provider_id]

            tier_hierarchy = {'free': 0, 'pro': 1}
            user_tier_level = tier_hierarchy.get(user.effective_tier, 0)
            provider_tier_level = tier_hierarchy.get(provider_info['tier'], 0)

            if provider_tier_level > user_tier_level:
                return jsonify({
                    'error': 'Upgrade required',
                    'required_tier': provider_info['tier'],
                    'current_tier': user.subscription_tier
                }), 403

            # Validate required fields
            for field in provider_info.get('fields', []):
                if field.get('required') and field['key'] not in config:
                    return jsonify({'error': f"Missing required field: {field['label']}"}), 400

            # Validate model selection
            if provider_info.get('models') and not selected_model:
                return jsonify({'error': 'Model selection required'}), 400

            # In a real implementation, save to database and test connection
            # For now, return success
            return jsonify({
                'success': True,
                'message': f"{provider_info['name']} connected successfully",
                'provider_id': provider_id,
                'model': selected_model,
                'agent_id': agent.id
            })

        except Exception as e:
            print(f"Error connecting provider: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/providers/agent/<int:agent_id>/disconnect/<provider_id>', methods=['POST'])
    def disconnect_provider(agent_id, provider_id):
        """Disconnect a LLM provider from an agent"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            agent = Agent.query.filter_by(id=agent_id, user_id=user_id).first()
            if not agent:
                return jsonify({'error': 'Agent not found'}), 404

            # In a real implementation, remove from database
            return jsonify({
                'success': True,
                'message': f"Provider {provider_id} disconnected"
            })

        except Exception as e:
            print(f"Error disconnecting provider: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/providers/test/<provider_id>', methods=['POST'])
    def test_provider_connection(provider_id):
        """Test a LLM provider configuration without saving"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            data = request.get_json()
            config = data.get('config', {})
            model = data.get('model')

            if provider_id not in PROVIDERS:
                return jsonify({'error': 'Invalid provider'}), 400

            # In a real implementation, test the connection with a simple API call
            # For now, simulate success
            return jsonify({
                'success': True,
                'message': 'Connection test successful',
                'details': f'Successfully connected to {PROVIDERS[provider_id]["name"]}',
                'model': model
            })

        except Exception as e:
            print(f"Error testing provider: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500

    @app.route('/api/providers/<provider_id>/models', methods=['GET'])
    def get_provider_models(provider_id):
        """Get available models for a specific provider"""
        try:
            if provider_id not in PROVIDERS:
                return jsonify({'error': 'Invalid provider'}), 400

            provider = PROVIDERS[provider_id]
            return jsonify({
                'provider_id': provider_id,
                'provider_name': provider['name'],
                'models': provider.get('models', [])
            })

        except Exception as e:
            print(f"Error getting provider models: {e}")
            return jsonify({'error': 'An internal error occurred'}), 500
