"""
Spotify integration routes - Profile, playlists, now playing
"""
from flask import jsonify, session
from models import db, Superpower
from datetime import datetime
import requests as http_requests

from routes.oauth_routes import refresh_oauth_token


def get_spotify_headers(user_id):
    """Get Spotify API headers, refreshing token if expired (tokens expire hourly)"""
    superpower = Superpower.query.filter_by(
        user_id=user_id,
        service_type='spotify',
        is_enabled=True
    ).first()

    if not superpower:
        return None, 'Spotify not connected'
    if not superpower.access_token_encrypted:
        return None, 'Spotify access token missing'

    # Spotify tokens expire every hour — refresh if needed
    if superpower.token_expires_at and superpower.token_expires_at < datetime.utcnow():
        if not refresh_oauth_token(superpower, 'spotify'):
            return None, 'Spotify token expired and refresh failed. Please reconnect.'

    headers = {
        'Authorization': f'Bearer {superpower.access_token_encrypted}',
    }

    superpower.last_used = datetime.utcnow()
    db.session.commit()

    return headers, None


def register_spotify_routes(app):
    """Register Spotify routes"""

    @app.route('/api/spotify/me', methods=['GET'])
    def spotify_me():
        """Get Spotify user profile"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_spotify_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get('https://api.spotify.com/v1/me', headers=headers)
            if resp.status_code != 200:
                return jsonify({'error': f'Spotify API error: {resp.text}'}), resp.status_code

            profile = resp.json()
            return jsonify({
                'success': True,
                'profile': {
                    'display_name': profile.get('display_name'),
                    'email': profile.get('email'),
                    'id': profile.get('id'),
                    'product': profile.get('product'),
                    'followers': profile.get('followers', {}).get('total', 0),
                    'images': profile.get('images', []),
                }
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/spotify/playlists', methods=['GET'])
    def spotify_playlists():
        """List user's playlists"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_spotify_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                'https://api.spotify.com/v1/me/playlists',
                headers=headers,
                params={'limit': 20}
            )
            if resp.status_code != 200:
                return jsonify({'error': f'Spotify API error: {resp.text}'}), resp.status_code

            data = resp.json()
            return jsonify({
                'success': True,
                'playlists': [{
                    'id': p['id'],
                    'name': p['name'],
                    'description': p.get('description', ''),
                    'tracks_total': p.get('tracks', {}).get('total', 0),
                    'public': p.get('public'),
                    'external_url': p.get('external_urls', {}).get('spotify'),
                    'images': p.get('images', []),
                } for p in data.get('items', [])]
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/spotify/now-playing', methods=['GET'])
    def spotify_now_playing():
        """Get currently playing track"""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        headers, error = get_spotify_headers(user_id)
        if error:
            return jsonify({'error': error}), 400

        try:
            resp = http_requests.get(
                'https://api.spotify.com/v1/me/player/currently-playing',
                headers=headers
            )

            # 204 means nothing is currently playing
            if resp.status_code == 204:
                return jsonify({'success': True, 'is_playing': False, 'track': None})

            if resp.status_code != 200:
                return jsonify({'error': f'Spotify API error: {resp.text}'}), resp.status_code

            data = resp.json()
            track = data.get('item')
            if not track:
                return jsonify({'success': True, 'is_playing': False, 'track': None})

            return jsonify({
                'success': True,
                'is_playing': data.get('is_playing', False),
                'track': {
                    'name': track.get('name'),
                    'artists': [a['name'] for a in track.get('artists', [])],
                    'album': track.get('album', {}).get('name'),
                    'duration_ms': track.get('duration_ms'),
                    'progress_ms': data.get('progress_ms'),
                    'external_url': track.get('external_urls', {}).get('spotify'),
                    'images': track.get('album', {}).get('images', []),
                }
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500
