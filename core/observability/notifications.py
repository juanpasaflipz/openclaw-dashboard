"""
Notification dispatch — Slack webhook, extensible to email/custom webhooks.
"""
import os
import requests as http_requests


def notify_slack(message: str) -> bool:
    """Send a message to the configured Slack webhook. Returns True on success."""
    slack_url = os.environ.get('SLACK_WEBHOOK_URL')
    if not slack_url:
        return False

    try:
        resp = http_requests.post(slack_url, json={'text': message}, timeout=5)
        return resp.status_code == 200
    except Exception as e:
        print(f"[obs] Slack notification failed: {e}")
        return False


def dispatch_alert_notification(message: str, channels: list[str] | None = None) -> dict:
    """
    Dispatch alert to all configured channels.
    Returns dict of {channel: success_bool}.

    Channels: 'slack' (more to come: 'email', 'webhook').
    """
    if channels is None:
        channels = ['slack']

    results = {}
    for channel in channels:
        if channel == 'slack':
            results['slack'] = notify_slack(message)
        # Future: elif channel == 'email': results['email'] = notify_email(...)
        else:
            results[channel] = False

    return results
