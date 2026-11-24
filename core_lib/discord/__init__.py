"""Discord notification submodule — bot API and webhook support."""

from __future__ import annotations


def __getattr__(name: str) -> object:
    if name == "DiscordNotifier":
        from core_lib.discord.discord_service import DiscordNotifier
        return DiscordNotifier
    if name == "DiscordNotificationError":
        from core_lib.discord.discord_service import DiscordNotificationError
        return DiscordNotificationError
    if name == "DiscordEmbed":
        from core_lib.discord.discord_service import DiscordEmbed
        return DiscordEmbed
    raise AttributeError(f"module 'core_lib.discord' has no attribute {name!r}")
