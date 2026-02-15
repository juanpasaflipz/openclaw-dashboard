"""
adapters.calendar — Google Calendar event operations.
"""
from __future__ import annotations

from typing import Any


def create_event(user_id: int, action_data: dict[str, Any]) -> tuple[dict | None, str | None]:
    """Create a Google Calendar event.

    Returns:
        (result_dict, None) on success or (None, error_message) on failure.
    """
    from routes.calendar_routes import get_calendar_service

    service, error = get_calendar_service(user_id)
    if error:
        return None, error

    event_body = {
        'summary': action_data.get('summary', 'Untitled Event'),
        'start': action_data.get('start', {}),
        'end': action_data.get('end', {}),
    }
    if action_data.get('description'):
        event_body['description'] = action_data['description']
    if action_data.get('location'):
        event_body['location'] = action_data['location']
    if action_data.get('attendees'):
        event_body['attendees'] = [{'email': e} for e in action_data['attendees']]

    created = service.events().insert(
        calendarId='primary',
        body=event_body,
        sendUpdates='all' if action_data.get('attendees') else 'none'
    ).execute()

    return {
        'event_id': created['id'],
        'html_link': created.get('htmlLink', ''),
    }, None


def update_event(user_id: int, action_data: dict[str, Any]) -> tuple[dict | None, str | None]:
    """Patch an existing Google Calendar event."""
    from routes.calendar_routes import get_calendar_service

    service, error = get_calendar_service(user_id)
    if error:
        return None, error

    event_id = action_data.get('event_id')
    if not event_id:
        return None, 'event_id required'

    update_body = {}
    for key in ('summary', 'description', 'start', 'end', 'location'):
        if action_data.get(key):
            update_body[key] = action_data[key]

    updated = service.events().patch(
        calendarId='primary',
        eventId=event_id,
        body=update_body,
    ).execute()

    return {
        'event_id': updated['id'],
        'html_link': updated.get('htmlLink', ''),
    }, None


def delete_event(user_id: int, action_data: dict[str, Any]) -> tuple[dict | None, str | None]:
    """Delete a Google Calendar event."""
    from routes.calendar_routes import get_calendar_service

    service, error = get_calendar_service(user_id)
    if error:
        return None, error

    event_id = action_data.get('event_id')
    if not event_id:
        return None, 'event_id required'

    service.events().delete(
        calendarId='primary',
        eventId=event_id,
    ).execute()

    return {'deleted_event_id': event_id}, None
