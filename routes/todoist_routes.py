"""
Todoist integration routes - Projects and tasks
"""
from flask import jsonify, request, session
from models import db, Superpower
from datetime import datetime
import requests as http_requests


def get_todoist_headers(user_id):
    """Get Todoist API headers with authentication"""
    superpower = Superpower.query.filter_by(
        user_id=user_id,
        service_type='todoist',
        is_enabled=True
    ).first()

    if not superpower:
        return None, 'Todoist not connected'
    if not superpower.access_token_encrypted:
        return None, 'Todoist access token missing'

    headers = {
        'Authorization': f'Bearer {superpower.access_token_encrypted}',
    }

    superpower.last_used = datetime.utcnow()
    db.session.commit()

    return headers, None


def register_todoist_routes(app):
    """Register Todoist routes"""

    @app.route('/api/todoist/projects', methods=['GET'])
    def todoist_projects():
        """List Todoist projects"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_todoist_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                'https://api.todoist.com/rest/v2/projects',
                headers=headers
            )
            if resp.status_code != 200:
                return jsonify({'error': f'Todoist API error: {resp.text}'}), resp.status_code

            projects = resp.json()
            return jsonify({
                'success': True,
                'projects': [{
                    'id': p['id'],
                    'name': p['name'],
                    'color': p.get('color'),
                    'is_favorite': p.get('is_favorite', False),
                    'url': p.get('url'),
                } for p in projects]
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/todoist/tasks', methods=['GET'])
    def todoist_tasks():
        """List Todoist tasks, optionally filtered by project"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_todoist_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            params = {}
            project_id = request.args.get('project_id')
            if project_id:
                params['project_id'] = project_id

            resp = http_requests.get(
                'https://api.todoist.com/rest/v2/tasks',
                headers=headers,
                params=params
            )
            if resp.status_code != 200:
                return jsonify({'error': f'Todoist API error: {resp.text}'}), resp.status_code

            tasks = resp.json()
            return jsonify({
                'success': True,
                'tasks': [{
                    'id': t['id'],
                    'content': t['content'],
                    'description': t.get('description', ''),
                    'is_completed': t.get('is_completed', False),
                    'priority': t.get('priority', 1),
                    'due': t.get('due'),
                    'project_id': t.get('project_id'),
                    'url': t.get('url'),
                } for t in tasks]
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500
