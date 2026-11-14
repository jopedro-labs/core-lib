from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.gdrive_update_bot import (
    MAX_RETRIES,
    fetch_discovery_data,
    load_previous_revision,
    main,
    save_state,
    write_github_output,
)

MOCK_API_DATA = {
    "name": "drive",
    "version": "v3",
    "revision": "20261114",
    "title": "Google Drive API",
}


def _make_mock_response(data: dict, status: int = 200) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.read.return_value = json.dumps(data).encode("utf-8")
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


# ---------------------------------------------------------------------------
# fetch_discovery_data
# ---------------------------------------------------------------------------

@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_success(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value.__enter__.return_value = _make_mock_response(MOCK_API_DATA)

    data = fetch_discovery_data()

    assert data["revision"] == "20261114"
    assert data["version"] == "v3"
    assert data["name"] == "drive"
    assert data["title"] == "Google Drive API"


@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_missing_fields_use_defaults(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value.__enter__.return_value = _make_mock_response({})

    data = fetch_discovery_data()

    assert data["revision"] == "unknown"
    assert data["name"] == "unknown"


@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_unexpected_http_status_raises(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value.__enter__.return_value = _make_mock_response({}, status=500)

    with pytest.raises(RuntimeError, match="Unexpected HTTP status: 500"):
        fetch_discovery_data()


@patch("scripts.gdrive_update_bot.time.sleep")
@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_retries_exact_count_then_raises(mock_urlopen: MagicMock, mock_sleep: MagicMock) -> None:
    mock_urlopen.side_effect = TimeoutError("timed out")

    with pytest.raises(TimeoutError):
        fetch_discovery_data()

    assert mock_urlopen.call_count == MAX_RETRIES
    assert mock_sleep.call_count == MAX_RETRIES - 1


@patch("scripts.gdrive_update_bot.time.sleep")
@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_succeeds_on_second_attempt(mock_urlopen: MagicMock, mock_sleep: MagicMock) -> None:
    good_response = _make_mock_response(MOCK_API_DATA)
    mock_urlopen.side_effect = [
        TimeoutError("first attempt fails"),
        MagicMock(__enter__=lambda s: good_response, __exit__=MagicMock(return_value=False)),
    ]

    data = fetch_discovery_data()

    assert data["revision"] == "20261114"
    assert mock_urlopen.call_count == 2
    mock_sleep.assert_called_once()


# ---------------------------------------------------------------------------
# load_previous_revision / save_state / write_github_output
# ---------------------------------------------------------------------------

def test_load_previous_revision_no_file(tmp_path: Path) -> None:
    with patch("scripts.gdrive_update_bot.STATE_FILE", tmp_path / "nonexistent.json"):
        assert load_previous_revision() is None


def test_load_previous_revision_valid_file(tmp_path: Path) -> None:
    state_file = tmp_path / "gdrive-revision.json"
    state_file.write_text(json.dumps(MOCK_API_DATA), encoding="utf-8")

    with patch("scripts.gdrive_update_bot.STATE_FILE", state_file):
        assert load_previous_revision() == "20261114"


def test_load_previous_revision_missing_key(tmp_path: Path) -> None:
    state_file = tmp_path / "gdrive-revision.json"
    state_file.write_text(json.dumps({"name": "drive"}), encoding="utf-8")

    with patch("scripts.gdrive_update_bot.STATE_FILE", state_file):
        assert load_previous_revision() is None


def test_load_previous_revision_corrupt_file(tmp_path: Path) -> None:
    state_file = tmp_path / "gdrive-revision.json"
    state_file.write_text("not valid json", encoding="utf-8")

    with patch("scripts.gdrive_update_bot.STATE_FILE", state_file):
        assert load_previous_revision() is None


def test_save_state_creates_file(tmp_path: Path) -> None:
    state_file = tmp_path / "sub" / "gdrive-revision.json"

    with patch("scripts.gdrive_update_bot.STATE_FILE", state_file):
        save_state(MOCK_API_DATA)

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["revision"] == "20261114"


def test_write_github_output_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    # Should execute safely without raising exceptions
    write_github_output("result", "ok")


def test_write_github_output_present_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    write_github_output("result", "revision_changed")

    content = out_file.read_text(encoding="utf-8")
    assert "result=revision_changed" in content


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

@patch("scripts.gdrive_update_bot.write_github_output")
@patch("scripts.gdrive_update_bot.fetch_discovery_data")
def test_main_no_previous_state_creates_file(
    mock_fetch: MagicMock,
    mock_output: MagicMock,
    tmp_path: Path,
) -> None:
    mock_fetch.return_value = MOCK_API_DATA
    state_file = tmp_path / "gdrive-revision.json"

    with patch("scripts.gdrive_update_bot.STATE_FILE", state_file):
        main()

    assert state_file.exists()
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["revision"] == "20261114"
    assert saved["name"] == "drive"
    mock_output.assert_called_with("result", "ok")


@patch("scripts.gdrive_update_bot.write_github_output")
@patch("scripts.gdrive_update_bot.fetch_discovery_data")
def test_main_same_revision_no_exit(
    mock_fetch: MagicMock,
    mock_output: MagicMock,
    tmp_path: Path,
) -> None:
    mock_fetch.return_value = MOCK_API_DATA
    state_file = tmp_path / "gdrive-revision.json"
    state_file.write_text(json.dumps(MOCK_API_DATA), encoding="utf-8")

    with patch("scripts.gdrive_update_bot.STATE_FILE", state_file):
        main()

    mock_output.assert_called_with("result", "ok")


@patch("scripts.gdrive_update_bot.write_github_output")
@patch("scripts.gdrive_update_bot.fetch_discovery_data")
def test_main_revision_changed_exits_2(
    mock_fetch: MagicMock,
    mock_output: MagicMock,
    tmp_path: Path,
) -> None:
    old_data = {**MOCK_API_DATA, "revision": "20260101"}
    new_data = {**MOCK_API_DATA, "revision": "20261114"}
    mock_fetch.return_value = new_data
    state_file = tmp_path / "gdrive-revision.json"
    state_file.write_text(json.dumps(old_data), encoding="utf-8")

    with patch("scripts.gdrive_update_bot.STATE_FILE", state_file):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 2
    mock_output.assert_called_with("result", "revision_changed")
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["revision"] == "20261114"


@patch("scripts.gdrive_update_bot.write_github_output")
@patch("scripts.gdrive_update_bot.fetch_discovery_data")
def test_main_network_error_exits_1(
    mock_fetch: MagicMock,
    mock_output: MagicMock,
) -> None:
    mock_fetch.side_effect = RuntimeError("network failure")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    mock_output.assert_called_with("result", "error")