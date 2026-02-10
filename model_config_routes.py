"""
Model Configuration Routes — per-feature LLM config management.
"""
from flask import jsonify, request, session
from models import db, UserModelConfig
from llm_service import LLMService, PROVIDER_DEFAULTS


def register_model_config_routes(app):

    @app.route('/api/model-config', methods=['GET'])
    def get_all_model_configs():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        configs = UserModelConfig.query.filter_by(user_id=user_id).all()
        return jsonify({'configs': [c.to_dict() for c in configs]})

    @app.route('/api/model-config/<feature_slot>', methods=['GET'])
    def get_model_config(feature_slot):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot=feature_slot).first()
        if not config:
            return jsonify({'config': None, 'configured': False})
        return jsonify({'config': config.to_dict(), 'configured': True})

    @app.route('/api/model-config/<feature_slot>', methods=['PUT', 'POST'])
    def save_model_config(feature_slot):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        provider = data.get('provider', '').strip()
        model = data.get('model', '').strip()

        if not provider or not model:
            return jsonify({'error': 'Provider and model are required'}), 400

        config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot=feature_slot).first()
        if config:
            config.provider = provider
            config.model = model
            if 'api_key' in data and data['api_key']:
                config.api_key = data['api_key']
            config.endpoint_url = data.get('endpoint_url', '').strip() or None
            config.extra_config = data.get('extra_config', {})
        else:
            config = UserModelConfig(
                user_id=user_id,
                feature_slot=feature_slot,
                provider=provider,
                model=model,
                api_key=data.get('api_key', ''),
                endpoint_url=data.get('endpoint_url', '').strip() or None,
                extra_config=data.get('extra_config', {}),
            )
            db.session.add(config)

        db.session.commit()
        return jsonify({'success': True, 'config': config.to_dict()})

    @app.route('/api/model-config/<feature_slot>', methods=['DELETE'])
    def delete_model_config(feature_slot):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot=feature_slot).first()
        if config:
            db.session.delete(config)
            db.session.commit()
        return jsonify({'success': True})

    @app.route('/api/model-config/<feature_slot>/test', methods=['POST'])
    def test_model_config(feature_slot):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        provider = data.get('provider', '').strip()
        model = data.get('model', '').strip()
        api_key = data.get('api_key', '').strip()
        endpoint_url = data.get('endpoint_url', '').strip() or None

        if not provider or not model:
            return jsonify({'success': False, 'message': 'Provider and model are required'}), 400

        # If no API key provided, try to load from saved config
        if not api_key:
            config = UserModelConfig.query.filter_by(user_id=user_id, feature_slot=feature_slot).first()
            if config and config.api_key:
                api_key = config.api_key

        success, message = LLMService.test_connection(provider, model, api_key, endpoint_url)
        return jsonify({'success': success, 'message': message})

    @app.route('/api/model-config/providers', methods=['GET'])
    def get_providers():
        return jsonify({'providers': LLMService.get_providers()})
