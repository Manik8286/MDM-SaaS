"""
Notification service — sends webhook notifications for important events.

Supports any incoming webhook (Slack, Microsoft Teams, Discord, etc.).
Set NOTIFICATION_WEBHOOK_URL in .env to enable.

Event types:
  - software_request_created  — new software request from portal
  - admin_access_requested    — new admin access request from portal
  - admin_access_auto_revoked — auto-revoke fired by background worker
"""
import logging
import httpx
from app.core.config import get_settings

log = logging.getLogger(__name__)


async def notify(event: str, data: dict) -> None:
    settings = get_settings()
    if not settings.notification_webhook_url:
        return

    try:
        message = _format_message(event, data)
        payload = _build_payload(settings.notification_webhook_url, message)
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(settings.notification_webhook_url, json=payload)
            if r.status_code >= 400:
                log.warning("Notification webhook returned %d: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("Notification failed for event %s: %s", event, e)


def _format_message(event: str, data: dict) -> str:
    if event == "software_request_created":
        return (
            f"📦 *New software request*\n"
            f"Software: *{data.get('software_name')}*\n"
            f"Requested by: {data.get('requester_name')} on {data.get('hostname', 'unknown device')}\n"
            f"Reason: {data.get('reason') or '—'}"
        )
    elif event == "admin_access_requested":
        return (
            f"🔑 *Admin access request*\n"
            f"User: *{data.get('username')}* on {data.get('hostname', 'unknown device')}\n"
            f"Duration: {data.get('duration_hours')}h\n"
            f"Reason: {data.get('reason') or '—'}"
        )
    elif event == "admin_access_auto_revoked":
        return (
            f"⏰ *Admin access auto-revoked*\n"
            f"User: *{data.get('username')}* on {data.get('hostname', 'unknown device')}\n"
            f"Grant expired after {data.get('duration_hours')}h"
        )
    else:
        return f"MDM event: {event}\n{data}"


def _build_payload(url: str, message: str) -> dict:
    """Build the right payload format based on the webhook URL."""
    if "hooks.slack.com" in url or "slack.com/services" in url:
        return {"text": message}
    elif "outlook.office.com" in url or "webhook.office.com" in url:
        # Microsoft Teams
        return {"text": message}
    elif "discord.com/api/webhooks" in url:
        return {"content": message}
    else:
        # Generic — try Slack format as default
        return {"text": message}
