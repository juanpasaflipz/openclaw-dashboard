"""
Google Drive integration routes - Access and manage files
"""
from flask import jsonify, request, session
from models import db, User, Superpower
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from datetime import datetime
import json
import os
import io


def get_drive_service(user_id):
    """
    Get authenticated Google Drive API service for a user.

    Returns:
        Drive API service object or (None, error_message)
    """
    try:
        # Get Drive superpower for user
        superpower = Superpower.query.filter_by(
            user_id=user_id,
            service_type='google_drive',
            is_enabled=True
        ).first()

        if not superpower:
            return None, 'Google Drive not connected'

        if not superpower.access_token_encrypted:
            return None, 'Drive access token missing'

        # Create credentials object with OAuth client info for token refresh
        credentials = Credentials(
            token=superpower.access_token_encrypted,
            refresh_token=superpower.refresh_token_encrypted,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.environ.get('GOOGLE_CLIENT_ID'),
            client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
            scopes=json.loads(superpower.scopes_granted) if superpower.scopes_granted else []
        )

        # Build Drive service
        service = build('drive', 'v3', credentials=credentials)

        # Update last used
        superpower.last_used = datetime.utcnow()
        db.session.commit()

        return service, None

    except Exception as e:
        print(f"Error getting drive service: {str(e)}")
        return None, str(e)


def register_drive_routes(app):
    """Register Google Drive routes with the Flask app"""

    @app.route('/api/drive/files', methods=['GET'])
    def list_drive_files():
        """List files from Google Drive"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            # Get parameters
            max_results = int(request.args.get('max_results', 20))
            folder_id = request.args.get('folder_id')  # Optional: list files in specific folder
            query = request.args.get('query')  # Optional: search query

            service, error = get_drive_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Build query
            q = []
            if folder_id:
                q.append(f"'{folder_id}' in parents")
            if query:
                q.append(f"name contains '{query}'")
            q.append("trashed = false")  # Exclude trashed files

            query_string = ' and '.join(q) if q else "trashed = false"

            # List files
            results = service.files().list(
                pageSize=max_results,
                q=query_string,
                fields='files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink, iconLink, owners)',
                orderBy='modifiedTime desc'
            ).execute()

            files = results.get('files', [])

            # Format files
            formatted_files = []
            for file in files:
                formatted_files.append({
                    'id': file['id'],
                    'name': file['name'],
                    'mimeType': file.get('mimeType', ''),
                    'size': file.get('size', '0'),
                    'createdTime': file.get('createdTime', ''),
                    'modifiedTime': file.get('modifiedTime', ''),
                    'webViewLink': file.get('webViewLink', ''),
                    'iconLink': file.get('iconLink', ''),
                    'owners': [o.get('emailAddress') for o in file.get('owners', [])]
                })

            return jsonify({
                'success': True,
                'files': formatted_files,
                'count': len(formatted_files)
            })

        except HttpError as e:
            return jsonify({'error': f'Drive API error: {str(e)}'}), 400
        except Exception as e:
            print(f"Error listing drive files: {str(e)}")
            return jsonify({'error': str(e)}), 500


    @app.route('/api/drive/files/<file_id>', methods=['GET'])
    def get_drive_file(file_id):
        """Get metadata for a specific file"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            service, error = get_drive_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            file = service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size, createdTime, modifiedTime, webViewLink, iconLink, owners, description'
            ).execute()

            return jsonify({
                'success': True,
                'file': {
                    'id': file['id'],
                    'name': file['name'],
                    'mimeType': file.get('mimeType', ''),
                    'size': file.get('size', '0'),
                    'description': file.get('description', ''),
                    'createdTime': file.get('createdTime', ''),
                    'modifiedTime': file.get('modifiedTime', ''),
                    'webViewLink': file.get('webViewLink', ''),
                    'iconLink': file.get('iconLink', ''),
                    'owners': [o.get('emailAddress') for o in file.get('owners', [])]
                }
            })

        except HttpError as e:
            return jsonify({'error': f'Drive API error: {str(e)}'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500


    @app.route('/api/drive/files/<file_id>/download', methods=['GET'])
    def download_drive_file(file_id):
        """Download file content"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            service, error = get_drive_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Get file metadata
            file = service.files().get(fileId=file_id, fields='name,mimeType,size').execute()

            # Check file size (limit to 10MB for now)
            file_size = int(file.get('size', 0))
            if file_size > 10 * 1024 * 1024:  # 10MB
                return jsonify({'error': 'File too large (max 10MB)'}), 400

            # Download file content
            request_obj = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_obj)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Get content
            content = fh.getvalue()

            return jsonify({
                'success': True,
                'name': file['name'],
                'mimeType': file['mimeType'],
                'size': len(content),
                'content': content.decode('utf-8', errors='ignore') if file['mimeType'].startswith('text/') else None,
                'message': 'Use webViewLink to view non-text files'
            })

        except HttpError as e:
            return jsonify({'error': f'Drive API error: {str(e)}'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500


    @app.route('/api/drive/folders', methods=['GET'])
    def list_drive_folders():
        """List folders from Google Drive"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            service, error = get_drive_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # List folders only
            results = service.files().list(
                pageSize=50,
                q="mimeType='application/vnd.google-apps.folder' and trashed = false",
                fields='files(id, name, createdTime, modifiedTime, webViewLink)',
                orderBy='name'
            ).execute()

            folders = results.get('files', [])

            return jsonify({
                'success': True,
                'folders': folders,
                'count': len(folders)
            })

        except HttpError as e:
            return jsonify({'error': f'Drive API error: {str(e)}'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500


    @app.route('/api/drive/folders', methods=['POST'])
    def create_drive_folder():
        """Create a new folder"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            data = request.json

            if not data.get('name'):
                return jsonify({'error': 'Folder name required'}), 400

            service, error = get_drive_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Create folder metadata
            folder_metadata = {
                'name': data['name'],
                'mimeType': 'application/vnd.google-apps.folder'
            }

            # Add parent folder if specified
            if data.get('parent_id'):
                folder_metadata['parents'] = [data['parent_id']]

            # Create folder
            folder = service.files().create(
                body=folder_metadata,
                fields='id, name, webViewLink'
            ).execute()

            return jsonify({
                'success': True,
                'folder': {
                    'id': folder['id'],
                    'name': folder['name'],
                    'webViewLink': folder.get('webViewLink', '')
                },
                'message': 'Folder created successfully'
            })

        except HttpError as e:
            return jsonify({'error': f'Drive API error: {str(e)}'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500


    @app.route('/api/drive/search', methods=['GET'])
    def search_drive():
        """Search Google Drive"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            query = request.args.get('q', '')
            if not query:
                return jsonify({'error': 'Search query required'}), 400

            service, error = get_drive_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Search
            results = service.files().list(
                pageSize=20,
                q=f"fullText contains '{query}' and trashed = false",
                fields='files(id, name, mimeType, webViewLink, modifiedTime)',
                orderBy='modifiedTime desc'
            ).execute()

            files = results.get('files', [])

            return jsonify({
                'success': True,
                'results': files,
                'count': len(files)
            })

        except HttpError as e:
            return jsonify({'error': f'Drive API error: {str(e)}'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
