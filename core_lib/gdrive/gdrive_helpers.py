"""
Helper functions for Google Drive validation and utilities.
"""

from __future__ import annotations

from core_lib.logger import logger


def sanitize_gdrive_folder_id(folder_id: str | None) -> str | None:
    """Sanitizes and validates a Google Drive folder ID string.

    Returns:
        The stripped folder ID, or None if input is None.

    Raises:
        ValueError: If the folder ID is empty or contains only whitespace.
    """
    if folder_id is None:
        return None

    cleaned_id = folder_id.strip()
    if not cleaned_id:
        raise ValueError("[gdrive] Google Drive folder ID cannot be empty or invalid.")

    return cleaned_id


def verify_gdrive_folder_access(folder_id: str, credentials_path: str | None = None) -> bool:
    """Verifies remotely if a Google Drive folder exists and is accessible.

    Args:
        folder_id: The Google Drive folder ID to check.
        credentials_path: Optional path to the OAuth2 credentials file.

    Returns:
        True if the folder is accessible and valid, False otherwise.
    """
    try:
        from core_lib.gdrive.gdrive_service import GDriveService

        drive_service = GDriveService(
            credentials_path=credentials_path,
            folder_id=folder_id,
        )
        return drive_service.verify_folder_access(folder_id)
    except Exception as e:
        logger.error(f"[gdrive] Failed to verify access for folder '{folder_id}'", exception=e)
        return False
