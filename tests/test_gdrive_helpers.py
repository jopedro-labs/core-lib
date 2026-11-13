import pytest

from core_lib.gdrive.gdrive_helpers import sanitize_gdrive_folder_id, verify_gdrive_folder_access


def test_sanitize_returns_stripped_id():
    assert sanitize_gdrive_folder_id("  abc123  ") == "abc123"


def test_sanitize_returns_none_for_none():
    assert sanitize_gdrive_folder_id(None) is None


def test_sanitize_raises_for_empty_string():
    with pytest.raises(ValueError):
        sanitize_gdrive_folder_id("")


def test_sanitize_raises_for_whitespace_only():
    with pytest.raises(ValueError):
        sanitize_gdrive_folder_id("   ")


def test_verify_gdrive_folder_access_returns_false_on_exception(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no connection")

    monkeypatch.setattr(
        "core_lib.gdrive.gdrive_service.GDriveService",
        boom,
    )
    assert verify_gdrive_folder_access("some-folder-id") is False
