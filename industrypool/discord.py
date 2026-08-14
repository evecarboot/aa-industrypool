"""Discord webhook notification helper for Industry Pool.

Sends job state change notifications to a configured Discord webhook URL
in addition to (or instead of) AllianceAuth's built-in notifications.

Also supports sending direct messages to individual users via the
``aadiscordbot`` plugin, if it is installed.
"""

import json

import requests
from django.apps import apps
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


def discord_bot_active() -> bool:
    """Return True if aadiscordbot is installed and available."""
    return apps.is_installed("aadiscordbot")


def send_discord_notification(title: str, message: str, level: str = "info", admin: bool = False) -> None:
    """Send a notification to a configured Discord webhook, if any.

    :param admin: If True, send to the admin webhook (``INDUSTRYPOOL_DISCORD_ADMIN_WEBHOOK_URL``).
                  If False, send to the public webhook (``INDUSTRYPOOL_DISCORD_WEBHOOK_URL``).
                  If the requested webhook is not configured, this is a no-op.
    """
    if admin:
        webhook_url = getattr(settings, "INDUSTRYPOOL_DISCORD_ADMIN_WEBHOOK_URL", None)
    else:
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


def send_discord_dm(user, title: str, message: str, level: str = "info") -> None:
    """Send a direct message to a user via aadiscordbot, if installed.

    :param user: Django User instance to DM.
    :param title: Embed title.
    :param message: Message body text.
    :param level: One of info/success/warning/error - controls embed colour.
    """
    if not discord_bot_active():
        return

    try:
        from aadiscordbot.tasks import send_message
        from discord import Embed, Color

        colour_map = {
            "info": Color.blue(),
            "success": Color.green(),
            "warning": Color.orange(),
            "error": Color.red(),
        }
        embed = Embed(
            title=title,
            description=message,
            color=colour_map.get(level, Color.blue()),
        )
        send_message(user=user, embed=embed)
    except Exception:
        logger.exception("Failed to send Discord DM to user %s", user)
