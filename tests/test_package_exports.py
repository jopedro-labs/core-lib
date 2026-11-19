import pytest
import core_lib.discord
import core_lib.gdrive


def test_discord_submodule_getattr_resolution():
    assert core_lib.discord.DiscordNotifier is not None
    assert core_lib.discord.DiscordNotificationError is not None

    with pytest.raises(AttributeError, match="module 'core_lib.discord' has no attribute 'NonExistent'"):
        _ = core_lib.discord.NonExistent


def test_gdrive_submodule_getattr_resolution():
    assert core_lib.gdrive.GDriveService is not None
    assert core_lib.gdrive.get_google_service_credentials is not None
    assert core_lib.gdrive.sanitize_gdrive_folder_id is not None

    with pytest.raises(AttributeError, match="module 'core_lib.gdrive' has no attribute 'NonExistent'"):
        _ = core_lib.gdrive.NonExistent
