"""
GitHub integration routes - Repos and issues
"""
from flask import jsonify, request, session
from models import db, Superpower
from datetime import datetime
import requests as http_requests


def get_github_headers(user_id):
    """Get GitHub API headers with authentication"""
    superpower = Superpower.query.filter_by(
        user_id=user_id,
        service_type='github',
        is_enabled=True
    ).first()

    if not superpower:
        return None, 'GitHub not connected'
    if not superpower.access_token_encrypted:
        return None, 'GitHub access token missing'

    headers = {
        'Authorization': f'token {superpower.access_token_encrypted}',
        'Accept': 'application/vnd.github.v3+json',
    }

    superpower.last_used = datetime.utcnow()
    db.session.commit()

    return headers, None


def register_github_routes(app):
    """Register GitHub routes"""

    @app.route('/api/github/repos', methods=['GET'])
    def github_repos():
        """List user's repositories"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_github_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                'https://api.github.com/user/repos',
                headers=headers,
                params={'sort': 'updated', 'per_page': 20}
            )
            if resp.status_code != 200:
                return jsonify({'error': f'GitHub API error: {resp.text}'}), resp.status_code

            repos = resp.json()
            return jsonify({
                'success': True,
                'repos': [{
                    'id': r['id'],
                    'name': r['name'],
                    'full_name': r['full_name'],
                    'description': r.get('description'),
                    'private': r['private'],
                    'html_url': r['html_url'],
                    'language': r.get('language'),
                    'stargazers_count': r.get('stargazers_count', 0),
                    'updated_at': r.get('updated_at'),
                } for r in repos]
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/github/repos/<owner>/<repo>/issues', methods=['GET'])
    def github_issues(owner, repo):
        """List issues for a repository"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_github_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                f'https://api.github.com/repos/{owner}/{repo}/issues',
                headers=headers,
                params={'state': 'open', 'per_page': 20}
            )
            if resp.status_code != 200:
                return jsonify({'error': f'GitHub API error: {resp.text}'}), resp.status_code

            issues = resp.json()
            return jsonify({
                'success': True,
                'issues': [{
                    'id': i['id'],
                    'number': i['number'],
                    'title': i['title'],
                    'state': i['state'],
                    'html_url': i['html_url'],
                    'user': i['user']['login'],
                    'labels': [l['name'] for l in i.get('labels', [])],
                    'created_at': i.get('created_at'),
                    'updated_at': i.get('updated_at'),
                } for i in issues]
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
