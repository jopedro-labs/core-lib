"""
Discord notification client supporting both Bot API (with dynamic channel targeting)
and Webhook URLs.
"""

from __future__ import annotations

import logging
from typing import TypedDict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)


class DiscordEmbed(TypedDict, total=False):
    """Structural schema for Discord embed objects."""

    title: str
    description: str
    url: str
    color: int
    fields: list[dict[str, str]]


class DiscordNotificationError(Exception):
    """Raised when failing to send a notification to Discord."""

    pass


class DiscordNotifier:
    """Client for dispatching notifications to Discord channels."""

    API_BASE_URL: str = "https://discord.com/api/v10"

    def __init__(
        self,
        bot_token: str | None = None,
        webhook_url: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        """Initializes the Discord notifier.

        Args:
            bot_token: Discord Bot Token for dynamic channel targeting.
            webhook_url: Fallback webhook URL for fixed-channel broadcasting.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of HTTP retry attempts.
        """
        if not bot_token and not webhook_url:
            raise ValueError(
                "[discord] Either 'bot_token' or 'webhook_url' must be provided."
            )

        self.bot_token: str | None = bot_token
        self.webhook_url: str | None = webhook_url
        self.timeout: float = timeout

        self.session: requests.Session = requests.Session()
        retries: Retry = Retry(
            total=max_retries,
            backoff_factor=1.0,
            # 429 intentionally excluded: Discord returns retry_after in the body,
            # so callers should handle rate-limit responses explicitly rather than
            # relying on blind exponential back-off that ignores that value.
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter: HTTPAdapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def send_message(
        self,
        content: str | None = None,
        channel_id: str | None = None,
        embeds: list[DiscordEmbed] | None = None,
    ) -> None:
        """Send a text message or rich embeds to Discord via Bot API or Webhook.

        Args:
            content: The text content of the message.
            channel_id: Optional target channel ID (required for Bot token mode).
            embeds: Optional list of rich embed dictionaries.

        Raises:
            ValueError: If neither content nor embeds are provided, or if channel_id
                        is missing when using a bot token.
            DiscordNotificationError: If the API request fails or is rate-limited.
        """
        if not content and not embeds:
            raise ValueError("Either 'content' or at least one embed is required.")

        if self.bot_token and not channel_id:
            raise ValueError("'channel_id' is required when using a bot token.")

        payload: dict[str, object] = {}
        if content:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds

        if self.bot_token:
            url = f"{self.API_BASE_URL}/channels/{channel_id}/messages"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bot {self.bot_token}",
            }
        else:
            url = str(self.webhook_url)
            headers = {"Content-Type": "application/json"}

        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)

            if response.status_code == 429:
                try:
                    data = response.json() if response.content else {}
                except Exception:
                    data = {}
                retry_after = data.get("retry_after", "unknown")
                raise DiscordNotificationError(
                    f"Rate limited by Discord API. retry_after={retry_after}s"
                )

            if response.status_code not in (200, 201, 204):
                raise DiscordNotificationError(
                    f"HTTP {response.status_code} from Discord API: {response.text}"
                )

        except requests.exceptions.RequestException as e:
            raise DiscordNotificationError(
                f"Network error while sending Discord notification: {e}"
            ) from e

    def close(self) -> None:
        """Releases the underlying HTTP session."""
        self.session.close()

    def __enter__(self) -> DiscordNotifier:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
