import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_message(text: str) -> bool:
    """Send a message to the notifications chat. Returns True on success."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.warning("Telegram is not configured, message skipped.")
        return False

    try:
        response = requests.post(
            TELEGRAM_API_URL.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        response.raise_for_status()

    except requests.RequestException:
        logger.exception("Failed to send Telegram message.")
        return False

    return True
