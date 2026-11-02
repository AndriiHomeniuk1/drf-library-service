from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings

from notifications.telegram import send_telegram_message


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID="12345")
class SendTelegramMessageTests(SimpleTestCase):
    def setUp(self):
        patcher = patch("notifications.telegram.requests.post")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)

    def test_message_is_sent_to_configured_chat(self):
        result = send_telegram_message("Hello")

        self.assertTrue(result)
        self.post.assert_called_once()
        args, kwargs = self.post.call_args
        self.assertIn("bottest-token/sendMessage", args[0])
        self.assertEqual(
            kwargs["json"],
            {"chat_id": "12345", "text": "Hello"}
        )

    def test_network_error_returns_false(self):
        self.post.side_effect = requests.ConnectionError("no network")

        with self.assertLogs("notifications.telegram", level="ERROR"):
            result = send_telegram_message("Hello")

        self.assertFalse(result)

    def test_http_error_returns_false(self):
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError("401")
        self.post.return_value = response

        with self.assertLogs("notifications.telegram", level="ERROR"):
            result = send_telegram_message("Hello")

        self.assertFalse(result)

    @override_settings(TELEGRAM_BOT_TOKEN="")
    def test_missing_token_skips_sending(self):
        with self.assertLogs("notifications.telegram", level="WARNING"):
            result = send_telegram_message("Hello")

        self.assertFalse(result)
        self.post.assert_not_called()

    @override_settings(TELEGRAM_CHAT_ID="")
    def test_missing_chat_id_skips_sending(self):
        with self.assertLogs("notifications.telegram", level="WARNING"):
            result = send_telegram_message("Hello")

        self.assertFalse(result)
        self.post.assert_not_called()
