"""Type definitions and schemas for Google Drive operations."""

from __future__ import annotations

from typing import Protocol, TypedDict, TypeVar

T_co = TypeVar("T_co", covariant=True)


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


class GoogleDriveExecutable(Protocol[T_co]):
    """Protocol for executable API requests in google-api-python-client."""

    def execute(self) -> T_co:
        ...


class GoogleDriveFilesResource(Protocol):
    """Protocol for Google Drive API files resource."""

    def get(self, **kwargs: object) -> GoogleDriveExecutable[DriveFileResource]:
        ...

    def list(self, **kwargs: object) -> GoogleDriveExecutable[DriveFileListResponse]:
        ...

    def create(self, **kwargs: object) -> GoogleDriveExecutable[DriveFileResource]:
        ...

    def update(self, **kwargs: object) -> GoogleDriveExecutable[DriveFileResource]:
        ...

    def get_media(self, **kwargs: object) -> GoogleDriveExecutable[object]:
        ...


class GoogleDriveClient(Protocol):
    """Protocol representing the Google Drive API client service resource."""

    def files(self) -> GoogleDriveFilesResource:
        ...
