"""
Service wrapper for Google Drive operations.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from core_lib.gdrive.gdrive_auth import get_google_service_credentials
from core_lib.gdrive.gdrive_helpers import sanitize_gdrive_folder_id
from core_lib.gdrive.types import (
    DriveFileListResponse,
    DriveFileResource,
    GoogleDriveClient,
)
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
                               Defaults to GDRIVE_CREDENTIALS_PATH env var or 'credentials.json'.
            token_path: Path to the token file.
                        Defaults to GDRIVE_TOKEN_PATH env var or 'token.json'.
            folder_id: Target Google Drive folder ID for operations.
                       Defaults to GDRIVE_DATA_FOLDER_ID env var.
        """
        if credentials_path and not Path(credentials_path).exists():
            raise FileNotFoundError(f"[gdrive] Missing Google credentials file: {credentials_path}")
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.folder_id: str | None = folder_id or os.getenv("GDRIVE_DATA_FOLDER_ID")
        self._service: GoogleDriveClient | None = None

    def _get_service(self) -> GoogleDriveClient | None:
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

    @staticmethod
    def _escape_query_str(val: str) -> str:
        """Escapes backslashes and single quotes for Google Drive search queries."""
        return val.replace("\\", "\\\\").replace("'", "\\'")

    def _format_parents_clause(self, folder_id: str | None) -> str:
        """Validates and formats the parents query clause."""
        target_folder = folder_id or self.folder_id
        if not target_folder:
            return ""
        clean_folder = sanitize_gdrive_folder_id(target_folder)
        safe_folder = self._escape_query_str(clean_folder or "")
        return f" and '{safe_folder}' in parents"

    def verify_folder_access(self, folder_id: str | None = None) -> bool:
        """Verifies remotely if a Google Drive folder exists and is accessible."""
        service = self._get_service()
        if not service:
            return False

        target_folder = folder_id or self.folder_id
        if not target_folder:
            return False

        try:
            clean_folder = sanitize_gdrive_folder_id(target_folder)
            if not clean_folder:
                return False
            file_metadata: dict[str, Any] = (
                service.files().get(fileId=clean_folder, fields="id, mimeType").execute()
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
        try:
            safe_name = self._escape_query_str(file_name)
            parents_clause = self._format_parents_clause(folder_id)
            query = f"name = '{safe_name}' and trashed = false{parents_clause}"
            response: DriveFileListResponse = (
                service.files().list(q=query, fields="files(id)").execute()
            )
            return len(response.get("files", [])) > 0
        except Exception as e:
            logger.error(f"[gdrive] Error checking file '{file_name}': {e}")
            return False

    def list_files(self, folder_id: str | None = None, limit: int = 100) -> list[DriveFileResource]:
        """Lists files inside a specific Google Drive folder."""
        service = self._get_service()
        if not service:
            return []
        try:
            parents_clause = self._format_parents_clause(folder_id)
            if parents_clause:
                query = f"{parents_clause.lstrip(' and ')} and trashed = false"
            else:
                query = "trashed = false"
            response: DriveFileListResponse = (
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
            clean_folder = sanitize_gdrive_folder_id(target_folder) if target_folder else None
            if overwrite:
                safe_name = self._escape_query_str(path.name)
                parents_clause = self._format_parents_clause(clean_folder)
                query = f"name = '{safe_name}' and trashed = false{parents_clause}"
                existing_resp: DriveFileListResponse = (
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
                "parents": [clean_folder] if clean_folder else [],
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
        """Downloads a file from Google Drive to a local destination path safely and atomically."""
        dest = Path(destination_path)
        service = self._get_service()
        if not service:
            return False
        try:
            safe_name = self._escape_query_str(file_name)
            parents_clause = self._format_parents_clause(folder_id)
            query = f"name = '{safe_name}' and trashed = false{parents_clause}"
            response: DriveFileListResponse = (
                service.files().list(q=query, fields="files(id)").execute()
            )
            files = response.get("files", [])
            if not files:
                logger.warning(f"[gdrive] '{file_name}' not found.")
                return False
            file_id = files[0]["id"]
            request = service.files().get_media(fileId=file_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp_dest = dest.with_suffix(dest.suffix + f".tmp.{os.getpid()}")
            with open(temp_dest, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            temp_dest.replace(dest)
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

    def get_latest_file_id(
        self, prefix: str = "finances", folder_id: str | None = None
    ) -> str | None:
        """Finds the ID of the most recent file in Google Drive matching the given prefix.

        Args:
            prefix: String prefix to filter filenames. Defaults to "finances".
            folder_id: Optional specific folder ID to search within. Defaults to instance folder_id.

        Returns:
            The file ID string of the latest matching file, or None if not found.
        """
        service = self._get_service()
        if not service:
            return None

        try:
            safe_prefix = self._escape_query_str(prefix)
            parents_clause = self._format_parents_clause(folder_id)
            query = f"name contains '{safe_prefix}' and trashed = false{parents_clause}"

            response: DriveFileListResponse = (
                service.files()
                .list(
                    q=query,
                    pageSize=10,
                    orderBy="modifiedTime desc",
                    fields="files(id, name, modifiedTime)",
                )
                .execute()
            )

            files = response.get("files", [])
            if not files:
                logger.warning(f"[gdrive] No files found matching prefix '{prefix}'.")
                return None

            latest_file = files[0]
            file_name = latest_file.get("name")
            mod_time = latest_file.get("modifiedTime")
            logger.info(f"[gdrive] Found latest remote file: '{file_name}' (modified: {mod_time})")
            return str(latest_file["id"])
        except Exception as e:
            logger.error(f"[gdrive] Error finding latest file with prefix '{prefix}': {e}")
            return None

    def download_latest_file(self, destination_path: str | Path, prefix: str = "finances") -> bool:
        """Downloads the most recent file matching a given prefix
        directly to a local destination path safely and atomically.

        Args:
            destination_path: Local filesystem path where the file should be saved.
            prefix: String prefix used to locate the latest remote file. Defaults to "finances".

        Returns:
            True if the download succeeded, False otherwise.
        """
        dest = Path(destination_path)
        file_id = self.get_latest_file_id(prefix=prefix)
        if not file_id:
            return False

        service = self._get_service()
        if not service:
            return False

        try:
            request = service.files().get_media(fileId=file_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp_dest = dest.with_suffix(dest.suffix + f".tmp.{os.getpid()}")

            with open(temp_dest, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            temp_dest.replace(dest)
            logger.success(f"[gdrive] Successfully downloaded latest remote file to '{dest}'.")
            return True
        except Exception as e:
            logger.error(f"[gdrive] Failed to download latest file ID '{file_id}': {e}")
            return False

    def get_file_modified_time(self, file_name: str, folder_id: str | None = None) -> str | None:
        """Gets the modifiedTime of a specific file by name in Google Drive."""
        service = self._get_service()
        if not service:
            return None
        try:
            safe_name = self._escape_query_str(file_name)
            parents_clause = self._format_parents_clause(folder_id)
            query = f"name = '{safe_name}' and trashed = false{parents_clause}"
            response: DriveFileListResponse = (
                service.files()
                .list(q=query, fields="files(id, name, modifiedTime)", pageSize=1)
                .execute()
            )
            files = response.get("files", [])
            if not files:
                return None
            mod_time: Any = files[0].get("modifiedTime")
            return str(mod_time) if mod_time is not None else None
        except Exception as e:
            logger.error(f"[gdrive] Error getting modification time for '{file_name}': {e}")
            return None
