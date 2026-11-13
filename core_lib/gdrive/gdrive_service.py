"""
Service wrapper for Google Drive operations.
"""

from __future__ import annotations

import io
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from core_lib.gdrive.gdrive_auth import get_google_service_credentials
from core_lib.logger import logger


class GDriveService:
    """Wrapper for Google Drive operations using OAuth2 user credentials."""

    def __init__(
        self,
        credentials_path: str | Path | None = None,
        token_path: str | Path | None = None,
        folder_id: str | None = None,
    ) -> None:
        """Initializes the Google Drive service wrapper.

        Args:
            credentials_path: Path to the OAuth2 credentials JSON file.
                               Defaults to gdrive_CREDENTIALS_PATH env var or 'credentials.json'.
            token_path: Path to the token file.
                        Defaults to gdrive_TOKEN_PATH env var or 'token.json'.
            folder_id: Target Google Drive folder ID for operations.
                       Defaults to gdrive_DATA_FOLDER_ID env var.
        """
        if credentials_path and not Path(credentials_path).exists():
            raise FileNotFoundError(f"[gdrive] Missing Google credentials file: {credentials_path}")
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.folder_id: str | None = folder_id or os.getenv("GDRIVE_DATA_FOLDER_ID")
        self._service: Any | None = None

    def _get_service(self) -> Any | None:
        if self._service is None:
            try:
                creds = get_google_service_credentials(
                    credentials_path=self.credentials_path,
                    token_path=self.token_path,
                )
                if not creds:
                    logger.warning("[gdrive] No valid credentials available.")
                    return None
                self._service = build("drive", "v3", credentials=creds)
            except Exception as e:
                logger.error(f"[gdrive] Failed to initialise service: {e}")
                return None
        return self._service

    def verify_folder_access(self, folder_id: str | None = None) -> bool:
        """Verifies remotely if a Google Drive folder exists and is accessible."""
        service = self._get_service()
        if not service:
            return False

        target_folder = folder_id or self.folder_id
        if not target_folder:
            return False

        try:
            file_metadata: dict[str, Any] = (
                service.files().get(fileId=target_folder, fields="id, mimeType").execute()
            )
            return file_metadata.get("mimeType") == "application/vnd.google-apps.folder"
        except Exception as e:
            logger.error(f"[gdrive] Error verifying folder '{target_folder}': {e}")
            return False

    def file_exists(self, file_name: str, folder_id: str | None = None) -> bool:
        """Checks whether a file with the given name exists in Google Drive."""
        service = self._get_service()
        if not service:
            return False
        target_folder = folder_id or self.folder_id
        safe_name = file_name.replace("'", "\\'")
        query = f"name = '{safe_name}' and trashed = false"
        if target_folder:
            query += f" and '{target_folder}' in parents"
        try:
            response: dict[str, list[dict[str, str]]] = (
                service.files().list(q=query, fields="files(id)").execute()
            )
            return len(response.get("files", [])) > 0
        except Exception as e:
            logger.error(f"[gdrive] Error checking file '{file_name}': {e}")
            return False

    def list_files(self, folder_id: str | None = None, limit: int = 100) -> list[dict[str, str]]:
        """Lists files inside a specific Google Drive folder."""
        service = self._get_service()
        if not service:
            return []
        target_folder = folder_id or self.folder_id
        query = "trashed = false"
        if target_folder:
            query = f"'{target_folder}' in parents and trashed = false"
        try:
            response: dict[str, list[dict[str, str]]] = (
                service.files().list(q=query, pageSize=limit, fields="files(id, name)").execute()
            )
            return response.get("files", [])
        except Exception as e:
            logger.error(f"[gdrive] Error listing files: {e}")
            return []

    def upload_file(
        self,
        file_path: str | Path,
        folder_id: str | None = None,
        overwrite: bool = False,
        mime_type: str = "application/octet-stream",
    ) -> str | None:
        """Uploads a local file to Google Drive."""
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"[gdrive] File not found: '{path}'.")
            return None
        service = self._get_service()
        if not service:
            return None
        target_folder = folder_id or self.folder_id
        media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
        try:
            if overwrite:
                safe_name = path.name.replace("'", "\\'")
                query = f"name = '{safe_name}' and trashed = false"
                if target_folder:
                    query += f" and '{target_folder}' in parents"
                existing_resp: dict[str, list[dict[str, str]]] = (
                    service.files().list(q=query, fields="files(id)").execute()
                )
                existing_files = existing_resp.get("files", [])
                if existing_files:
                    file_id = existing_files[0]["id"]
                    service.files().update(fileId=file_id, media_body=media).execute()
                    logger.info(f"[gdrive] '{path.name}' updated.")
                    return file_id
            file_metadata = {
                "name": path.name,
                "parents": [target_folder] if target_folder else [],
            }
            created_file: dict[str, str] = (
                service.files().create(body=file_metadata, media_body=media, fields="id").execute()
            )
            logger.success(f"[gdrive] '{path.name}' uploaded successfully.")
            return created_file.get("id")
        except Exception as e:
            logger.error(f"[gdrive] Upload failed for '{path.name}': {e}")
            return None

    def download_file(
        self,
        file_name: str,
        destination_path: str | Path,
        folder_id: str | None = None,
    ) -> bool:
        """Downloads a file from Google Drive to a local destination path."""
        dest = Path(destination_path)
        service = self._get_service()
        if not service:
            return False
        target_folder = folder_id or self.folder_id
        safe_name = file_name.replace("'", "\\'")
        query = f"name = '{safe_name}' and trashed = false"
        if target_folder:
            query += f" and '{target_folder}' in parents"
        try:
            response: dict[str, list[dict[str, str]]] = (
                service.files().list(q=query, fields="files(id)").execute()
            )
            files = response.get("files", [])
            if not files:
                logger.warning(f"[gdrive] '{file_name}' not found in folder '{target_folder}'.")
                return False
            file_id = files[0]["id"]
            request = service.files().get_media(fileId=file_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with io.BytesIO() as fh:
                downloader = MediaIoBaseDownload(fh, request)
                while not downloader.next_chunk()[1]:
                    pass
                dest.write_bytes(fh.getvalue())
            logger.info(f"[gdrive] '{file_name}' downloaded to '{dest}'.")
            return True
        except Exception as e:
            logger.error(f"[gdrive] Download failed for '{file_name}': {e}")
            return False

    def backup_file(self, file_path: str | Path, folder_id: str | None = None) -> bool:
        """Backs up a local file by overwriting its remote counterpart or creating it if missing."""
        return self.upload_file(file_path, folder_id=folder_id, overwrite=True) is not None

    def sync_files(
        self, file_paths: Sequence[str | Path], direction: str = "pull"
    ) -> dict[str, bool]:
        """Synchronizes a sequence of local files with Google Drive (pull or push)."""
        results: dict[str, bool] = {}
        for file_path in file_paths:
            path = Path(file_path)
            try:
                if direction == "pull":
                    results[path.name] = self.download_file(path.name, path)
                elif direction == "push":
                    results[path.name] = self.upload_file(path, overwrite=True) is not None
                else:
                    raise ValueError(f"[gdrive] Invalid direction: {direction}")
            except Exception as e:
                logger.error(f"[gdrive] Sync error for {path.name}: {e}")
                results[path.name] = False
        return results
