"""
Agent Tool Registry — lets AI agents call the app's service APIs as tools.

Public API:
    get_tools_for_user(user_id)   → list of OpenAI-format tool schemas
    execute_tool(name, uid, args) → dict result
    get_tools_system_prompt(uid)  → str for LLM system prompt
"""
import base64
import json
import os
import requests as http_requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models import db, Superpower, ConfigFile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _superpower(user_id, service_type):
    """Return enabled Superpower row or None."""
    return Superpower.query.filter_by(
        user_id=user_id, service_type=service_type, is_enabled=True
    ).first()


def _fn_schema(name, description, parameters=None):
    """Build an OpenAI function-calling tool schema."""
    schema = {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': parameters or {'type': 'object', 'properties': {}, 'required': []},
        },
    }
    return schema


# ---------------------------------------------------------------------------
# Meta tool executors (always available)
# ---------------------------------------------------------------------------

def _exec_list_connected_services(user_id, params):
    superpowers = Superpower.query.filter_by(user_id=user_id, is_enabled=True).all()
    return {
        'connected_services': [
            {'service_type': sp.service_type, 'service_name': sp.service_name,
             'connected_at': sp.connected_at.isoformat() if sp.connected_at else None}
            for sp in superpowers
        ],
        'count': len(superpowers),
    }


def _exec_connect_service(user_id, params):
    provider = params.get('provider', '').lower()
    # Google services use a different OAuth route
    google_services = {'gmail', 'calendar', 'drive'}
    # OAuth providers via generic flow
    oauth_providers = {'slack', 'github', 'discord', 'spotify', 'todoist', 'dropbox'}
    # Telegram uses bot token (not OAuth)
    if provider == 'telegram':
        return {'instructions': 'Telegram uses a bot token, not OAuth. The user should go to the Connect tab in the dashboard and enter their bot token from @BotFather.'}
    # Binance uses API keys
    if provider == 'binance':
        return {'instructions': 'Binance uses API key + secret. The user should go to the Connect tab and enter their Binance API credentials.'}
    # Notion uses internal integration
    if provider == 'notion':
        return {'instructions': 'Notion uses an integration token. The user should go to the Connect tab and enter their Notion internal integration token.'}

    base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
    if provider in google_services:
        authorization_url = f'{base_url}/api/oauth/google/start/{provider}'
        return {'authorization_url': authorization_url, 'provider': provider,
                'instructions': f'Opening {provider.title()} authorization. Please approve access in the popup.'}
    elif provider in oauth_providers:
        authorization_url = f'{base_url}/api/oauth/{provider}/start'
        return {'authorization_url': authorization_url, 'provider': provider,
                'instructions': f'Opening {provider.title()} authorization. Please approve access in the popup.'}
    else:
        available = sorted(google_services | oauth_providers | {'telegram', 'binance', 'notion'})
        return {'error': f'Unknown provider "{provider}". Available: {", ".join(available)}'}


# ---------------------------------------------------------------------------
# Service tool executors
# ---------------------------------------------------------------------------

# --- GitHub ---
def _exec_get_github_repos(user_id, params):
    from routes.github_routes import get_github_headers
    headers, err = get_github_headers(user_id)
    if err:
        return {'error': err}
    resp = http_requests.get('https://api.github.com/user/repos?per_page=30&sort=updated', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'GitHub API error ({resp.status_code})'}
    return {'repos': [{'name': r['full_name'], 'description': r.get('description', ''),
                        'stars': r['stargazers_count'], 'language': r.get('language'),
                        'updated_at': r['updated_at']} for r in resp.json()[:20]]}


def _exec_get_github_issues(user_id, params):
    from routes.github_routes import get_github_headers
    headers, err = get_github_headers(user_id)
    if err:
        return {'error': err}
    owner = params.get('owner', '')
    repo = params.get('repo', '')
    if not owner or not repo:
        return {'error': 'owner and repo are required'}
    resp = http_requests.get(f'https://api.github.com/repos/{owner}/{repo}/issues?per_page=20&state=open', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'GitHub API error ({resp.status_code})'}
    return {'issues': [{'number': i['number'], 'title': i['title'], 'state': i['state'],
                         'user': i['user']['login'], 'created_at': i['created_at']}
                        for i in resp.json()[:15]]}


# --- Slack ---
def _exec_get_slack_channels(user_id, params):
    from routes.slack_routes import get_slack_headers
    headers, err = get_slack_headers(user_id)
    if err:
        return {'error': err}
    resp = http_requests.get('https://slack.com/api/conversations.list?limit=50&types=public_channel,private_channel', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'Slack API error ({resp.status_code})'}
    data = resp.json()
    if not data.get('ok'):
        return {'error': data.get('error', 'Slack API error')}
    return {'channels': [{'id': c['id'], 'name': c['name'], 'topic': c.get('topic', {}).get('value', '')}
                          for c in data.get('channels', [])[:30]]}


def _exec_get_slack_messages(user_id, params):
    from routes.slack_routes import get_slack_headers
    headers, err = get_slack_headers(user_id)
    if err:
        return {'error': err}
    channel_id = params.get('channel_id', '')
    if not channel_id:
        return {'error': 'channel_id is required'}
    resp = http_requests.get(f'https://slack.com/api/conversations.history?channel={channel_id}&limit=20', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'Slack API error ({resp.status_code})'}
    data = resp.json()
    if not data.get('ok'):
        return {'error': data.get('error', 'Slack API error')}
    return {'messages': [{'text': m.get('text', ''), 'user': m.get('user', ''), 'ts': m.get('ts')}
                          for m in data.get('messages', [])[:15]]}


# --- Spotify ---
def _exec_get_spotify_profile(user_id, params):
    from routes.spotify_routes import get_spotify_headers
    headers, err = get_spotify_headers(user_id)
    if err:
        return {'error': err}
    resp = http_requests.get('https://api.spotify.com/v1/me', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'Spotify API error ({resp.status_code})'}
    d = resp.json()
    return {'display_name': d.get('display_name'), 'email': d.get('email'),
            'followers': d.get('followers', {}).get('total', 0),
            'product': d.get('product'), 'country': d.get('country')}


def _exec_get_spotify_playlists(user_id, params):
    from routes.spotify_routes import get_spotify_headers
    headers, err = get_spotify_headers(user_id)
    if err:
        return {'error': err}
    resp = http_requests.get('https://api.spotify.com/v1/me/playlists?limit=20', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'Spotify API error ({resp.status_code})'}
    data = resp.json()
    return {'playlists': [{'name': p['name'], 'tracks': p['tracks']['total'],
                            'public': p.get('public'), 'id': p['id']}
                           for p in data.get('items', [])]}


def _exec_get_spotify_now_playing(user_id, params):
    from routes.spotify_routes import get_spotify_headers
    headers, err = get_spotify_headers(user_id)
    if err:
        return {'error': err}
    resp = http_requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers=headers, timeout=15)
    if resp.status_code == 204 or not resp.content:
        return {'playing': False, 'message': 'Nothing is currently playing'}
    if not resp.ok:
        return {'error': f'Spotify API error ({resp.status_code})'}
    d = resp.json()
    item = d.get('item', {})
    artists = ', '.join(a['name'] for a in item.get('artists', []))
    return {'playing': d.get('is_playing', False), 'track': item.get('name'),
            'artists': artists, 'album': item.get('album', {}).get('name')}


# --- Telegram ---
def _exec_get_telegram_bot_info(user_id, params):
    sp = _superpower(user_id, 'telegram')
    if not sp:
        return {'error': 'Telegram not connected'}
    token = sp.access_token_encrypted
    resp = http_requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=15)
    if not resp.ok:
        return {'error': f'Telegram API error ({resp.status_code})'}
    d = resp.json()
    bot = d.get('result', {})
    sp.last_used = datetime.utcnow()
    db.session.commit()
    return {'username': bot.get('username'), 'first_name': bot.get('first_name'),
            'can_join_groups': bot.get('can_join_groups'), 'id': bot.get('id')}


def _exec_get_telegram_updates(user_id, params):
    sp = _superpower(user_id, 'telegram')
    if not sp:
        return {'error': 'Telegram not connected'}
    token = sp.access_token_encrypted
    resp = http_requests.get(f'https://api.telegram.org/bot{token}/getUpdates?limit=10', timeout=15)
    if not resp.ok:
        return {'error': f'Telegram API error ({resp.status_code})'}
    d = resp.json()
    sp.last_used = datetime.utcnow()
    db.session.commit()
    updates = d.get('result', [])
    return {'updates': [{'update_id': u['update_id'],
                          'message': u.get('message', {}).get('text', ''),
                          'from': u.get('message', {}).get('from', {}).get('username', '')}
                         for u in updates[-10:]]}


# --- Todoist ---
def _exec_get_todoist_projects(user_id, params):
    from routes.todoist_routes import get_todoist_headers
    headers, err = get_todoist_headers(user_id)
    if err:
        return {'error': err}
    resp = http_requests.get('https://api.todoist.com/rest/v2/projects', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'Todoist API error ({resp.status_code})'}
    return {'projects': [{'id': p['id'], 'name': p['name'], 'color': p.get('color'),
                           'is_favorite': p.get('is_favorite')} for p in resp.json()]}


def _exec_get_todoist_tasks(user_id, params):
    from routes.todoist_routes import get_todoist_headers
    headers, err = get_todoist_headers(user_id)
    if err:
        return {'error': err}
    url = 'https://api.todoist.com/rest/v2/tasks'
    project_id = params.get('project_id')
    if project_id:
        url += f'?project_id={project_id}'
    resp = http_requests.get(url, headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'Todoist API error ({resp.status_code})'}
    return {'tasks': [{'id': t['id'], 'content': t['content'], 'priority': t.get('priority'),
                        'due': t.get('due', {}).get('string') if t.get('due') else None,
                        'is_completed': t.get('is_completed')}
                       for t in resp.json()[:30]]}


# --- Discord ---
def _exec_get_discord_guilds(user_id, params):
    from routes.discord_routes import get_discord_headers
    headers, err = get_discord_headers(user_id)
    if err:
        return {'error': err}
    resp = http_requests.get('https://discord.com/api/v10/users/@me/guilds', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'Discord API error ({resp.status_code})'}
    return {'guilds': [{'id': g['id'], 'name': g['name'], 'owner': g.get('owner', False)}
                        for g in resp.json()[:25]]}


def _exec_get_discord_channels(user_id, params):
    from routes.discord_routes import get_discord_headers
    headers, err = get_discord_headers(user_id)
    if err:
        return {'error': err}
    guild_id = params.get('guild_id', '')
    if not guild_id:
        return {'error': 'guild_id is required'}
    resp = http_requests.get(f'https://discord.com/api/v10/guilds/{guild_id}/channels', headers=headers, timeout=15)
    if not resp.ok:
        return {'error': f'Discord API error ({resp.status_code})'}
    return {'channels': [{'id': c['id'], 'name': c['name'], 'type': c['type']}
                          for c in resp.json() if c['type'] in (0, 2, 5)]}  # text, voice, announcement


# --- Dropbox ---
def _exec_get_dropbox_files(user_id, params):
    from routes.dropbox_routes import get_dropbox_headers
    headers, err = get_dropbox_headers(user_id)
    if err:
        return {'error': err}
    path = params.get('path', '')
    resp = http_requests.post('https://api.dropboxapi.com/2/files/list_folder',
                              headers=headers, json={'path': path, 'limit': 25}, timeout=15)
    if not resp.ok:
        return {'error': f'Dropbox API error ({resp.status_code})'}
    entries = resp.json().get('entries', [])
    return {'files': [{'name': e['name'], 'type': e['.tag'], 'path': e.get('path_display', ''),
                        'size': e.get('size')} for e in entries]}


def _exec_get_dropbox_metadata(user_id, params):
    from routes.dropbox_routes import get_dropbox_headers
    headers, err = get_dropbox_headers(user_id)
    if err:
        return {'error': err}
    path = params.get('path', '')
    if not path:
        return {'error': 'path is required'}
    resp = http_requests.post('https://api.dropboxapi.com/2/files/get_metadata',
                              headers=headers, json={'path': path}, timeout=15)
    if not resp.ok:
        return {'error': f'Dropbox API error ({resp.status_code})'}
    d = resp.json()
    return {'name': d.get('name'), 'type': d.get('.tag'), 'path': d.get('path_display'),
            'size': d.get('size'), 'modified': d.get('server_modified')}


# --- Gmail ---
def _exec_get_gmail_recent(user_id, params):
    from routes.gmail_routes import get_gmail_service
    service, err = get_gmail_service(user_id)
    if err:
        return {'error': err}
    try:
        results = service.users().messages().list(userId='me', maxResults=10).execute()
        messages = results.get('messages', [])
        emails = []
        for msg_ref in messages[:10]:
            msg = service.users().messages().get(userId='me', id=msg_ref['id'], format='metadata',
                                                  metadataHeaders=['Subject', 'From', 'Date']).execute()
            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
            emails.append({'id': msg_ref['id'], 'subject': headers.get('Subject', ''),
                           'from': headers.get('From', ''), 'date': headers.get('Date', ''),
                           'snippet': msg.get('snippet', '')})
        return {'emails': emails}
    except Exception as e:
        return {'error': str(e)[:200]}


def _exec_get_gmail_email(user_id, params):
    from routes.gmail_routes import get_gmail_service
    service, err = get_gmail_service(user_id)
    if err:
        return {'error': err}
    email_id = params.get('email_id', '')
    if not email_id:
        return {'error': 'email_id is required'}
    try:
        msg = service.users().messages().get(userId='me', id=email_id, format='metadata',
                                              metadataHeaders=['Subject', 'From', 'To', 'Date']).execute()
        headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
        return {'id': email_id, 'subject': headers.get('Subject', ''), 'from': headers.get('From', ''),
                'to': headers.get('To', ''), 'date': headers.get('Date', ''),
                'snippet': msg.get('snippet', ''), 'labels': msg.get('labelIds', [])}
    except Exception as e:
        return {'error': str(e)[:200]}


# --- Google Calendar ---
def _exec_get_calendar_events(user_id, params):
    from routes.calendar_routes import get_calendar_service
    service, err = get_calendar_service(user_id)
    if err:
        return {'error': err}
    try:
        now = datetime.utcnow().isoformat() + 'Z'
        result = service.events().list(calendarId='primary', timeMin=now, maxResults=15,
                                        singleEvents=True, orderBy='startTime').execute()
        events = result.get('items', [])
        return {'events': [{'summary': e.get('summary', 'No title'),
                             'start': e.get('start', {}).get('dateTime', e.get('start', {}).get('date', '')),
                             'end': e.get('end', {}).get('dateTime', e.get('end', {}).get('date', '')),
                             'location': e.get('location', '')} for e in events]}
    except Exception as e:
        return {'error': str(e)[:200]}


# --- Google Drive ---
def _exec_get_drive_files(user_id, params):
    from routes.drive_routes import get_drive_service
    service, err = get_drive_service(user_id)
    if err:
        return {'error': err}
    try:
        result = service.files().list(pageSize=20, fields='files(id,name,mimeType,modifiedTime,size)',
                                       orderBy='modifiedTime desc').execute()
        return {'files': [{'id': f['id'], 'name': f['name'], 'type': f.get('mimeType', ''),
                            'modified': f.get('modifiedTime', ''), 'size': f.get('size')}
                           for f in result.get('files', [])]}
    except Exception as e:
        return {'error': str(e)[:200]}


def _exec_search_drive(user_id, params):
    from routes.drive_routes import get_drive_service
    service, err = get_drive_service(user_id)
    if err:
        return {'error': err}
    query = params.get('query', '')
    if not query:
        return {'error': 'query is required'}
    try:
        result = service.files().list(q=f"name contains '{query}'", pageSize=15,
                                       fields='files(id,name,mimeType,modifiedTime)').execute()
        return {'files': [{'id': f['id'], 'name': f['name'], 'type': f.get('mimeType', ''),
                            'modified': f.get('modifiedTime', '')}
                           for f in result.get('files', [])]}
    except Exception as e:
        return {'error': str(e)[:200]}


# --- Notion ---
def _exec_search_notion(user_id, params):
    from routes.notion_routes import get_notion_headers
    headers, err = get_notion_headers(user_id)
    if err:
        return {'error': err}
    query = params.get('query', '')
    payload = {'page_size': 15}
    if query:
        payload['query'] = query
    resp = http_requests.post('https://api.notion.com/v1/search', headers=headers, json=payload, timeout=15)
    if not resp.ok:
        return {'error': f'Notion API error ({resp.status_code})'}
    results = resp.json().get('results', [])
    return {'results': [{'id': r['id'], 'type': r['object'],
                          'title': _notion_title(r)} for r in results[:15]]}


def _notion_title(obj):
    """Extract title from a Notion page/database object."""
    props = obj.get('properties', {})
    for v in props.values():
        if v.get('type') == 'title':
            parts = v.get('title', [])
            return ''.join(p.get('plain_text', '') for p in parts)
    return obj.get('url', 'Untitled')


# --- Binance ---
def _exec_get_binance_portfolio(user_id, params):
    try:
        from binance_service import get_portfolio
    except ImportError:
        return {'error': 'Binance service not available'}
    portfolio, err = get_portfolio(user_id)
    if err:
        return {'error': err}
    return portfolio


def _exec_get_binance_prices(user_id, params):
    try:
        from binance_service import get_binance_client
    except ImportError:
        return {'error': 'Binance service not available'}
    symbols = params.get('symbols', ['BTC/USDT', 'ETH/USDT'])
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(',')]
    client, err = get_binance_client(user_id)
    if err:
        return {'error': err}
    try:
        prices = {}
        for sym in symbols[:10]:
            ticker = client.fetch_ticker(sym)
            prices[sym] = {'last': ticker.get('last'), 'change_pct': ticker.get('percentage'),
                           'high': ticker.get('high'), 'low': ticker.get('low')}
        return {'prices': prices}
    except Exception as e:
        return {'error': str(e)[:200]}


# ---------------------------------------------------------------------------
# Write tool executors
# ---------------------------------------------------------------------------

# --- Gmail writes ---
def _exec_send_email(user_id, params):
    from routes.gmail_routes import get_gmail_service
    service, err = get_gmail_service(user_id)
    if err:
        return {'error': err}
    to = params.get('to', '')
    subject = params.get('subject', '')
    body = params.get('body', '')
    if not to or not subject or not body:
        return {'error': 'to, subject, and body are required'}
    try:
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject
        message.attach(MIMEText(body, 'plain'))
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        sent = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        return {'success': True, 'message_id': sent.get('id'), 'to': to, 'subject': subject}
    except Exception as e:
        return {'error': str(e)[:200]}


def _exec_reply_to_email(user_id, params):
    from routes.gmail_routes import get_gmail_service
    service, err = get_gmail_service(user_id)
    if err:
        return {'error': err}
    email_id = params.get('email_id', '')
    body = params.get('body', '')
    if not email_id or not body:
        return {'error': 'email_id and body are required'}
    try:
        original = service.users().messages().get(userId='me', id=email_id, format='metadata',
                                                   metadataHeaders=['Subject', 'From', 'To', 'Message-ID']).execute()
        headers = {h['name']: h['value'] for h in original.get('payload', {}).get('headers', [])}
        reply_to = headers.get('From', '')
        subject = headers.get('Subject', '')
        if not subject.lower().startswith('re:'):
            subject = f'Re: {subject}'
        message_id = headers.get('Message-ID', '')

        msg = MIMEMultipart()
        msg['to'] = reply_to
        msg['subject'] = subject
        if message_id:
            msg['In-Reply-To'] = message_id
            msg['References'] = message_id
        msg.attach(MIMEText(body, 'plain'))
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        sent = service.users().messages().send(userId='me', body={'raw': raw_message, 'threadId': original.get('threadId')}).execute()
        return {'success': True, 'message_id': sent.get('id'), 'to': reply_to, 'subject': subject}
    except Exception as e:
        return {'error': str(e)[:200]}


# --- Calendar writes ---
def _exec_create_calendar_event(user_id, params):
    from routes.calendar_routes import get_calendar_service
    service, err = get_calendar_service(user_id)
    if err:
        return {'error': err}
    summary = params.get('summary', '')
    start = params.get('start', '')
    end = params.get('end', '')
    if not summary or not start or not end:
        return {'error': 'summary, start, and end are required'}
    try:
        event = {
            'summary': summary,
            'start': {'dateTime': start, 'timeZone': params.get('timeZone', 'UTC')},
            'end': {'dateTime': end, 'timeZone': params.get('timeZone', 'UTC')},
        }
        if params.get('description'):
            event['description'] = params['description']
        if params.get('location'):
            event['location'] = params['location']
        created = service.events().insert(calendarId='primary', body=event).execute()
        return {'success': True, 'event_id': created.get('id'), 'summary': summary,
                'start': start, 'end': end, 'link': created.get('htmlLink', '')}
    except Exception as e:
        return {'error': str(e)[:200]}


def _exec_delete_calendar_event(user_id, params):
    from routes.calendar_routes import get_calendar_service
    service, err = get_calendar_service(user_id)
    if err:
        return {'error': err}
    event_id = params.get('event_id', '')
    if not event_id:
        return {'error': 'event_id is required'}
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return {'success': True, 'deleted_event_id': event_id}
    except Exception as e:
        return {'error': str(e)[:200]}


# --- Drive writes ---
def _exec_create_drive_folder(user_id, params):
    from routes.drive_routes import get_drive_service
    service, err = get_drive_service(user_id)
    if err:
        return {'error': err}
    name = params.get('name', '')
    if not name:
        return {'error': 'name is required'}
    try:
        folder_metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
        if params.get('parent_id'):
            folder_metadata['parents'] = [params['parent_id']]
        folder = service.files().create(body=folder_metadata, fields='id, name, webViewLink').execute()
        return {'success': True, 'folder_id': folder.get('id'), 'name': folder.get('name'),
                'link': folder.get('webViewLink', '')}
    except Exception as e:
        return {'error': str(e)[:200]}


# --- Notion writes ---
def _exec_create_notion_page(user_id, params):
    from routes.notion_routes import get_notion_headers
    headers, err = get_notion_headers(user_id)
    if err:
        return {'error': err}
    parent_id = params.get('parent_id', '')
    title = params.get('title', '')
    if not parent_id or not title:
        return {'error': 'parent_id and title are required'}
    page_data = {
        'parent': {'page_id': parent_id},
        'properties': {
            'title': {'title': [{'text': {'content': title}}]}
        }
    }
    if params.get('content'):
        page_data['children'] = [{
            'object': 'block', 'type': 'paragraph',
            'paragraph': {'rich_text': [{'text': {'content': params['content']}}]}
        }]
    resp = http_requests.post('https://api.notion.com/v1/pages', headers=headers, json=page_data, timeout=15)
    if not resp.ok:
        return {'error': f'Notion API error ({resp.status_code}): {resp.text[:200]}'}
    result = resp.json()
    return {'success': True, 'page_id': result.get('id'), 'url': result.get('url', ''), 'title': title}


# --- GitHub writes ---
def _exec_create_github_issue(user_id, params):
    from routes.github_routes import get_github_headers
    headers, err = get_github_headers(user_id)
    if err:
        return {'error': err}
    owner = params.get('owner', '')
    repo = params.get('repo', '')
    title = params.get('title', '')
    if not owner or not repo or not title:
        return {'error': 'owner, repo, and title are required'}
    payload = {'title': title}
    if params.get('body'):
        payload['body'] = params['body']
    if params.get('labels'):
        payload['labels'] = params['labels']
    resp = http_requests.post(f'https://api.github.com/repos/{owner}/{repo}/issues',
                               headers=headers, json=payload, timeout=15)
    if not resp.ok:
        return {'error': f'GitHub API error ({resp.status_code}): {resp.text[:200]}'}
    issue = resp.json()
    return {'success': True, 'issue_number': issue.get('number'), 'title': issue.get('title'),
            'url': issue.get('html_url', '')}


def _exec_create_github_comment(user_id, params):
    from routes.github_routes import get_github_headers
    headers, err = get_github_headers(user_id)
    if err:
        return {'error': err}
    owner = params.get('owner', '')
    repo = params.get('repo', '')
    issue_number = params.get('issue_number')
    body = params.get('body', '')
    if not owner or not repo or not issue_number or not body:
        return {'error': 'owner, repo, issue_number, and body are required'}
    resp = http_requests.post(f'https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments',
                               headers=headers, json={'body': body}, timeout=15)
    if not resp.ok:
        return {'error': f'GitHub API error ({resp.status_code}): {resp.text[:200]}'}
    comment = resp.json()
    return {'success': True, 'comment_id': comment.get('id'), 'url': comment.get('html_url', '')}


# --- Slack writes ---
def _exec_send_slack_message(user_id, params):
    from routes.slack_routes import get_slack_headers
    headers, err = get_slack_headers(user_id)
    if err:
        return {'error': err}
    channel_id = params.get('channel_id', '')
    text = params.get('text', '')
    if not channel_id or not text:
        return {'error': 'channel_id and text are required'}
    resp = http_requests.post('https://slack.com/api/chat.postMessage',
                               headers=headers, json={'channel': channel_id, 'text': text}, timeout=15)
    data = resp.json()
    if not data.get('ok'):
        return {'error': data.get('error', 'Slack API error')}
    return {'success': True, 'channel': channel_id, 'message_ts': data.get('ts')}


# --- Discord writes ---
def _exec_send_discord_message(user_id, params):
    from routes.discord_routes import get_discord_headers
    headers, err = get_discord_headers(user_id)
    if err:
        return {'error': err}
    channel_id = params.get('channel_id', '')
    content = params.get('content', '')
    if not channel_id or not content:
        return {'error': 'channel_id and content are required'}
    resp = http_requests.post(f'https://discord.com/api/v10/channels/{channel_id}/messages',
                               headers=headers, json={'content': content}, timeout=15)
    if not resp.ok:
        return {'error': f'Discord API error ({resp.status_code})'}
    msg = resp.json()
    return {'success': True, 'message_id': msg.get('id'), 'channel_id': channel_id}


# --- Telegram writes ---
def _exec_send_telegram_message(user_id, params):
    sp = _superpower(user_id, 'telegram')
    if not sp:
        return {'error': 'Telegram not connected'}
    token = sp.access_token_encrypted
    chat_id = params.get('chat_id', '')
    text = params.get('text', '')
    if not chat_id or not text:
        return {'error': 'chat_id and text are required'}
    resp = http_requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                               json={'chat_id': chat_id, 'text': text}, timeout=15)
    if not resp.ok:
        return {'error': f'Telegram API error ({resp.status_code})'}
    data = resp.json()
    if not data.get('ok'):
        return {'error': data.get('description', 'Telegram API error')}
    sp.last_used = datetime.utcnow()
    db.session.commit()
    result_msg = data.get('result', {})
    return {'success': True, 'message_id': result_msg.get('message_id'), 'chat_id': chat_id}


# --- Todoist writes ---
def _exec_create_todoist_task(user_id, params):
    from routes.todoist_routes import get_todoist_headers
    headers, err = get_todoist_headers(user_id)
    if err:
        return {'error': err}
    content = params.get('content', '')
    if not content:
        return {'error': 'content is required'}
    payload = {'content': content}
    if params.get('project_id'):
        payload['project_id'] = params['project_id']
    if params.get('due_string'):
        payload['due_string'] = params['due_string']
    if params.get('priority'):
        payload['priority'] = params['priority']
    resp = http_requests.post('https://api.todoist.com/rest/v2/tasks',
                               headers=headers, json=payload, timeout=15)
    if not resp.ok:
        return {'error': f'Todoist API error ({resp.status_code})'}
    task = resp.json()
    return {'success': True, 'task_id': task.get('id'), 'content': task.get('content'),
            'url': task.get('url', '')}


def _exec_complete_todoist_task(user_id, params):
    from routes.todoist_routes import get_todoist_headers
    headers, err = get_todoist_headers(user_id)
    if err:
        return {'error': err}
    task_id = params.get('task_id', '')
    if not task_id:
        return {'error': 'task_id is required'}
    resp = http_requests.post(f'https://api.todoist.com/rest/v2/tasks/{task_id}/close',
                               headers=headers, timeout=15)
    if resp.status_code == 204:
        return {'success': True, 'task_id': task_id, 'status': 'completed'}
    if not resp.ok:
        return {'error': f'Todoist API error ({resp.status_code})'}
    return {'success': True, 'task_id': task_id, 'status': 'completed'}


# --- Spotify writes ---
def _exec_spotify_play(user_id, params):
    from routes.spotify_routes import get_spotify_headers
    headers, err = get_spotify_headers(user_id)
    if err:
        return {'error': err}
    payload = {}
    uri = params.get('uri', '')
    if uri:
        if ':track:' in uri:
            payload['uris'] = [uri]
        else:
            payload['context_uri'] = uri
    resp = http_requests.put('https://api.spotify.com/v1/me/player/play',
                              headers=headers, json=payload if payload else None, timeout=15)
    if resp.status_code == 204:
        return {'success': True, 'action': 'playback started', 'uri': uri or 'resumed current'}
    if resp.status_code == 403:
        return {'error': 'Spotify Premium required for playback control'}
    if not resp.ok:
        return {'error': f'Spotify API error ({resp.status_code}): {resp.text[:200]}'}
    return {'success': True, 'action': 'playback started', 'uri': uri or 'resumed current'}


# ---------------------------------------------------------------------------
# Soul / Memory tool executors
# ---------------------------------------------------------------------------

def _exec_update_soul(user_id, params):
    """Append an observation or fact to a soul file (SOUL.md, IDENTITY.md, or USER.md)."""
    key = (params.get('key') or '').upper()
    content = (params.get('content') or '').strip()
    if key not in ('SOUL', 'IDENTITY', 'USER'):
        return {'error': 'key must be one of: SOUL, IDENTITY, USER'}
    if not content:
        return {'error': 'content is required'}

    filename = f'{key}.md'
    cfg = ConfigFile.query.filter_by(user_id=user_id, filename=filename).first()
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    entry = f'\n\n[{timestamp}] {content}'

    if cfg:
        cfg.content = (cfg.content or '') + entry
        cfg.updated_at = datetime.utcnow()
    else:
        cfg = ConfigFile(user_id=user_id, filename=filename, content=entry.strip())
        db.session.add(cfg)

    db.session.commit()
    return {'success': True, 'file': filename, 'appended': content}


def _exec_save_memory(user_id, params):
    """Save a fact or observation to semantic memory for cross-conversation recall."""
    content = (params.get('content') or '').strip()
    if not content:
        return {'error': 'content is required'}
    try:
        from memory_service import store_memory
        store_memory(user_id, content, source_type='manual', source_id=None)
        return {'success': True, 'stored': content}
    except Exception as e:
        return {'error': f'Memory storage failed: {str(e)[:200]}'}


def _exec_recall_memory(user_id, params):
    """Search past memories for relevant facts."""
    query = (params.get('query') or '').strip()
    if not query:
        return {'error': 'query is required'}
    try:
        from memory_service import search_memories
        results = search_memories(user_id, query, limit=params.get('limit', 5))
        return {'memories': results}
    except Exception as e:
        return {'error': f'Memory search failed: {str(e)[:200]}'}


# ---------------------------------------------------------------------------
# TOOL_REGISTRY
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    # -- Meta tools (always available) --
    'list_connected_services': {
        'schema': _fn_schema('list_connected_services', 'List all external services currently connected to the user\'s account.'),
        'required_service': None,
        'execute': _exec_list_connected_services,
    },
    'connect_service': {
        'schema': _fn_schema('connect_service', 'Initiate the OAuth flow to connect a new external service. Returns an authorization URL for the user.',
                             {'type': 'object', 'properties': {
                                 'provider': {'type': 'string', 'description': 'Service to connect: gmail, calendar, drive, slack, github, discord, spotify, todoist, dropbox, telegram, binance, notion'}
                             }, 'required': ['provider']}),
        'required_service': None,
        'execute': _exec_connect_service,
    },

    # -- Soul / Memory tools (always available) --
    'update_soul': {
        'schema': _fn_schema('update_soul', 'Append an observation or fact to your persistent memory files (SOUL, IDENTITY, or USER). Use this to remember important things about the user or yourself.',
                             {'type': 'object', 'properties': {
                                 'key': {'type': 'string', 'enum': ['SOUL', 'IDENTITY', 'USER'], 'description': 'Which file to update: SOUL (persistent memory), IDENTITY (your personality), USER (user profile)'},
                                 'content': {'type': 'string', 'description': 'The observation or fact to save'},
                             }, 'required': ['key', 'content']}),
        'required_service': None,
        'execute': _exec_update_soul,
    },
    'save_memory': {
        'schema': _fn_schema('save_memory', 'Save a fact or observation to semantic memory for cross-conversation recall. Use this for important facts you want to remember across conversations.',
                             {'type': 'object', 'properties': {
                                 'content': {'type': 'string', 'description': 'The fact or observation to remember'},
                             }, 'required': ['content']}),
        'required_service': None,
        'execute': _exec_save_memory,
    },
    'recall_memory': {
        'schema': _fn_schema('recall_memory', 'Search your semantic memory for relevant facts from past conversations.',
                             {'type': 'object', 'properties': {
                                 'query': {'type': 'string', 'description': 'What to search for in memory'},
                                 'limit': {'type': 'integer', 'description': 'Max results to return (default 5)', 'default': 5},
                             }, 'required': ['query']}),
        'required_service': None,
        'execute': _exec_recall_memory,
    },

    # -- GitHub --
    'get_github_repos': {
        'schema': _fn_schema('get_github_repos', 'List the user\'s GitHub repositories, sorted by recently updated.'),
        'required_service': 'github',
        'execute': _exec_get_github_repos,
    },
    'get_github_issues': {
        'schema': _fn_schema('get_github_issues', 'List open issues for a specific GitHub repository.',
                             {'type': 'object', 'properties': {
                                 'owner': {'type': 'string', 'description': 'Repository owner (user or org)'},
                                 'repo': {'type': 'string', 'description': 'Repository name'},
                             }, 'required': ['owner', 'repo']}),
        'required_service': 'github',
        'execute': _exec_get_github_issues,
    },

    # -- Slack --
    'get_slack_channels': {
        'schema': _fn_schema('get_slack_channels', 'List Slack channels the user has access to.'),
        'required_service': 'slack',
        'execute': _exec_get_slack_channels,
    },
    'get_slack_messages': {
        'schema': _fn_schema('get_slack_messages', 'Get recent messages from a Slack channel.',
                             {'type': 'object', 'properties': {
                                 'channel_id': {'type': 'string', 'description': 'Slack channel ID'},
                             }, 'required': ['channel_id']}),
        'required_service': 'slack',
        'execute': _exec_get_slack_messages,
    },

    # -- Spotify --
    'get_spotify_profile': {
        'schema': _fn_schema('get_spotify_profile', 'Get the user\'s Spotify profile info.'),
        'required_service': 'spotify',
        'execute': _exec_get_spotify_profile,
    },
    'get_spotify_playlists': {
        'schema': _fn_schema('get_spotify_playlists', 'List the user\'s Spotify playlists.'),
        'required_service': 'spotify',
        'execute': _exec_get_spotify_playlists,
    },
    'get_spotify_now_playing': {
        'schema': _fn_schema('get_spotify_now_playing', 'Get the track currently playing on Spotify.'),
        'required_service': 'spotify',
        'execute': _exec_get_spotify_now_playing,
    },

    # -- Telegram --
    'get_telegram_bot_info': {
        'schema': _fn_schema('get_telegram_bot_info', 'Get info about the connected Telegram bot.'),
        'required_service': 'telegram',
        'execute': _exec_get_telegram_bot_info,
    },
    'get_telegram_updates': {
        'schema': _fn_schema('get_telegram_updates', 'Get recent messages/updates received by the Telegram bot.'),
        'required_service': 'telegram',
        'execute': _exec_get_telegram_updates,
    },

    # -- Todoist --
    'get_todoist_projects': {
        'schema': _fn_schema('get_todoist_projects', 'List the user\'s Todoist projects.'),
        'required_service': 'todoist',
        'execute': _exec_get_todoist_projects,
    },
    'get_todoist_tasks': {
        'schema': _fn_schema('get_todoist_tasks', 'List tasks from Todoist, optionally filtered by project.',
                             {'type': 'object', 'properties': {
                                 'project_id': {'type': 'string', 'description': 'Optional Todoist project ID to filter tasks'},
                             }, 'required': []}),
        'required_service': 'todoist',
        'execute': _exec_get_todoist_tasks,
    },

    # -- Discord --
    'get_discord_guilds': {
        'schema': _fn_schema('get_discord_guilds', 'List Discord servers (guilds) the user belongs to.'),
        'required_service': 'discord',
        'execute': _exec_get_discord_guilds,
    },
    'get_discord_channels': {
        'schema': _fn_schema('get_discord_channels', 'List channels in a Discord server.',
                             {'type': 'object', 'properties': {
                                 'guild_id': {'type': 'string', 'description': 'Discord guild (server) ID'},
                             }, 'required': ['guild_id']}),
        'required_service': 'discord',
        'execute': _exec_get_discord_channels,
    },

    # -- Dropbox --
    'get_dropbox_files': {
        'schema': _fn_schema('get_dropbox_files', 'List files in a Dropbox folder.',
                             {'type': 'object', 'properties': {
                                 'path': {'type': 'string', 'description': 'Folder path (empty string for root)', 'default': ''},
                             }, 'required': []}),
        'required_service': 'dropbox',
        'execute': _exec_get_dropbox_files,
    },
    'get_dropbox_metadata': {
        'schema': _fn_schema('get_dropbox_metadata', 'Get metadata for a specific Dropbox file or folder.',
                             {'type': 'object', 'properties': {
                                 'path': {'type': 'string', 'description': 'Full path to the file or folder'},
                             }, 'required': ['path']}),
        'required_service': 'dropbox',
        'execute': _exec_get_dropbox_metadata,
    },

    # -- Gmail --
    'get_gmail_recent': {
        'schema': _fn_schema('get_gmail_recent', 'Get the user\'s most recent emails with subject, sender, and snippet.'),
        'required_service': 'gmail',
        'execute': _exec_get_gmail_recent,
    },
    'get_gmail_email': {
        'schema': _fn_schema('get_gmail_email', 'Get details of a specific email by ID.',
                             {'type': 'object', 'properties': {
                                 'email_id': {'type': 'string', 'description': 'Gmail message ID'},
                             }, 'required': ['email_id']}),
        'required_service': 'gmail',
        'execute': _exec_get_gmail_email,
    },

    # -- Google Calendar --
    'get_calendar_events': {
        'schema': _fn_schema('get_calendar_events', 'Get upcoming events from the user\'s Google Calendar.'),
        'required_service': 'calendar',
        'execute': _exec_get_calendar_events,
    },

    # -- Google Drive --
    'get_drive_files': {
        'schema': _fn_schema('get_drive_files', 'List recent files in the user\'s Google Drive.'),
        'required_service': 'drive',
        'execute': _exec_get_drive_files,
    },
    'search_drive': {
        'schema': _fn_schema('search_drive', 'Search for files in Google Drive by name.',
                             {'type': 'object', 'properties': {
                                 'query': {'type': 'string', 'description': 'Search query (file name)'},
                             }, 'required': ['query']}),
        'required_service': 'drive',
        'execute': _exec_search_drive,
    },

    # -- Notion --
    'search_notion': {
        'schema': _fn_schema('search_notion', 'Search pages and databases in the user\'s Notion workspace.',
                             {'type': 'object', 'properties': {
                                 'query': {'type': 'string', 'description': 'Search query (leave empty to list all)', 'default': ''},
                             }, 'required': []}),
        'required_service': 'notion',
        'execute': _exec_search_notion,
    },

    # -- Binance --
    'get_binance_portfolio': {
        'schema': _fn_schema('get_binance_portfolio', 'Get the user\'s Binance portfolio/balance overview.'),
        'required_service': 'binance',
        'execute': _exec_get_binance_portfolio,
    },
    'get_binance_prices': {
        'schema': _fn_schema('get_binance_prices', 'Get current prices for crypto trading pairs.',
                             {'type': 'object', 'properties': {
                                 'symbols': {'type': 'array', 'items': {'type': 'string'},
                                             'description': 'Trading pairs, e.g. ["BTC/USDT", "ETH/USDT"]', 'default': ['BTC/USDT', 'ETH/USDT']},
                             }, 'required': []}),
        'required_service': 'binance',
        'execute': _exec_get_binance_prices,
    },

    # ===================================================================
    # WRITE TOOLS
    # ===================================================================

    # -- Gmail writes --
    'send_email': {
        'schema': _fn_schema('send_email', 'Send an email from the user\'s Gmail account.',
                             {'type': 'object', 'properties': {
                                 'to': {'type': 'string', 'description': 'Recipient email address'},
                                 'subject': {'type': 'string', 'description': 'Email subject line'},
                                 'body': {'type': 'string', 'description': 'Email body text'},
                             }, 'required': ['to', 'subject', 'body']}),
        'required_service': 'gmail',
        'execute': _exec_send_email,
    },
    'reply_to_email': {
        'schema': _fn_schema('reply_to_email', 'Reply to an existing email in the user\'s Gmail. Automatically sets reply headers and thread.',
                             {'type': 'object', 'properties': {
                                 'email_id': {'type': 'string', 'description': 'Gmail message ID of the email to reply to'},
                                 'body': {'type': 'string', 'description': 'Reply body text'},
                             }, 'required': ['email_id', 'body']}),
        'required_service': 'gmail',
        'execute': _exec_reply_to_email,
    },

    # -- Calendar writes --
    'create_calendar_event': {
        'schema': _fn_schema('create_calendar_event', 'Create a new event on the user\'s Google Calendar.',
                             {'type': 'object', 'properties': {
                                 'summary': {'type': 'string', 'description': 'Event title'},
                                 'start': {'type': 'string', 'description': 'Start time in ISO 8601 format (e.g. 2025-06-15T10:00:00-05:00)'},
                                 'end': {'type': 'string', 'description': 'End time in ISO 8601 format (e.g. 2025-06-15T11:00:00-05:00)'},
                                 'description': {'type': 'string', 'description': 'Event description (optional)'},
                                 'location': {'type': 'string', 'description': 'Event location (optional)'},
                             }, 'required': ['summary', 'start', 'end']}),
        'required_service': 'calendar',
        'execute': _exec_create_calendar_event,
    },
    'delete_calendar_event': {
        'schema': _fn_schema('delete_calendar_event', 'Delete an event from the user\'s Google Calendar.',
                             {'type': 'object', 'properties': {
                                 'event_id': {'type': 'string', 'description': 'Google Calendar event ID'},
                             }, 'required': ['event_id']}),
        'required_service': 'calendar',
        'execute': _exec_delete_calendar_event,
    },

    # -- Drive writes --
    'create_drive_folder': {
        'schema': _fn_schema('create_drive_folder', 'Create a new folder in the user\'s Google Drive.',
                             {'type': 'object', 'properties': {
                                 'name': {'type': 'string', 'description': 'Folder name'},
                                 'parent_id': {'type': 'string', 'description': 'Parent folder ID (optional, defaults to root)'},
                             }, 'required': ['name']}),
        'required_service': 'drive',
        'execute': _exec_create_drive_folder,
    },

    # -- Notion writes --
    'create_notion_page': {
        'schema': _fn_schema('create_notion_page', 'Create a new page in the user\'s Notion workspace.',
                             {'type': 'object', 'properties': {
                                 'parent_id': {'type': 'string', 'description': 'Parent page ID to create the new page under'},
                                 'title': {'type': 'string', 'description': 'Page title'},
                                 'content': {'type': 'string', 'description': 'Page body text (optional)'},
                             }, 'required': ['parent_id', 'title']}),
        'required_service': 'notion',
        'execute': _exec_create_notion_page,
    },

    # -- GitHub writes --
    'create_github_issue': {
        'schema': _fn_schema('create_github_issue', 'Create a new issue on a GitHub repository.',
                             {'type': 'object', 'properties': {
                                 'owner': {'type': 'string', 'description': 'Repository owner (user or org)'},
                                 'repo': {'type': 'string', 'description': 'Repository name'},
                                 'title': {'type': 'string', 'description': 'Issue title'},
                                 'body': {'type': 'string', 'description': 'Issue description (optional)'},
                                 'labels': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Labels to apply (optional)'},
                             }, 'required': ['owner', 'repo', 'title']}),
        'required_service': 'github',
        'execute': _exec_create_github_issue,
    },
    'create_github_comment': {
        'schema': _fn_schema('create_github_comment', 'Add a comment to a GitHub issue or pull request.',
                             {'type': 'object', 'properties': {
                                 'owner': {'type': 'string', 'description': 'Repository owner (user or org)'},
                                 'repo': {'type': 'string', 'description': 'Repository name'},
                                 'issue_number': {'type': 'integer', 'description': 'Issue or PR number'},
                                 'body': {'type': 'string', 'description': 'Comment text'},
                             }, 'required': ['owner', 'repo', 'issue_number', 'body']}),
        'required_service': 'github',
        'execute': _exec_create_github_comment,
    },

    # -- Slack writes --
    'send_slack_message': {
        'schema': _fn_schema('send_slack_message', 'Send a message to a Slack channel.',
                             {'type': 'object', 'properties': {
                                 'channel_id': {'type': 'string', 'description': 'The Slack channel ID'},
                                 'text': {'type': 'string', 'description': 'Message text to send'},
                             }, 'required': ['channel_id', 'text']}),
        'required_service': 'slack',
        'execute': _exec_send_slack_message,
    },

    # -- Discord writes --
    'send_discord_message': {
        'schema': _fn_schema('send_discord_message', 'Send a message to a Discord channel.',
                             {'type': 'object', 'properties': {
                                 'channel_id': {'type': 'string', 'description': 'Discord channel ID'},
                                 'content': {'type': 'string', 'description': 'Message content to send'},
                             }, 'required': ['channel_id', 'content']}),
        'required_service': 'discord',
        'execute': _exec_send_discord_message,
    },

    # -- Telegram writes --
    'send_telegram_message': {
        'schema': _fn_schema('send_telegram_message', 'Send a message via the connected Telegram bot.',
                             {'type': 'object', 'properties': {
                                 'chat_id': {'type': 'string', 'description': 'Telegram chat ID to send the message to'},
                                 'text': {'type': 'string', 'description': 'Message text to send'},
                             }, 'required': ['chat_id', 'text']}),
        'required_service': 'telegram',
        'execute': _exec_send_telegram_message,
    },

    # -- Todoist writes --
    'create_todoist_task': {
        'schema': _fn_schema('create_todoist_task', 'Create a new task in Todoist.',
                             {'type': 'object', 'properties': {
                                 'content': {'type': 'string', 'description': 'Task title/content'},
                                 'project_id': {'type': 'string', 'description': 'Project ID to add the task to (optional)'},
                                 'due_string': {'type': 'string', 'description': 'Due date in natural language, e.g. "tomorrow", "next Monday" (optional)'},
                                 'priority': {'type': 'integer', 'description': 'Priority 1 (normal) to 4 (urgent) (optional)'},
                             }, 'required': ['content']}),
        'required_service': 'todoist',
        'execute': _exec_create_todoist_task,
    },
    'complete_todoist_task': {
        'schema': _fn_schema('complete_todoist_task', 'Mark a Todoist task as completed.',
                             {'type': 'object', 'properties': {
                                 'task_id': {'type': 'string', 'description': 'Todoist task ID to complete'},
                             }, 'required': ['task_id']}),
        'required_service': 'todoist',
        'execute': _exec_complete_todoist_task,
    },

    # -- Spotify writes --
    'spotify_play': {
        'schema': _fn_schema('spotify_play', 'Start or resume playback on the user\'s Spotify. Can play a specific track, album, or playlist by URI, or resume current playback.',
                             {'type': 'object', 'properties': {
                                 'uri': {'type': 'string', 'description': 'Spotify URI (e.g. spotify:track:xxx, spotify:album:xxx, spotify:playlist:xxx). Leave empty to resume current playback.'},
                             }, 'required': []}),
        'required_service': 'spotify',
        'execute': _exec_spotify_play,
    },
}

# Map of service_type -> display name (for system prompt)
SERVICE_DISPLAY_NAMES = {
    'github': 'GitHub', 'slack': 'Slack', 'spotify': 'Spotify',
    'telegram': 'Telegram', 'todoist': 'Todoist', 'discord': 'Discord',
    'dropbox': 'Dropbox', 'gmail': 'Gmail', 'calendar': 'Google Calendar',
    'drive': 'Google Drive', 'notion': 'Notion', 'binance': 'Binance',
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_tools_for_user(user_id):
    """Return list of OpenAI-format tool schemas for connected services + meta tools."""
    connected = {sp.service_type for sp in
                 Superpower.query.filter_by(user_id=user_id, is_enabled=True).all()}
    tools = []
    for name, entry in TOOL_REGISTRY.items():
        req = entry['required_service']
        if req is None or req in connected:
            tools.append(entry['schema'])
    return tools


def execute_tool(tool_name, user_id, arguments):
    """Execute a tool by name. Returns a result dict (always JSON-serializable)."""
    entry = TOOL_REGISTRY.get(tool_name)
    if not entry:
        return {'error': f'Unknown tool: {tool_name}'}
    try:
        return entry['execute'](user_id, arguments or {})
    except Exception as e:
        return {'error': f'Tool execution failed: {str(e)[:300]}'}


def get_tools_system_prompt(user_id):
    """Build a system prompt fragment describing available tools."""
    connected = {sp.service_type for sp in
                 Superpower.query.filter_by(user_id=user_id, is_enabled=True).all()}

    connected_names = [SERVICE_DISPLAY_NAMES.get(s, s) for s in sorted(connected)]
    all_services = set(SERVICE_DISPLAY_NAMES.keys())
    disconnected = all_services - connected
    disconnected_names = [SERVICE_DISPLAY_NAMES.get(s, s) for s in sorted(disconnected)]

    lines = [
        'You have access to tools that can interact with the user\'s connected services.',
        'Use these tools when the user asks about their services, data, or wants to perform actions.',
    ]
    if connected_names:
        lines.append(f'Connected services: {", ".join(connected_names)}.')
    else:
        lines.append('No services are currently connected.')
    if disconnected_names:
        lines.append(f'Not yet connected: {", ".join(disconnected_names)}. You can offer to connect them using the connect_service tool.')
    lines.append('Always use a tool when it can answer the user\'s question rather than guessing.')

    return '\n'.join(lines)
