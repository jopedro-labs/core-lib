from unittest.mock import MagicMock, patch
import pytest

from core_lib.gdrive.gdrive_helpers import sanitize_gdrive_folder_id, verify_gdrive_folder_access


def test_sanitize_returns_stripped_id() -> None:
    assert sanitize_gdrive_folder_id("  abc123  ") == "abc123"


def test_sanitize_returns_none_for_none() -> None:
    assert sanitize_gdrive_folder_id(None) is None


def test_sanitize_raises_for_empty_string() -> None:
    with pytest.raises(ValueError):
        sanitize_gdrive_folder_id("")


def test_sanitize_raises_for_whitespace_only() -> None:
    with pytest.raises(ValueError):
        sanitize_gdrive_folder_id("   ")


def test_verify_gdrive_folder_access_returns_false_on_exception(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("no connection")

    monkeypatch.setattr(
        "core_lib.gdrive.gdrive_service.GDriveService",
        boom,
    )
    assert verify_gdrive_folder_access("some-folder-id") is False

def test_verify_gdrive_folder_access_exception_path() -> None:
    from core_lib.gdrive.gdrive_helpers import verify_gdrive_folder_access
    mock_service = MagicMock()
    mock_service.verify_folder_access.side_effect = Exception("Folder check network error")
    with patch("core_lib.gdrive.gdrive_service.GDriveService", return_value=mock_service):
        assert verify_gdrive_folder_access(folder_id="some-folder") is False
