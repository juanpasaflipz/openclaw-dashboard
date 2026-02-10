"""
Utility Routes — general-purpose AI tools with tailored system prompts.
"""
from flask import jsonify, request, session
from models import db, UserModelConfig
from llm_service import LLMService


UTILITY_TOOLS = {
    'code_gen': {
        'name': 'Code Assistant',
        'emoji': '💻',
        'description': 'Code generation, explanation, and debugging',
        'system_prompt': 'You are an expert programmer. Help with code generation, explanation, debugging, and optimization. Provide clear, well-commented code. Use markdown code blocks with language tags.',
        'placeholder': 'Describe what code you need, paste code to explain, or describe a bug to debug...',
    },
    'calculator': {
        'name': 'Calculator',
        'emoji': '🧮',
        'description': 'Math, calculations, and data analysis',
        'system_prompt': 'You are a math and data analysis expert. Solve calculations, explain mathematical concepts, analyze data, and show your work step by step. Use LaTeX notation for complex formulas when helpful.',
        'placeholder': 'Enter a math problem, calculation, or data to analyze...',
    },
    'writer': {
        'name': 'Writer',
        'emoji': '✍️',
        'description': 'Content writing, editing, and summarization',
        'system_prompt': 'You are a skilled writer and editor. Help with content creation, editing, proofreading, summarization, and rewriting. Maintain the user\'s voice while improving clarity and impact.',
        'placeholder': 'Describe what you need written, or paste text to edit/summarize...',
    },
    'translator': {
        'name': 'Translator',
        'emoji': '🌐',
        'description': 'Language translation',
        'system_prompt': 'You are an expert translator fluent in all major languages. Translate text accurately while preserving tone, idioms, and cultural context. If the target language is not specified, ask.',
        'placeholder': 'Paste text to translate and specify the target language...',
    },
    'analyzer': {
        'name': 'Analyzer',
        'emoji': '📊',
        'description': 'Data and text analysis, CSV parsing',
        'system_prompt': 'You are a data and text analyst. Analyze text, data, CSV content, or structured information. Identify patterns, trends, key points, and provide actionable insights. Use tables and structured formats for clarity.',
        'placeholder': 'Paste data, text, or CSV to analyze...',
    },
}


def register_utility_routes(app):

    @app.route('/api/utility/tools', methods=['GET'])
    def list_utility_tools():
        tools = []
        for tool_id, info in UTILITY_TOOLS.items():
            tools.append({
                'id': tool_id,
                'name': info['name'],
                'emoji': info['emoji'],
                'description': info['description'],
                'placeholder': info['placeholder'],
            })
        return jsonify({'tools': tools})

    @app.route('/api/utility/execute', methods=['POST'])
    def execute_utility():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        tool_id = data.get('tool', 'code_gen')
        prompt = (data.get('prompt') or '').strip()

        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400

        tool_info = UTILITY_TOOLS.get(tool_id)
        if not tool_info:
            return jsonify({'error': f'Unknown tool: {tool_id}'}), 400

        # Load model config
        config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot='utility').first()
        if not config:
            return jsonify({'error': 'No model configured for utility. Please configure a model first.'}), 400

        try:
            messages = [
                {'role': 'system', 'content': tool_info['system_prompt']},
                {'role': 'user', 'content': prompt},
            ]

            result = LLMService.call(
                provider=config.provider,
                model=config.model,
                api_key=config.api_key,
                messages=messages,
                endpoint_url=config.endpoint_url,
                extra_config=config.extra_config,
            )

            return jsonify({
                'success': True,
                'content': result['content'],
                'model': result.get('model'),
                'usage': result.get('usage', {}),
                'tool': tool_id,
            })

        except Exception as e:
            return jsonify({'error': f'Utility error: {str(e)[:300]}'}), 500
