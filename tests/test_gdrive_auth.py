from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core_lib.gdrive.gdrive_auth import get_google_service_credentials


def test_raises_when_credentials_file_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_google_service_credentials(
            credentials_path=tmp_path / "missing.json",
            token_path=tmp_path / "token.json",
        )


def test_loads_existing_valid_token(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")

    mock_creds = MagicMock()
    mock_creds.valid = True

    with patch("core_lib.gdrive.gdrive_auth.Credentials.from_authorized_user_file", return_value=mock_creds):
        result = get_google_service_credentials(
            credentials_path=tmp_path / "creds.json",
            token_path=token_path,
        )

    assert result is mock_creds


def test_refreshes_expired_token(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh"
    mock_creds.to_json.return_value = "{}"

    with patch("core_lib.gdrive.gdrive_auth.Credentials.from_authorized_user_file", return_value=mock_creds):
        result = get_google_service_credentials(
            credentials_path=tmp_path / "creds.json",
            token_path=token_path,
        )

    mock_creds.refresh.assert_called_once()
    assert result is mock_creds


def test_uses_env_var_for_credentials_path(tmp_path, monkeypatch):
    monkeypatch.setenv("GDRIVE_CREDENTIALS_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setenv("GDRIVE_TOKEN_PATH", str(tmp_path / "token.json"))

    with pytest.raises(FileNotFoundError):
        get_google_service_credentials()
