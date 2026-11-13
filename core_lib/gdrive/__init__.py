"""Google Drive client submodule — authentication, service, and helpers."""

from __future__ import annotations


def __getattr__(name: str) -> object:
    if name == "GDriveService":
        from core_lib.gdrive.gdrive_service import GDriveService
        return GDriveService
    if name == "get_google_service_credentials":
        from core_lib.gdrive.gdrive_auth import get_google_service_credentials
        return get_google_service_credentials
    if name == "sanitize_gdrive_folder_id":
        from core_lib.gdrive.gdrive_helpers import sanitize_gdrive_folder_id
        return sanitize_gdrive_folder_id
    raise AttributeError(f"module 'core_lib.gdrive' has no attribute {name!r}")
