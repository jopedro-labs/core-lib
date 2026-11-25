"""Integration test suite for urllib retry and backoff behavior in scripts/gdrive_update_bot.py."""


from __future__ import annotations

import json
import threading
import urllib.error
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import _Call, call, patch

import pytest

import scripts.gdrive_update_bot as bot_module


class LoopbackHTTPHandler(BaseHTTPRequestHandler):
    """Deterministic HTTP request handler supporting sequential responses."""

    response_queue: list[tuple[int, bytes]] = []
    received_requests: list[str] = []

    def do_GET(self) -> None:
        """Handles HTTP GET requests deterministically using response_queue."""
        self.__class__.received_requests.append(self.path)
        if self.__class__.response_queue:
            status_code, body = self.__class__.response_queue.pop(0)
        else:
            status_code, body = 500, b'{"error": "queue empty"}'

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Silences standard HTTP server stderr logging in pytest output."""


@pytest.fixture
def loopback_server() -> Generator[str, None, None]:
    """Spins up a local HTTPServer on 127.0.0.1:0 with deterministic teardown."""
    server: HTTPServer = HTTPServer(("127.0.0.1", 0), LoopbackHTTPHandler)
    server_port: int = server.server_port
    server_thread: threading.Thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    server_thread.start()
    LoopbackHTTPHandler.response_queue = []
    LoopbackHTTPHandler.received_requests = []

    try:
        yield f"http://127.0.0.1:{server_port}/discovery"
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5.0)
        LoopbackHTTPHandler.response_queue = []
        LoopbackHTTPHandler.received_requests = []


def test_loopback_transient_429_recovery(
    loopback_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies recovery from transient HTTP 429 followed by 200 and exact backoff delays."""
    success_payload: dict[str, str] = {
        "name": "drive",
        "version": "v3",
        "revision": "20261125",
        "title": "Google Drive API",
    }
    encoded_success: bytes = json.dumps(success_payload).encode("utf-8")
    rate_limit_payload: bytes = b'{"error": "Too Many Requests"}'

    LoopbackHTTPHandler.response_queue = [
        (429, rate_limit_payload),
        (200, encoded_success),
    ]

    monkeypatch.setattr(bot_module, "DISCOVERY_URL", loopback_server)

    with patch("scripts.gdrive_update_bot.time.sleep") as mock_sleep:
        metadata, data = bot_module.fetch_discovery_data()

    assert metadata["revision"] == "20261125"
    assert metadata["name"] == "drive"
    assert data["revision"] == "20261125"
    assert len(LoopbackHTTPHandler.received_requests) == 2
    mock_sleep.assert_called_once_with(bot_module.RETRIES_DELAY * 1)


def test_loopback_transient_503_recovery(
    loopback_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies recovery from multiple 503 transient errors before 200 success."""
    success_payload: dict[str, str] = {
        "name": "drive",
        "version": "v3",
        "revision": "20261125",
        "title": "Google Drive API",
    }
    encoded_success: bytes = json.dumps(success_payload).encode("utf-8")
    service_unavailable_payload: bytes = b'{"error": "Service Unavailable"}'

    LoopbackHTTPHandler.response_queue = [
        (503, service_unavailable_payload),
        (503, service_unavailable_payload),
        (200, encoded_success),
    ]

    monkeypatch.setattr(bot_module, "DISCOVERY_URL", loopback_server)

    with patch("scripts.gdrive_update_bot.time.sleep") as mock_sleep:
        metadata, data = bot_module.fetch_discovery_data()

    assert metadata["revision"] == "20261125"
    assert len(LoopbackHTTPHandler.received_requests) == 3
    expected_sleep_calls: list[_Call] = [
        call(bot_module.RETRIES_DELAY * 1),
        call(bot_module.RETRIES_DELAY * 2),
    ]
    assert mock_sleep.call_args_list == expected_sleep_calls


def test_loopback_exhausted_retries_raises_http_error(
    loopback_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that persistent HTTP errors exhaust retries and propagate urllib HTTPError."""
    rate_limit_payload: bytes = b'{"error": "Rate limit exceeded"}'
    LoopbackHTTPHandler.response_queue = [
        (429, rate_limit_payload),
        (429, rate_limit_payload),
        (429, rate_limit_payload),
    ]

    monkeypatch.setattr(bot_module, "DISCOVERY_URL", loopback_server)

    with patch("scripts.gdrive_update_bot.time.sleep") as mock_sleep:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            bot_module.fetch_discovery_data()

    assert exc_info.value.code == 429
    assert len(LoopbackHTTPHandler.received_requests) == bot_module.MAX_RETRIES
    expected_sleep_calls: list[_Call] = [
        call(bot_module.RETRIES_DELAY * 1),
        call(bot_module.RETRIES_DELAY * 2),
    ]
    assert mock_sleep.call_args_list == expected_sleep_calls


def test_loopback_exhausted_retries_500_server_error(
    loopback_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that persistent 500 server errors exhaust retries and propagate HTTPError."""
    server_error_payload: bytes = b'{"error": "Internal Server Error"}'
    LoopbackHTTPHandler.response_queue = [
        (500, server_error_payload),
        (500, server_error_payload),
        (500, server_error_payload),
    ]

    monkeypatch.setattr(bot_module, "DISCOVERY_URL", loopback_server)

    with patch("scripts.gdrive_update_bot.time.sleep") as mock_sleep:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            bot_module.fetch_discovery_data()

    assert exc_info.value.code == 500
    assert len(LoopbackHTTPHandler.received_requests) == bot_module.MAX_RETRIES
    assert mock_sleep.call_count == bot_module.MAX_RETRIES - 1
