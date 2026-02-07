"""
Notion integration routes - Access and manage pages/databases
"""
from flask import jsonify, request, session
from models import db, User, Superpower
from datetime import datetime
import json
import os
import requests


def get_notion_headers(user_id):
    """Get Notion API headers with authentication"""
    try:
        # Get Notion superpower for user
        superpower = Superpower.query.filter_by(
            user_id=user_id,
            service_type='notion',
            is_enabled=True
        ).first()

        if not superpower:
            return None, 'Notion not connected'

        if not superpower.access_token_encrypted:
            return None, 'Notion access token missing'

        headers = {
            'Authorization': f'Bearer {superpower.access_token_encrypted}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }

        # Update last used
        superpower.last_used = datetime.utcnow()
        db.session.commit()

        return headers, None

    except Exception as e:
        print(f"Error getting notion headers: {str(e)}")
        return None, str(e)


def register_notion_routes(app):
    """Register Notion routes with the Flask app"""

    @app.route('/api/notion/search', methods=['POST'])
    def search_notion():
        """Search Notion pages and databases"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            data = request.json
            query = data.get('query', '')

            headers, error = get_notion_headers(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Search Notion
            search_data = {
                'query': query,
                'filter': {
                    'property': 'object',
                    'value': 'page'
                },
                'page_size': 20
            }

            response = requests.post(
                'https://api.notion.com/v1/search',
                headers=headers,
                json=search_data
            )

            if response.status_code != 200:
                return jsonify({'error': f'Notion API error: {response.text}'}), 400

            results = response.json()

            # Format results
            pages = []
            for item in results.get('results', []):
                if item['object'] == 'page':
                    title = ''
                    if 'properties' in item and 'title' in item['properties']:
                        title_prop = item['properties']['title']
                        if title_prop.get('title'):
                            title = ''.join([t.get('plain_text', '') for t in title_prop['title']])

                    pages.append({
                        'id': item['id'],
                        'title': title or 'Untitled',
                        'url': item.get('url', ''),
                        'created_time': item.get('created_time', ''),
                        'last_edited_time': item.get('last_edited_time', '')
                    })

            return jsonify({
                'success': True,
                'pages': pages,
                'count': len(pages)
            })

        except Exception as e:
            print(f"Error searching notion: {str(e)}")
            return jsonify({'error': str(e)}), 500


    @app.route('/api/notion/pages', methods=['POST'])
    def create_notion_page():
        """Create a new Notion page"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            data = request.json

            if not data.get('parent_id'):
                return jsonify({'error': 'parent_id required'}), 400

            headers, error = get_notion_headers(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Build page data
            page_data = {
                'parent': {
                    'page_id': data['parent_id']
                },
                'properties': {
                    'title': {
                        'title': [
                            {
                                'text': {
                                    'content': data.get('title', 'Untitled')
                                }
                            }
                        ]
                    }
                }
            }

            # Add content if provided
            if data.get('content'):
                page_data['children'] = [
                    {
                        'object': 'block',
                        'type': 'paragraph',
                        'paragraph': {
                            'rich_text': [
                                {
                                    'text': {
                                        'content': data['content']
                                    }
                                }
                            ]
                        }
                    }
                ]

            response = requests.post(
                'https://api.notion.com/v1/pages',
                headers=headers,
                json=page_data
            )

            if response.status_code not in [200, 201]:
                return jsonify({'error': f'Notion API error: {response.text}'}), 400

            page = response.json()

            return jsonify({
                'success': True,
                'page_id': page['id'],
                'url': page.get('url', ''),
                'message': 'Page created successfully'
            })

        except Exception as e:
            print(f"Error creating notion page: {str(e)}")
            return jsonify({'error': str(e)}), 500


    @app.route('/api/notion/pages/<page_id>', methods='GET'])
    def get_notion_page(page_id):
        """Get Notion page content"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            headers, error = get_notion_headers(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Get page metadata
            response = requests.get(
                f'https://api.notion.com/v1/pages/{page_id}',
                headers=headers
            )

            if response.status_code != 200:
                return jsonify({'error': f'Notion API error: {response.text}'}), 400

            page = response.json()

            # Get page blocks (content)
            blocks_response = requests.get(
                f'https://api.notion.com/v1/blocks/{page_id}/children',
                headers=headers
            )

            blocks = []
            if blocks_response.status_code == 200:
                blocks = blocks_response.json().get('results', [])

            return jsonify({
                'success': True,
                'page': page,
                'blocks': blocks
            })

        except Exception as e:
            print(f"Error getting notion page: {str(e)}")
            return jsonify({'error': str(e)}), 500


    @app.route('/api/notion/pages/<page_id>/append', methods=['POST'])
    def append_to_notion_page(page_id):
        """Append content to a Notion page"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            data = request.json

            if not data.get('content'):
                return jsonify({'error': 'content required'}), 400

            headers, error = get_notion_headers(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Append block
            block_data = {
                'children': [
                    {
                        'object': 'block',
                        'type': 'paragraph',
                        'paragraph': {
                            'rich_text': [
                                {
                                    'text': {
                                        'content': data['content']
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

            response = requests.patch(
                f'https://api.notion.com/v1/blocks/{page_id}/children',
                headers=headers,
                json=block_data
            )

            if response.status_code != 200:
                return jsonify({'error': f'Notion API error: {response.text}'}), 400

            return jsonify({
                'success': True,
                'message': 'Content appended successfully'
            })

        except Exception as e:
            print(f"Error appending to notion page: {str(e)}")
            return jsonify({'error': str(e)}), 500


    @app.route('/api/notion/databases/<database_id>/query', methods=['POST'])
    def query_notion_database(database_id):
        """Query a Notion database"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            data = request.json or {}

            headers, error = get_notion_headers(user_id)
            if error:
                return jsonify({'error': error}), 400

            response = requests.post(
                f'https://api.notion.com/v1/databases/{database_id}/query',
                headers=headers,
                json=data
            )

            if response.status_code != 200:
                return jsonify({'error': f'Notion API error: {response.text}'}), 400

            results = response.json()

            return jsonify({
                'success': True,
                'results': results.get('results', []),
                'has_more': results.get('has_more', False)
            })

        except Exception as e:
            print(f"Error querying notion database: {str(e)}")
            return jsonify({'error': str(e)}), 500
