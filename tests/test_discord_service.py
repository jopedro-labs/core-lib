from unittest.mock import MagicMock, patch
import pytest
import requests

from core_lib.discord.discord_service import (
    DiscordNotificationError,
    DiscordNotifier,
)


class TestDiscordNotifierInit:
    def test_init_raises_when_neither_token_nor_webhook_provided(self):
        with pytest.raises(ValueError, match="Either 'bot_token' or 'webhook_url' must be provided"):
            DiscordNotifier()

    def test_init_with_bot_token(self):
        notifier = DiscordNotifier(bot_token="test_bot_token")
        assert notifier.bot_token == "test_bot_token"
        assert notifier.webhook_url is None
        assert notifier.timeout == 10.0

    def test_init_with_webhook_url(self):
        url = "https://discord.com/api/webhooks/123/xyz"
        notifier = DiscordNotifier(webhook_url=url, timeout=5.0)
        assert notifier.webhook_url == url
        assert notifier.bot_token is None
        assert notifier.timeout == 5.0


class TestDiscordNotifierContextManager:
    def test_context_manager_lifecycle(self):
        with patch.object(requests.Session, "close") as mock_close:
            with DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/xyz") as notifier:
                assert isinstance(notifier, DiscordNotifier)
            mock_close.assert_called_once()


class TestDiscordNotifierSendMessage:
    def test_send_message_raises_on_empty_content_and_embeds(self):
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/xyz")
        with pytest.raises(ValueError, match="'content' or at least one embed is required"):
            notifier.send_message(content="", embeds=None)

    def test_send_message_bot_token_requires_channel_id(self):
        notifier = DiscordNotifier(bot_token="token_123")
        with pytest.raises(ValueError, match="'channel_id' is required when using a bot token"):
            notifier.send_message(content="Hello", channel_id=None)

    def test_send_message_bot_token_payload_and_headers(self):
        notifier = DiscordNotifier(bot_token="token_123")
        mock_response = MagicMock(status_code=200)

        with patch.object(notifier.session, "post", return_value=mock_response) as mock_post:
            notifier.send_message(
                content="Alert message",
                channel_id="chan_999",
                embeds=[{"title": "Job Failed"}],
            )

            mock_post.assert_called_once_with(
                "https://discord.com/api/v10/channels/chan_999/messages",
                json={"content": "Alert message", "embeds": [{"title": "Job Failed"}]},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bot token_123",
                },
                timeout=10.0,
            )

    def test_send_message_webhook_success_codes(self):
        url = "https://discord.com/api/webhooks/123/xyz"
        notifier = DiscordNotifier(webhook_url=url)

        for status in (200, 201, 204):
            mock_response = MagicMock(status_code=status)
            with patch.object(notifier.session, "post", return_value=mock_response) as mock_post:
                notifier.send_message(content="Webhook test")
                mock_post.assert_called_once_with(
                    url,
                    json={"content": "Webhook test"},
                    headers={"Content-Type": "application/json"},
                    timeout=10.0,
                )

    def test_send_message_rate_limit_extracts_retry_after(self):
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/xyz")
        mock_response = MagicMock(status_code=429)
        mock_response.json.return_value = {"retry_after": 4.5}

        with patch.object(notifier.session, "post", return_value=mock_response):
            with pytest.raises(DiscordNotificationError, match=r"Rate limited by Discord API\. retry_after=4\.5s"):
                notifier.send_message(content="Spamming")

    def test_send_message_rate_limit_missing_retry_after(self):
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/xyz")
        mock_response = MagicMock(status_code=429)
        mock_response.json.return_value = {}

        with patch.object(notifier.session, "post", return_value=mock_response):
            with pytest.raises(DiscordNotificationError, match=r"Rate limited by Discord API\. retry_after=unknown"):
                notifier.send_message(content="Spamming")

    def test_send_message_http_error_status(self):
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/xyz")
        mock_response = MagicMock(status_code=401, text="Unauthorized token")

        with patch.object(notifier.session, "post", return_value=mock_response):
            with pytest.raises(DiscordNotificationError, match=r"HTTP 401 from Discord API: Unauthorized token"):
                notifier.send_message(content="Invalid")

    def test_send_message_network_request_exception(self):
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/123/xyz")
        with patch.object(notifier.session, "post", side_effect=requests.exceptions.ConnectTimeout("Connection timed out")):
            with pytest.raises(DiscordNotificationError, match="Network error while sending Discord notification"):
                notifier.send_message(content="Timeout")