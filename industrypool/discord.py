"""Discord webhook notification helper for Industry Pool.

Sends job state change notifications to a configured Discord webhook URL
in addition to (or instead of) AllianceAuth's built-in notifications.
"""

import json

import requests
from django.conf import settings

from allianceauth.services.hooks import get_extension_logger

logger = get_extension_logger(__name__)

# Webhook colours (Discord embed colour as decimal int)
COLOURS = {
    "info": 0x3498DB,      # blue
    "success": 0x2ECC71,   # green
    "warning": 0xF39C12,   # orange
    "error": 0xE74C3C,     # red
}


def send_discord_notification(title: str, message: str, level: str = "info") -> None:
    """Send a notification to the configured Discord webhook, if any.

    The webhook URL is read from ``settings.INDUSTRYPOOL_DISCORD_WEBHOOK_URL``.
    If not set, this is a no-op.
    """
    webhook_url = getattr(settings, "INDUSTRYPOOL_DISCORD_WEBHOOK_URL", None)
    if not webhook_url:
        return

    colour = COLOURS.get(level, COLOURS["info"])
    payload = {
        "embeds": [
            {
                "title": title,
                "description": message,
                "color": colour,
            }
        ]
    }

    try:
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
    except Exception:
        logger.exception("Failed to send Discord webhook notification")
