"""Type definitions and schemas for Google Drive operations."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class DriveFileResource(TypedDict, total=False):
    """Structural schema for Google Drive API v3 file resources."""

    id: str
    name: str
    mimeType: str
    modifiedTime: str
    parents: list[str]
    size: str


class DriveFileListResponse(TypedDict, total=False):
    """Structural schema for Google Drive API v3 file listing responses."""

    kind: str
    nextPageToken: str
    incompleteSearch: bool
    files: list[DriveFileResource]


class GoogleDriveExecutable(Protocol):
    """Protocol for executable API requests in google-api-python-client."""

    def execute(self) -> Any:
        ...


class GoogleDriveFilesResource(Protocol):
    """Protocol for Google Drive API files resource."""

    def get(self, **kwargs: Any) -> GoogleDriveExecutable:
        ...

    def list(self, **kwargs: Any) -> GoogleDriveExecutable:
        ...

    def create(self, **kwargs: Any) -> GoogleDriveExecutable:
        ...

    def update(self, **kwargs: Any) -> GoogleDriveExecutable:
        ...

    def get_media(self, **kwargs: Any) -> GoogleDriveExecutable:
        ...


class GoogleDriveClient(Protocol):
    """Protocol representing the Google Drive API client service resource."""

    def files(self) -> GoogleDriveFilesResource:
        ...
