"""
Unified LLM abstraction layer for OpenClaw Dashboard.
Supports multiple providers via raw HTTP requests.
"""
import requests
import json
import time


# Provider endpoint defaults
PROVIDER_DEFAULTS = {
    'openai': {
        'endpoint': 'https://api.openai.com/v1/chat/completions',
        'models': ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'],
    },
    'anthropic': {
        'endpoint': 'https://api.anthropic.com/v1/messages',
        'models': ['claude-sonnet-4-5-20250929', 'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
    },
    'google': {
        'endpoint': 'https://generativelanguage.googleapis.com/v1beta/models',
        'models': ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
    },
    'groq': {
        'endpoint': 'https://api.groq.com/openai/v1/chat/completions',
        'models': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768', 'gemma2-9b-it'],
    },
    'mistral': {
        'endpoint': 'https://api.mistral.ai/v1/chat/completions',
        'models': ['mistral-large-latest', 'mistral-medium-latest', 'mistral-small-latest', 'open-mistral-7b'],
    },
    'ollama': {
        'endpoint': 'http://localhost:11434/api/chat',
        'models': ['llama3.2', 'mistral', 'codellama', 'mixtral', 'phi3', 'gemma2'],
    },
    'together': {
        'endpoint': 'https://api.together.xyz/v1/chat/completions',
        'models': ['meta-llama/Llama-3.3-70B-Instruct-Turbo', 'mistralai/Mixtral-8x7B-Instruct-v0.1', 'Qwen/Qwen2.5-72B-Instruct-Turbo'],
    },
    'xai': {
        'endpoint': 'https://api.x.ai/v1/chat/completions',
        'models': ['grok-4-1-fast-reasoning', 'grok-3-fast', 'grok-3-mini-fast', 'grok-2-latest'],
    },
    'openrouter': {
        'endpoint': 'https://openrouter.ai/api/v1/chat/completions',
        'models': ['anthropic/claude-3.5-sonnet', 'openai/gpt-4o', 'google/gemini-pro-1.5', 'meta-llama/llama-3.1-70b-instruct'],
    },
    'cohere': {
        'endpoint': 'https://api.cohere.ai/v2/chat',
        'models': ['command-r-plus', 'command-r', 'command-light'],
    },
    'azure': {
        'endpoint': '',  # User must provide
        'models': ['gpt-4o', 'gpt-4', 'gpt-35-turbo'],
    },
    'custom': {
        'endpoint': '',
        'models': [],
    },
}

DEFAULT_TIMEOUT = 30


class LLMService:

    # Providers that support function/tool calling
    TOOL_CAPABLE_PROVIDERS = {'openai', 'anthropic', 'groq', 'mistral', 'together', 'xai', 'openrouter', 'azure'}

    # Observability hook — set by caller to capture LLM metrics.
    # Signature: (provider, model, usage_dict, latency_ms, success, error_msg)
    _obs_hook = None

    @staticmethod
    def call(provider, model, api_key, messages, endpoint_url=None, extra_config=None, tools=None):
        """
        Unified LLM call. Returns dict with content, model, usage, tool_calls.
        When tools is provided and the provider supports it, tool_calls may be
        a list of {id, name, arguments} dicts instead of (or alongside) content.
        """
        extra_config = extra_config or {}
        temperature = extra_config.get('temperature', 0.7)
        max_tokens = extra_config.get('max_tokens', 1024)
        timeout = extra_config.get('timeout', DEFAULT_TIMEOUT)

        # Only pass tools to capable providers
        if tools and provider not in LLMService.TOOL_CAPABLE_PROVIDERS:
            tools = None

        t0 = time.time()
        error_msg = None
        result = None
        try:
            if provider == 'anthropic':
                result = LLMService._call_anthropic(model, api_key, messages, endpoint_url, temperature, max_tokens, timeout, tools=tools)
            elif provider == 'google':
                result = LLMService._call_google(model, api_key, messages, endpoint_url, temperature, max_tokens, timeout)
            elif provider == 'ollama':
                result = LLMService._call_ollama(model, messages, endpoint_url, temperature, timeout)
            elif provider == 'cohere':
                result = LLMService._call_cohere(model, api_key, messages, endpoint_url, temperature, max_tokens, timeout)
            else:
                result = LLMService._call_openai_compatible(provider, model, api_key, messages, endpoint_url, temperature, max_tokens, timeout, tools=tools)
            return result
        except Exception as exc:
            error_msg = str(exc)[:300]
            raise
        finally:
            latency_ms = int((time.time() - t0) * 1000)
            if LLMService._obs_hook:
                try:
                    usage = (result or {}).get('usage', {})
                    LLMService._obs_hook(provider, model, usage, latency_ms, error_msg is None, error_msg)
                except Exception:
                    pass  # Never let observability break the response

    @staticmethod
    def _call_openai_compatible(provider, model, api_key, messages, endpoint_url, temperature, max_tokens, timeout, tools=None):
        url = endpoint_url or PROVIDER_DEFAULTS.get(provider, {}).get('endpoint', '')
        if not url:
            raise ValueError(f'No endpoint URL configured for provider: {provider}')

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }

        # OpenRouter wants extra headers
        if provider == 'openrouter':
            headers['HTTP-Referer'] = 'https://openclaw.dev'
            headers['X-Title'] = 'OpenClaw Dashboard'

        payload = {
            'model': model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }

        if tools:
            payload['tools'] = tools

        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if not resp.ok:
            raise Exception(f'{provider} API error ({resp.status_code}): {resp.text[:500]}')

        data = resp.json()
        choice = data['choices'][0]
        message = choice['message']

        # Parse tool calls if present
        tool_calls = None
        if message.get('tool_calls'):
            tool_calls = []
            for tc in message['tool_calls']:
                args = tc['function'].get('arguments', '{}')
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                tool_calls.append({
                    'id': tc.get('id', ''),
                    'name': tc['function']['name'],
                    'arguments': args,
                })

        return {
            'content': message.get('content') or '',
            'model': data.get('model', model),
            'usage': data.get('usage', {}),
            'tool_calls': tool_calls,
        }

    @staticmethod
    def _call_anthropic(model, api_key, messages, endpoint_url, temperature, max_tokens, timeout, tools=None):
        url = endpoint_url or PROVIDER_DEFAULTS['anthropic']['endpoint']

        # Extract system prompt and build chat messages
        system_text = ''
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_text += msg['content'] + '\n'
            else:
                # Pass through structured content (for tool_result blocks)
                chat_messages.append({
                    'role': msg['role'],
                    'content': msg.get('content', ''),
                })

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        }

        payload = {
            'model': model,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'messages': chat_messages,
        }
        if system_text.strip():
            payload['system'] = system_text.strip()

        # Convert OpenAI tool format → Anthropic tool format
        if tools:
            payload['tools'] = [
                {
                    'name': t['function']['name'],
                    'description': t['function'].get('description', ''),
                    'input_schema': t['function'].get('parameters', {'type': 'object', 'properties': {}}),
                }
                for t in tools
            ]

        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if not resp.ok:
            raise Exception(f'Anthropic API error ({resp.status_code}): {resp.text[:500]}')

        data = resp.json()

        # Parse response content blocks — may contain text and/or tool_use
        content = ''
        tool_calls = None
        for block in data.get('content', []):
            if block.get('type') == 'text':
                content += block['text']
            elif block.get('type') == 'tool_use':
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append({
                    'id': block['id'],
                    'name': block['name'],
                    'arguments': block.get('input', {}),
                })

        return {
            'content': content,
            'model': data.get('model', model),
            'usage': data.get('usage', {}),
            'tool_calls': tool_calls,
        }

    @staticmethod
    def _call_google(model, api_key, messages, endpoint_url, temperature, max_tokens, timeout):
        base = endpoint_url or PROVIDER_DEFAULTS['google']['endpoint']
        url = f'{base}/{model}:generateContent?key={api_key}'

        # Convert messages to Gemini format
        system_text = ''
        contents = []
        for msg in messages:
            if msg['role'] == 'system':
                system_text += msg['content'] + '\n'
            else:
                role = 'user' if msg['role'] == 'user' else 'model'
                contents.append({'role': role, 'parts': [{'text': msg['content']}]})

        payload = {
            'contents': contents,
            'generationConfig': {
                'temperature': temperature,
                'maxOutputTokens': max_tokens,
            },
        }
        if system_text.strip():
            payload['systemInstruction'] = {'parts': [{'text': system_text.strip()}]}

        headers = {'Content-Type': 'application/json'}
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if not resp.ok:
            raise Exception(f'Google API error ({resp.status_code}): {resp.text[:500]}')

        data = resp.json()
        candidates = data.get('candidates', [])
        content = ''
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])
            content = ''.join(p.get('text', '') for p in parts)

        usage = data.get('usageMetadata', {})
        return {
            'content': content,
            'model': model,
            'usage': {
                'prompt_tokens': usage.get('promptTokenCount', 0),
                'completion_tokens': usage.get('candidatesTokenCount', 0),
                'total_tokens': usage.get('totalTokenCount', 0),
            },
            'tool_calls': None,
        }

    @staticmethod
    def _call_ollama(model, messages, endpoint_url, temperature, timeout):
        url = endpoint_url or PROVIDER_DEFAULTS['ollama']['endpoint']

        payload = {
            'model': model,
            'messages': messages,
            'stream': False,
            'options': {'temperature': temperature},
        }

        resp = requests.post(url, json=payload, timeout=timeout)
        if not resp.ok:
            raise Exception(f'Ollama error ({resp.status_code}): {resp.text[:500]}')

        data = resp.json()
        return {
            'content': data.get('message', {}).get('content', ''),
            'model': data.get('model', model),
            'usage': {
                'prompt_tokens': data.get('prompt_eval_count', 0),
                'completion_tokens': data.get('eval_count', 0),
                'total_tokens': (data.get('prompt_eval_count', 0) + data.get('eval_count', 0)),
            },
            'tool_calls': None,
        }

    @staticmethod
    def _call_cohere(model, api_key, messages, endpoint_url, temperature, max_tokens, timeout):
        url = endpoint_url or PROVIDER_DEFAULTS['cohere']['endpoint']

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }

        # Convert to Cohere v2 format
        cohere_messages = []
        for msg in messages:
            role = msg['role']
            if role == 'system':
                cohere_messages.append({'role': 'system', 'content': msg['content']})
            elif role == 'user':
                cohere_messages.append({'role': 'user', 'content': msg['content']})
            else:
                cohere_messages.append({'role': 'assistant', 'content': msg['content']})

        payload = {
            'model': model,
            'messages': cohere_messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if not resp.ok:
            raise Exception(f'Cohere API error ({resp.status_code}): {resp.text[:500]}')

        data = resp.json()
        content = ''
        msg = data.get('message', {})
        for item in msg.get('content', []):
            if item.get('type') == 'text':
                content += item.get('text', '')

        return {
            'content': content,
            'model': model,
            'usage': data.get('usage', {}),
            'tool_calls': None,
        }

    @staticmethod
    def test_connection(provider, model, api_key, endpoint_url=None, extra_config=None):
        """
        Test LLM connection. Returns (success: bool, message: str).
        """
        try:
            if provider == 'ollama':
                # Just check if Ollama is running and model exists
                base = endpoint_url or 'http://localhost:11434'
                tags_url = base.replace('/api/chat', '') + '/api/tags'
                resp = requests.get(tags_url, timeout=5)
                if resp.ok:
                    models = [m['name'] for m in resp.json().get('models', [])]
                    if model and model in models:
                        return True, f'Connected. Model {model} available.'
                    elif model:
                        return False, f'Ollama running but model "{model}" not found. Available: {", ".join(models[:5])}'
                    return True, f'Ollama running. {len(models)} models available.'
                return False, f'Cannot connect to Ollama at {base}'

            # For all other providers, send a tiny test message
            test_messages = [{'role': 'user', 'content': 'Say "ok" and nothing else.'}]
            result = LLMService.call(
                provider, model, api_key, test_messages,
                endpoint_url=endpoint_url,
                extra_config={'max_tokens': 10, 'temperature': 0, 'timeout': 15, **(extra_config or {})}
            )
            return True, f'Connected. Model: {result.get("model", model)}'

        except requests.exceptions.ConnectionError:
            return False, f'Cannot connect to {provider} endpoint.'
        except requests.exceptions.Timeout:
            return False, f'Connection timed out for {provider}.'
        except Exception as e:
            return False, f'Error: {str(e)[:200]}'

    @staticmethod
    def get_providers():
        """Return list of all supported providers with their models."""
        providers = []
        for key, info in PROVIDER_DEFAULTS.items():
            needs_key = key not in ('ollama',)
            needs_url = key in ('azure', 'custom', 'ollama')
            providers.append({
                'id': key,
                'name': key.replace('_', ' ').title(),
                'models': info['models'],
                'default_endpoint': info['endpoint'],
                'needs_api_key': needs_key,
                'needs_endpoint_url': needs_url,
            })
        return providers
