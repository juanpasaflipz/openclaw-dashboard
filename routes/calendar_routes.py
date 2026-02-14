"""
Google Calendar integration routes - View and manage calendar events
"""
from flask import jsonify, request, session
from models import db, User, Superpower
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import json
import os


def get_calendar_service(user_id):
    """
    Get authenticated Google Calendar API service for a user.

    Returns:
        Calendar API service object or (None, error_message)
    """
    try:
        # Get Calendar superpower for user
        superpower = Superpower.query.filter_by(
            user_id=user_id,
            service_type='google_calendar',
            is_enabled=True
        ).first()

        if not superpower:
            return None, 'Google Calendar not connected'

        if not superpower.access_token_encrypted:
            return None, 'Calendar access token missing'

        # Create credentials object with OAuth client info for token refresh
        credentials = Credentials(
            token=superpower.access_token_encrypted,
            refresh_token=superpower.refresh_token_encrypted,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.environ.get('GOOGLE_CLIENT_ID'),
            client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
            scopes=json.loads(superpower.scopes_granted) if superpower.scopes_granted else []
        )

        # Build Calendar service
        service = build('calendar', 'v3', credentials=credentials)

        # Update last used
        superpower.last_used = datetime.utcnow()
        db.session.commit()

        return service, None

    except Exception as e:
        print(f"Error getting calendar service: {str(e)}")
        return None, str(e)


def register_calendar_routes(app):
    """Register Google Calendar routes with the Flask app"""

    @app.route('/api/calendar/events', methods=['GET'])
    def list_calendar_events():
        """Get upcoming calendar events"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            # Get parameters
            max_results = int(request.args.get('max_results', 10))
            days_ahead = int(request.args.get('days_ahead', 7))

            # Get Calendar service
            service, error = get_calendar_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Get events from primary calendar
            now = datetime.utcnow().isoformat() + 'Z'
            time_max = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'

            events_result = service.events().list(
                calendarId='primary',
                timeMin=now,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Format events
            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))

                formatted_events.append({
                    'id': event['id'],
                    'summary': event.get('summary', 'No title'),
                    'description': event.get('description', ''),
                    'start': start,
                    'end': end,
                    'location': event.get('location', ''),
                    'attendees': [a.get('email') for a in event.get('attendees', [])],
                    'htmlLink': event.get('htmlLink', ''),
                    'status': event.get('status', 'confirmed')
                })

            return jsonify({
                'success': True,
                'events': formatted_events,
                'count': len(formatted_events)
            })

        except HttpError as e:
            return jsonify({'error': f'Calendar API error: {str(e)}'}), 400
        except Exception as e:
            print(f"Error listing calendar events: {str(e)}")
            return jsonify({'error': 'An internal error occurred'}), 500


    @app.route('/api/calendar/events/<event_id>', methods=['GET'])
    def get_calendar_event(event_id):
        """Get details of a specific event"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            service, error = get_calendar_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            event = service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()

            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))

            return jsonify({
                'success': True,
                'event': {
                    'id': event['id'],
                    'summary': event.get('summary', 'No title'),
                    'description': event.get('description', ''),
                    'start': start,
                    'end': end,
                    'location': event.get('location', ''),
                    'attendees': [a.get('email') for a in event.get('attendees', [])],
                    'htmlLink': event.get('htmlLink', ''),
                    'status': event.get('status', 'confirmed'),
                    'creator': event.get('creator', {}).get('email', '')
                }
            })

        except HttpError as e:
            return jsonify({'error': f'Calendar API error: {str(e)}'}), 400
        except Exception as e:
            print(f"Error getting calendar event: {str(e)}")
            return jsonify({'error': 'An internal error occurred'}), 500


    @app.route('/api/calendar/events', methods=['POST'])
    def create_calendar_event():
        """Create a new calendar event"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            data = request.json

            # Validate required fields
            if not data.get('summary'):
                return jsonify({'error': 'Event summary required'}), 400
            if not data.get('start'):
                return jsonify({'error': 'Event start time required'}), 400
            if not data.get('end'):
                return jsonify({'error': 'Event end time required'}), 400

            service, error = get_calendar_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Build event object
            event = {
                'summary': data['summary'],
                'description': data.get('description', ''),
                'start': {
                    'dateTime': data['start'],
                    'timeZone': data.get('timeZone', 'UTC'),
                },
                'end': {
                    'dateTime': data['end'],
                    'timeZone': data.get('timeZone', 'UTC'),
                },
            }

            # Optional fields
            if data.get('location'):
                event['location'] = data['location']

            if data.get('attendees'):
                event['attendees'] = [{'email': email} for email in data['attendees']]

            # Create event
            created_event = service.events().insert(
                calendarId='primary',
                body=event,
                sendUpdates='all' if data.get('attendees') else 'none'
            ).execute()

            return jsonify({
                'success': True,
                'event_id': created_event['id'],
                'htmlLink': created_event.get('htmlLink', ''),
                'message': 'Event created successfully'
            })

        except HttpError as e:
            return jsonify({'error': f'Calendar API error: {str(e)}'}), 400
        except Exception as e:
            print(f"Error creating calendar event: {str(e)}")
            return jsonify({'error': 'An internal error occurred'}), 500


    @app.route('/api/calendar/events/<event_id>', methods=['PUT'])
    def update_calendar_event(event_id):
        """Update an existing calendar event"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            data = request.json

            service, error = get_calendar_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            # Get existing event
            event = service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()

            # Update fields
            if data.get('summary'):
                event['summary'] = data['summary']
            if data.get('description'):
                event['description'] = data['description']
            if data.get('start'):
                event['start'] = {
                    'dateTime': data['start'],
                    'timeZone': data.get('timeZone', 'UTC')
                }
            if data.get('end'):
                event['end'] = {
                    'dateTime': data['end'],
                    'timeZone': data.get('timeZone', 'UTC')
                }
            if data.get('location'):
                event['location'] = data['location']

            # Update event
            updated_event = service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event,
                sendUpdates='all'
            ).execute()

            return jsonify({
                'success': True,
                'event_id': updated_event['id'],
                'message': 'Event updated successfully'
            })

        except HttpError as e:
            return jsonify({'error': f'Calendar API error: {str(e)}'}), 400
        except Exception as e:
            print(f"Error updating calendar event: {str(e)}")
            return jsonify({'error': 'An internal error occurred'}), 500


    @app.route('/api/calendar/events/<event_id>', methods=['DELETE'])
    def delete_calendar_event(event_id):
        """Delete a calendar event"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            service, error = get_calendar_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            service.events().delete(
                calendarId='primary',
                eventId=event_id,
                sendUpdates='all'
            ).execute()

            return jsonify({
                'success': True,
                'message': 'Event deleted successfully'
            })

        except HttpError as e:
            return jsonify({'error': f'Calendar API error: {str(e)}'}), 400
        except Exception as e:
            print(f"Error deleting calendar event: {str(e)}")
            return jsonify({'error': 'An internal error occurred'}), 500


    @app.route('/api/calendar/free-busy', methods=['POST'])
    def check_free_busy():
        """Check free/busy status for time slots"""
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        user_id = session['user_id']

        try:
            data = request.json

            if not data.get('timeMin') or not data.get('timeMax'):
                return jsonify({'error': 'timeMin and timeMax required'}), 400

            service, error = get_calendar_service(user_id)
            if error:
                return jsonify({'error': error}), 400

            body = {
                'timeMin': data['timeMin'],
                'timeMax': data['timeMax'],
                'items': [{'id': 'primary'}]
            }

            freebusy = service.freebusy().query(body=body).execute()

            busy_times = freebusy['calendars']['primary'].get('busy', [])

            return jsonify({
                'success': True,
                'busy': busy_times,
                'available': len(busy_times) == 0
            })

        except HttpError as e:
            return jsonify({'error': f'Calendar API error: {str(e)}'}), 400
        except Exception as e:
            print(f"Error checking free/busy: {str(e)}")
            return jsonify({'error': 'An internal error occurred'}), 500
