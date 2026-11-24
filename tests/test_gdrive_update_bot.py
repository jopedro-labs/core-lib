from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.gdrive_update_bot import (
    MAX_RETRIES,
    fetch_discovery_data,
    load_previous_revision,
    main,
    stage_runner_files,
    write_github_output,
)

MOCK_METADATA = {
    "name": "drive",
    "version": "v3",
    "revision": "20261114",
    "title": "Google Drive API",
}

MOCK_FULL_DISCOVERY = {
    "name": "drive",
    "version": "v3",
    "revision": "20261114",
    "title": "Google Drive API",
    "resources": {},
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
    mock_urlopen.return_value.__enter__.return_value = _make_mock_response(MOCK_METADATA)

    metadata, discovery = fetch_discovery_data()

    assert metadata["revision"] == "20261114"
    assert metadata["version"] == "v3"
    assert metadata["name"] == "drive"
    assert metadata["title"] == "Google Drive API"
    assert discovery["revision"] == "20261114"


@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_missing_fields_use_defaults(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value.__enter__.return_value = _make_mock_response({})

    metadata, discovery = fetch_discovery_data()

    assert metadata["revision"] == "unknown"
    assert metadata["name"] == "unknown"
    assert discovery == {}


@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_unexpected_http_status_raises(mock_urlopen: MagicMock) -> None:
    mock_urlopen.return_value.__enter__.return_value = _make_mock_response({}, status=500)

    with pytest.raises(RuntimeError, match="Unexpected HTTP status: 500"):
        fetch_discovery_data()


@patch("scripts.gdrive_update_bot.time.sleep")
@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_retries_exact_count_then_raises(
    mock_urlopen: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_urlopen.side_effect = TimeoutError("timed out")

    with pytest.raises(TimeoutError):
        fetch_discovery_data()

    assert mock_urlopen.call_count == MAX_RETRIES
    assert mock_sleep.call_count == MAX_RETRIES - 1


@patch("scripts.gdrive_update_bot.time.sleep")
@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_succeeds_on_second_attempt(mock_urlopen: MagicMock, mock_sleep: MagicMock) -> None:
    good_response = _make_mock_response(MOCK_METADATA)
    mock_urlopen.side_effect = [
        TimeoutError("first attempt fails"),
        MagicMock(__enter__=lambda s: good_response, __exit__=MagicMock(return_value=False)),
    ]

    metadata, discovery = fetch_discovery_data()

    assert metadata["revision"] == "20261114"
    assert mock_urlopen.call_count == 2
    mock_sleep.assert_called_once()


# ---------------------------------------------------------------------------
# load_previous_revision / stage_runner_files / write_github_output
# ---------------------------------------------------------------------------

def test_load_previous_revision_no_file(tmp_path: Path) -> None:
    with patch("scripts.gdrive_update_bot.STATE_FILE", tmp_path / "nonexistent.json"):
        assert load_previous_revision() is None


def test_load_previous_revision_valid_file(tmp_path: Path) -> None:
    state_file = tmp_path / "gdrive-revision.json"
    state_file.write_text(json.dumps(MOCK_METADATA), encoding="utf-8")

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


def test_stage_runner_files_creates_files(tmp_path: Path) -> None:
    state_dir = tmp_path / "revisions"
    state_file = state_dir / "gdrive-revision.json"
    prev_state_file = state_dir / "gdrive-revision.previous.json"
    disc_file = state_dir / "drive-v3-discovery.json"
    prev_disc_file = state_dir / "drive-v3-discovery.previous.json"

    with (
        patch("scripts.gdrive_update_bot.STATE_DIR", state_dir),
        patch("scripts.gdrive_update_bot.STATE_FILE", state_file),
        patch("scripts.gdrive_update_bot.PREVIOUS_STATE_FILE", prev_state_file),
        patch("scripts.gdrive_update_bot.DISCOVERY_FILE", disc_file),
        patch("scripts.gdrive_update_bot.PREVIOUS_DISCOVERY_FILE", prev_disc_file),
    ):
        stage_runner_files(MOCK_METADATA, MOCK_FULL_DISCOVERY)

    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved_state["revision"] == "20261114"

    saved_disc = json.loads(disc_file.read_text(encoding="utf-8"))
    assert saved_disc["revision"] == "20261114"


def test_write_github_output_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    # Should execute safely without raising exceptions
    write_github_output("result", "ok")


def test_write_github_output_present_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    write_github_output("result", "revision_changed")

    content = out_file.read_text(encoding="utf-8")
    assert "result<<EOF_" in content
    assert "revision_changed" in content


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
    mock_fetch.return_value = (MOCK_METADATA, MOCK_FULL_DISCOVERY)
    state_dir = tmp_path / "revisions"
    state_file = state_dir / "gdrive-revision.json"
    disc_file = state_dir / "drive-v3-discovery.json"
    prev_state_file = state_dir / "gdrive-revision.previous.json"
    prev_disc_file = state_dir / "drive-v3-discovery.previous.json"

    with (
        patch("scripts.gdrive_update_bot.STATE_DIR", state_dir),
        patch("scripts.gdrive_update_bot.STATE_FILE", state_file),
        patch("scripts.gdrive_update_bot.PREVIOUS_STATE_FILE", prev_state_file),
        patch("scripts.gdrive_update_bot.DISCOVERY_FILE", disc_file),
        patch("scripts.gdrive_update_bot.PREVIOUS_DISCOVERY_FILE", prev_disc_file),
    ):
        main()

    assert state_file.exists()
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["revision"] == "20261114"
    assert saved["name"] == "drive"
    mock_output.assert_any_call("result", "ok")


@patch("scripts.gdrive_update_bot.write_github_output")
@patch("scripts.gdrive_update_bot.fetch_discovery_data")
def test_main_same_revision_no_exit(
    mock_fetch: MagicMock,
    mock_output: MagicMock,
    tmp_path: Path,
) -> None:
    mock_fetch.return_value = (MOCK_METADATA, MOCK_FULL_DISCOVERY)
    state_dir = tmp_path / "revisions"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "gdrive-revision.json"
    disc_file = state_dir / "drive-v3-discovery.json"
    state_file.write_text(json.dumps(MOCK_METADATA), encoding="utf-8")
    prev_state_file = state_dir / "gdrive-revision.previous.json"
    prev_disc_file = state_dir / "drive-v3-discovery.previous.json"

    with (
        patch("scripts.gdrive_update_bot.STATE_DIR", state_dir),
        patch("scripts.gdrive_update_bot.STATE_FILE", state_file),
        patch("scripts.gdrive_update_bot.PREVIOUS_STATE_FILE", prev_state_file),
        patch("scripts.gdrive_update_bot.DISCOVERY_FILE", disc_file),
        patch("scripts.gdrive_update_bot.PREVIOUS_DISCOVERY_FILE", prev_disc_file),
    ):
        main()

    mock_output.assert_any_call("result", "ok")


@patch("scripts.gdrive_update_bot.write_github_output")
@patch("scripts.gdrive_update_bot.fetch_discovery_data")
def test_main_revision_changed_exits_2(
    mock_fetch: MagicMock,
    mock_output: MagicMock,
    tmp_path: Path,
) -> None:
    old_data = {**MOCK_METADATA, "revision": "20260101"}
    new_data = {**MOCK_METADATA, "revision": "20261114"}
    mock_fetch.return_value = (new_data, MOCK_FULL_DISCOVERY)
    state_dir = tmp_path / "revisions"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "gdrive-revision.json"
    disc_file = state_dir / "drive-v3-discovery.json"
    state_file.write_text(json.dumps(old_data), encoding="utf-8")
    prev_state_file = state_dir / "gdrive-revision.previous.json"
    prev_disc_file = state_dir / "drive-v3-discovery.previous.json"

    with (
        patch("scripts.gdrive_update_bot.STATE_DIR", state_dir),
        patch("scripts.gdrive_update_bot.STATE_FILE", state_file),
        patch("scripts.gdrive_update_bot.PREVIOUS_STATE_FILE", prev_state_file),
        patch("scripts.gdrive_update_bot.DISCOVERY_FILE", disc_file),
        patch("scripts.gdrive_update_bot.PREVIOUS_DISCOVERY_FILE", prev_disc_file),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 2
    mock_output.assert_any_call("result", "revision_changed")
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


@patch("scripts.gdrive_update_bot.time.sleep")
@patch("scripts.gdrive_update_bot.urllib.request.urlopen")
def test_fetch_retries_exact_linear_backoff_values(mock_urlopen, mock_sleep) -> None:
    """Ensures backoff mutant (RETRIES_DELAY * attempt) is killed."""
    import unittest.mock
    from scripts.gdrive_update_bot import RETRIES_DELAY, fetch_discovery_data

    mock_urlopen.side_effect = TimeoutError("transient timeout")

    with pytest.raises(TimeoutError):
        fetch_discovery_data()

    # Attempts 1 and 2 sleep before failure 3 raises
    expected_calls = [
        unittest.mock.call(RETRIES_DELAY * 1),
        unittest.mock.call(RETRIES_DELAY * 2),
    ]
    assert mock_sleep.call_args_list == expected_calls
