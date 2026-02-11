"""
Dropbox integration routes - List files and metadata (Dropbox uses POST for reads)
"""
from flask import jsonify, request, session
from models import db, Superpower
from datetime import datetime
import requests as http_requests

from routes.oauth_routes import refresh_oauth_token


def get_dropbox_headers(user_id):
    """Get Dropbox API headers, refreshing token if expired"""
    superpower = Superpower.query.filter_by(
        user_id=user_id,
        service_type='dropbox',
        is_enabled=True
    ).first()

    if not superpower:
        return None, 'Dropbox not connected'
    if not superpower.access_token_encrypted:
        return None, 'Dropbox access token missing'

    # Refresh token if expired
    if superpower.token_expires_at and superpower.token_expires_at < datetime.utcnow():
        if not refresh_oauth_token(superpower, 'dropbox'):
            return None, 'Dropbox token expired and refresh failed. Please reconnect.'

    headers = {
        'Authorization': f'Bearer {superpower.access_token_encrypted}',
        'Content-Type': 'application/json',
    }

    superpower.last_used = datetime.utcnow()
    db.session.commit()

    return headers, None


def register_dropbox_routes(app):
    """Register Dropbox routes"""

    @app.route('/api/dropbox/files', methods=['GET'])
    def dropbox_files():
        """List files in a folder (Dropbox uses POST for list_folder)"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_dropbox_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            path = request.args.get('path', '')
            resp = http_requests.post(
                'https://api.dropboxapi.com/2/files/list_folder',
                headers=headers,
                json={'path': path, 'limit': 50}
            )

            if resp.status_code != 200:
                return jsonify({'error': f'Dropbox API error: {resp.text}'}), resp.status_code

            data = resp.json()
            entries = [{
                'name': e['name'],
                'path': e['path_display'],
                'type': e['.tag'],
                'size': e.get('size'),
                'modified': e.get('server_modified'),
            } for e in data.get('entries', [])]

            return jsonify({
                'success': True,
                'files': entries,
                'has_more': data.get('has_more', False),
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/dropbox/files/metadata', methods=['GET'])
    def dropbox_metadata():
        """Get metadata for a specific file or folder"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_dropbox_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        filepath = request.args.get('path')
        if not filepath:
            return jsonify({'error': 'path parameter required'}), 400

        try:
            resp = http_requests.post(
                'https://api.dropboxapi.com/2/files/get_metadata',
                headers=headers,
                json={'path': filepath}
            )

            if resp.status_code != 200:
                return jsonify({'error': f'Dropbox API error: {resp.text}'}), resp.status_code

            meta = resp.json()
            return jsonify({
                'success': True,
                'metadata': {
                    'name': meta['name'],
                    'path': meta['path_display'],
                    'type': meta['.tag'],
                    'size': meta.get('size'),
                    'modified': meta.get('server_modified'),
                    'id': meta.get('id'),
                }
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500
