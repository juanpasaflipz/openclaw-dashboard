"""
adapters.gmail — Send emails via the Gmail API.
"""
from __future__ import annotations

import base64
import json
from email.mime.text import MIMEText
from typing import Any


def send_email(user_id: int, action_data: dict[str, Any]) -> tuple[dict | None, str | None]:
    """Send an email through the authenticated user's Gmail account.

    Args:
        user_id: Owner of the Gmail superpower.
        action_data: Must contain 'to', 'subject', 'body'.

    Returns:
        (result_dict, None) on success or (None, error_message) on failure.
    """
    from routes.gmail_routes import get_gmail_service

    service, error = get_gmail_service(user_id)
    if error:
        return None, error

    message = MIMEText(action_data['body'])
    message['To'] = action_data['to']
    message['Subject'] = action_data['subject']

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    sent_message = service.users().messages().send(
        userId='me',
        body={'raw': raw}
    ).execute()

    return {'message_id': sent_message['id']}, None
