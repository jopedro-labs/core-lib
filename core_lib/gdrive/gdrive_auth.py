"""
Authentication module for Google Drive using OAuth2 (installed app flow).

First run: opens a browser for authorization and saves secrets/token.json.
Subsequent runs: loads the saved token with automatic refresh.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES: list[str] = ["https://www.googleapis.com/auth/drive.file"]

_DEFAULT_CREDENTIALS_PATH = "credentials.json"
_DEFAULT_TOKEN_PATH = "token.json"


def get_google_service_credentials(
    credentials_path: str | Path | None = None,
    token_path: str | Path | None = None,
) -> Credentials:
    """Returns valid OAuth2 credentials for Google Drive.

    Args:
        credentials_path: Path to the OAuth2 credentials JSON file.
                          Defaults to GDRIVE_CREDENTIALS_PATH env var or 'credentials.json'.
        token_path: Path to the token file for storing/loading the access token.
                    Defaults to GDRIVE_TOKEN_PATH env var or 'token.json'.
    """
    creds_path = Path(
        credentials_path
        or os.getenv("GDRIVE_CREDENTIALS_PATH")
        or _DEFAULT_CREDENTIALS_PATH
    )
    tok_path = Path(
        token_path
        or os.getenv("GDRIVE_TOKEN_PATH")
        or _DEFAULT_TOKEN_PATH
    )

    creds: Credentials | None = None

    if tok_path.exists():
        creds = Credentials.from_authorized_user_file(str(tok_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(f"[gdrive] Missing OAuth2 credentials file at {creds_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        assert creds is not None
        tok_path.parent.mkdir(parents=True, exist_ok=True)
        tok_path.write_text(creds.to_json())

    return creds
