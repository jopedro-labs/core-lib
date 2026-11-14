"""
Discord notification client supporting both Bot API (with dynamic channel targeting)
and Webhook URLs.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)


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
        content: str,
        channel_id: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
    ) -> None:
        """Sends a text message or embed to a Discord channel.

        Args:
            content: The message text content.
            channel_id: Target Discord channel ID (required when using bot_token).
            embeds: Optional list of rich embed objects.

        Raises:
            ValueError: If bot_token is set but channel_id is missing.
            DiscordNotificationError: If the API request fails or returns an error.
        """
        if not content and not embeds:
            raise ValueError("[discord] 'content' or at least one embed is required.")

        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self.bot_token:
            if not channel_id:
                raise ValueError(
                    "[discord] 'channel_id' is required when using a bot token."
                )
            url: str = f"{self.API_BASE_URL}/channels/{channel_id}/messages"
            headers["Authorization"] = f"Bot {self.bot_token}"
        else:
            url = self.webhook_url  # type: ignore[assignment]

        try:
            response: requests.Response = self.session.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            if response.status_code == 429:
                retry_after = response.json().get("retry_after", "unknown")
                raise DiscordNotificationError(
                    f"[discord] Rate limited by Discord API. retry_after={retry_after}s"
                )
            if response.status_code not in (200, 201, 204):
                raise DiscordNotificationError(
                    f"[discord] HTTP {response.status_code} from Discord API: {response.text}"
                )
        except requests.RequestException as e:
            logger.exception("[discord] Failed to send notification.")
            raise DiscordNotificationError(
                f"[discord] Network error while sending Discord notification: {e}"
            ) from e

    def close(self) -> None:
        """Releases the underlying HTTP session."""
        self.session.close()

    def __enter__(self) -> DiscordNotifier:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
