"""Tests covering edge cases across core_lib modules and HTTP fixtures."""

from __future__ import annotations

import io
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials

from core_lib.discord.discord_service import DiscordNotificationError, DiscordNotifier
from core_lib.file_utils.file_utils import load_file_content
from core_lib.gdrive.gdrive_auth import get_google_service_credentials
from core_lib.gdrive.gdrive_helpers import sanitize_gdrive_folder_id
from core_lib.gdrive.gdrive_service import GDriveService
from core_lib.logger.logger import Logger, logger

# ---------------------------------------------------------
# Logger Edge Cases
# ---------------------------------------------------------

def test_logger_print_with_custom_color_and_non_ascii(capsys) -> None:
    test_logger = Logger()
    test_logger._colors_enabled = True

    # Multi-line non-ASCII string
    msg = "Linha 1: Olá Mundo 🚀\nLinha 2: Teste €ção"
    test_logger.print(msg, color="\033[33m")

    captured = capsys.readouterr()
    assert "\033[33m" in captured.out
    assert "Olá Mundo 🚀" in captured.out
    assert "Teste €ção" in captured.out


def test_logger_print_without_colors(capsys) -> None:
    test_logger = Logger()
    test_logger._colors_enabled = False
    test_logger.print("Plain text", color="\033[31m")
    captured = capsys.readouterr()
    assert "\033[31m" not in captured.out
    assert "Plain text" in captured.out


def test_logger_error_with_multiline_exception(capsys) -> None:
    try:
        raise ValueError("Line A\nLine B")
    except ValueError as e:
        logger.error("Something went wrong", exception=e)

    captured = capsys.readouterr()
    assert "Something went wrong | Error: Line A" in captured.err


# ---------------------------------------------------------
# File Utils Edge Cases
# ---------------------------------------------------------

def test_load_file_content_non_utf8_binary(tmp_path) -> None:
    bin_file = tmp_path / "binary.dat"
    # Write invalid UTF-8 bytes
    bin_file.write_bytes(b"\x80\x81\xFF\xFE")

    content = load_file_content(bin_file)
    assert content == ""


@pytest.mark.skipif(
    not hasattr(os, "symlink") or sys.platform == "win32",
    reason="Symlinks not supported or require elevated privileges in this environment",
)
def test_load_file_content_broken_symlink(tmp_path: Path) -> None:
    target = tmp_path / "non_existent.txt"
    symlink = tmp_path / "broken_link.txt"
    symlink.symlink_to(target)
    assert load_file_content(symlink) == ""


def test_load_file_content_directory(tmp_path) -> None:
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    assert load_file_content(sub_dir) == ""


# ---------------------------------------------------------
# Discord Edge Cases & Local HTTP Loopback Server
# ---------------------------------------------------------

class MockDiscordHTTPHandler(BaseHTTPRequestHandler):
    status_to_return = 200
    response_body = b'{"status": "ok"}'

    def do_POST(self):
        self.send_response(self.status_to_return)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.response_body)

    def log_message(self, format, *args):
        # Silence HTTP server logs during pytest
        pass


@pytest.fixture
def local_http_server():
    server = HTTPServer(("127.0.0.1", 0), MockDiscordHTTPHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_discord_loopback_success(local_http_server) -> None:
    MockDiscordHTTPHandler.status_to_return = 200
    MockDiscordHTTPHandler.response_body = b'{"success": true}'

    with DiscordNotifier(webhook_url=local_http_server) as notifier:
        notifier.send_message(content="Integration test message")


def test_discord_loopback_rate_limit_invalid_json(local_http_server) -> None:
    MockDiscordHTTPHandler.status_to_return = 429
    MockDiscordHTTPHandler.response_body = b"Not JSON"

    with DiscordNotifier(webhook_url=local_http_server) as notifier:
        with pytest.raises(DiscordNotificationError) as exc:
            notifier.send_message(content="Testing rate limit error")
        assert "Rate limited by Discord API. retry_after=unknown" in str(exc.value)


def test_discord_loopback_rate_limit_numeric_retry_after(local_http_server) -> None:
    MockDiscordHTTPHandler.status_to_return = 429
    MockDiscordHTTPHandler.response_body = b'{"retry_after": 2.5}'

    with DiscordNotifier(webhook_url=local_http_server) as notifier:
        with pytest.raises(DiscordNotificationError) as exc:
            notifier.send_message(content="Testing rate limit error")
        assert "retry_after=2.5s" in str(exc.value)


def test_discord_content_length_oversized(local_http_server) -> None:
    # Verify large payloads (e.g. >2000 chars) are handled or rejected cleanly
    huge_content = "X" * 3000
    MockDiscordHTTPHandler.status_to_return = 400
    MockDiscordHTTPHandler.response_body = b'{"message": "Cannot send an empty message or content too long", "code": 50006}'

    with DiscordNotifier(webhook_url=local_http_server) as notifier:
        with pytest.raises(DiscordNotificationError) as exc:
            notifier.send_message(content=huge_content)
        assert "HTTP 400" in str(exc.value)


def test_discord_session_retries_configured() -> None:
    notifier = DiscordNotifier(webhook_url="http://example.com/webhook", max_retries=5)
    adapter = notifier.session.adapters.get("https://")
    assert adapter is not None
    assert adapter.max_retries.total == 5


# ---------------------------------------------------------
# GDrive Service & Helper Edge Cases
# ---------------------------------------------------------

def test_sanitize_gdrive_folder_id_invalid_characters() -> None:
    with pytest.raises(ValueError, match="empty or invalid"):
        sanitize_gdrive_folder_id("folder'id")

    with pytest.raises(ValueError, match="empty or invalid"):
        sanitize_gdrive_folder_id("folder\"id")

    with pytest.raises(ValueError, match="empty or invalid"):
        sanitize_gdrive_folder_id("folder\\id")

    with pytest.raises(ValueError, match="empty or invalid"):
        sanitize_gdrive_folder_id("folder\nid")


def test_gdrive_upload_empty_0_byte_file(tmp_path) -> None:
    empty_file = tmp_path / "empty.dat"
    empty_file.write_bytes(b"")

    svc = GDriveService(folder_id="valid_folder_123")
    mock_api = MagicMock()
    svc._service = mock_api
    mock_api.files().create().execute.return_value = {"id": "empty_id"}

    file_id = svc.upload_file(empty_file, mime_type="application/octet-stream")
    assert file_id == "empty_id"


def test_gdrive_upload_overwrite_multiple_existing_remotes(tmp_path) -> None:
    f = tmp_path / "report.csv"
    f.write_text("dummy")

    svc = GDriveService(folder_id="valid_folder_123")
    mock_api = MagicMock()
    svc._service = mock_api
    files_resource = mock_api.files.return_value
    # Simulate multiple files with identical name existing remotely
    files_resource.list.return_value.execute.return_value = {
        "files": [{"id": "first_match"}, {"id": "second_match"}]
    }
    files_resource.update.return_value.execute.return_value = {"id": "first_match"}

    file_id = svc.upload_file(f, overwrite=True)
    assert file_id == "first_match"
    files_resource.update.assert_called_once()


def test_gdrive_download_file_creates_parent_directories_and_atomic_replace(tmp_path) -> None:
    target_path = tmp_path / "deep" / "nested" / "dest.csv"
    svc = GDriveService()
    mock_api = MagicMock()
    svc._service = mock_api
    mock_api.files().list().execute.return_value = {"files": [{"id": "remote_id"}]}

    with patch("core_lib.gdrive.gdrive_service.MediaIoBaseDownload") as mock_downloader_cls:
        downloader_mock = MagicMock()
        downloader_mock.next_chunk.return_value = (None, True)
        mock_downloader_cls.return_value = downloader_mock

        assert svc.download_file("report.csv", target_path) is True
        assert target_path.exists()
        # Verify no left-over temporary file
        temp_files = list((tmp_path / "deep" / "nested").glob("*.tmp.*"))
        assert len(temp_files) == 0


def test_gdrive_get_latest_file_id_special_characters() -> None:
    svc = GDriveService(folder_id="folder_123")
    mock_api = MagicMock()
    svc._service = mock_api
    mock_api.files().list().execute.return_value = {
        "files": [{"id": "latest_id", "name": "finance's_%_2026.csv", "modifiedTime": "2026-01-01"}]
    }

    file_id = svc.get_latest_file_id(prefix="finance's_%")
    assert file_id == "latest_id"
    # Ensure query escaped properly
    call_kwargs = mock_api.files().list.call_args[1]
    assert r"name contains 'finance\'s_%'" in call_kwargs["q"]


def test_gdrive_get_file_modified_time_missing_field() -> None:
    svc = GDriveService()
    mock_api = MagicMock()
    svc._service = mock_api
    # File found but modifiedTime key is omitted by API
    mock_api.files().list().execute.return_value = {"files": [{"id": "some_id"}]}

    mod_time = svc.get_file_modified_time("file.txt")
    assert mod_time is None


# ---------------------------------------------------------
# Auth Module Edge Cases
# ---------------------------------------------------------

def test_get_google_service_credentials_invalid_json_token(tmp_path) -> None:
    bad_token = tmp_path / "token.json"
    bad_token.write_text("invalid json content")

    creds_path = tmp_path / "credentials.json"
    creds_path.write_text('{"installed": {}}')

    # When token is invalid JSON, Credentials.from_authorized_user_file fails or raises,
    # or falls through to flow
    with patch("core_lib.gdrive.gdrive_auth.InstalledAppFlow") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_creds = MagicMock(spec=Credentials)
        mock_creds.valid = True
        mock_creds.to_json.return_value = "{}"
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        # When JSON is malformed, from_authorized_user_file throws json.decoder.JSONDecodeError
        with pytest.raises(json.decoder.JSONDecodeError):
            get_google_service_credentials(
                credentials_path=creds_path,
                token_path=bad_token,
            )


def test_get_google_service_credentials_parent_dir_creation(tmp_path) -> None:
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"installed": {}}')
    nested_token = tmp_path / "deep" / "secrets" / "token.json"

    with patch("core_lib.gdrive.gdrive_auth.InstalledAppFlow") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_creds = MagicMock(spec=Credentials)
        mock_creds.valid = True
        mock_creds.to_json.return_value = '{"token": "xyz"}'
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        res = get_google_service_credentials(
            credentials_path=creds_file,
            token_path=nested_token,
        )
        assert res == mock_creds
        assert nested_token.exists()
        assert nested_token.read_text() == '{"token": "xyz"}'
