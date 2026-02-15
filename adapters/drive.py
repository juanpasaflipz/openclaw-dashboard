"""
adapters.drive — Google Drive file operations.
"""
from __future__ import annotations

from typing import Any


def create_folder(user_id: int, action_data: dict[str, Any]) -> tuple[dict | None, str | None]:
    """Create a folder in Google Drive.

    Returns:
        (result_dict, None) on success or (None, error_message) on failure.
    """
    from routes.drive_routes import get_drive_service

    service, error = get_drive_service(user_id)
    if error:
        return None, error

    file_metadata = {
        'name': action_data.get('name', 'Untitled Folder'),
        'mimeType': 'application/vnd.google-apps.folder',
    }
    if action_data.get('parent_id'):
        file_metadata['parents'] = [action_data['parent_id']]

    created = service.files().create(
        body=file_metadata,
        fields='id, name, webViewLink',
    ).execute()

    return {
        'folder_id': created['id'],
        'name': created.get('name', ''),
        'web_link': created.get('webViewLink', ''),
    }, None


def upload_file(user_id: int, action_data: dict[str, Any]) -> tuple[dict | None, str | None]:
    """Upload a file to Google Drive."""
    from routes.drive_routes import get_drive_service
    from googleapiclient.http import MediaInMemoryUpload

    service, error = get_drive_service(user_id)
    if error:
        return None, error

    file_metadata = {
        'name': action_data.get('name', 'untitled.txt'),
    }
    if action_data.get('parent_id'):
        file_metadata['parents'] = [action_data['parent_id']]

    content = action_data.get('content', '')
    mime_type = action_data.get('mime_type', 'text/plain')
    media = MediaInMemoryUpload(
        content.encode('utf-8'),
        mimetype=mime_type,
        resumable=False,
    )

    created = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, webViewLink',
    ).execute()

    return {
        'file_id': created['id'],
        'name': created.get('name', ''),
        'web_link': created.get('webViewLink', ''),
    }, None
