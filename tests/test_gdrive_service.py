from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core_lib.gdrive.gdrive_service import GDriveService


@pytest.fixture
def service(tmp_path):
    return GDriveService(folder_id="folder-123")


@pytest.fixture
def mock_drive(service):
    mock_api = MagicMock()
    service._service = mock_api
    return mock_api


def test_raises_when_credentials_file_missing(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        GDriveService(credentials_path=tmp_path / "missing.json")


def test_uses_env_var_for_folder_id(monkeypatch) -> None:
    monkeypatch.setenv("GDRIVE_DATA_FOLDER_ID", "env-folder-id")
    svc = GDriveService()
    assert svc.folder_id == "env-folder-id"


def test_folder_id_param_takes_precedence_over_env(monkeypatch) -> None:
    monkeypatch.setenv("GDRIVE_DATA_FOLDER_ID", "env-folder-id")
    svc = GDriveService(folder_id="explicit-id")
    assert svc.folder_id == "explicit-id"


def test_verify_folder_access_returns_true_for_valid_folder(service, mock_drive) -> None:
    files_mock = mock_drive.files.return_value
    files_mock.get().execute.return_value = {
        "id": "folder-123",
        "mimeType": "application/vnd.google-apps.folder",
    }
    assert service.verify_folder_access("folder-123") is True


def test_verify_folder_access_returns_false_for_non_folder(service, mock_drive) -> None:
    files_mock = mock_drive.files.return_value
    files_mock.get().execute.return_value = {
        "id": "file-id",
        "mimeType": "text/plain",
    }
    assert service.verify_folder_access("folder-123") is False


def test_verify_folder_access_returns_false_on_exception(service, mock_drive) -> None:
    files_mock = mock_drive.files.return_value
    files_mock.get().execute.side_effect = Exception("API error")
    assert service.verify_folder_access("folder-123") is False


def test_file_exists_returns_true_when_found(service, mock_drive) -> None:
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": [{"id": "file-id"}]}
    assert service.file_exists("report.csv") is True


def test_file_exists_returns_false_when_not_found(service, mock_drive) -> None:
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    assert service.file_exists("report.csv") is False


def test_list_files_returns_list(service, mock_drive) -> None:
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {
        "files": [{"id": "1", "name": "a.csv"}, {"id": "2", "name": "b.csv"}]
    }
    result = service.list_files()
    assert len(result) == 2
    assert result[0]["name"] == "a.csv"


def test_upload_file_returns_none_when_file_missing(service) -> None:
    assert service.upload_file("/tmp/__nonexistent__.csv") is None


def test_upload_file_returns_file_id_on_success(service, mock_drive, tmp_path) -> None:
    f = tmp_path / "data.csv"
    f.write_text("a,b,c")
    files_mock = mock_drive.files.return_value
    files_mock.create().execute.return_value = {"id": "new-file-id"}
    result = service.upload_file(f)
    assert result == "new-file-id"


def test_backup_file_returns_true_on_success(service, mock_drive, tmp_path) -> None:
    f = tmp_path / "backup.csv"
    f.write_text("data")
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    files_mock.create().execute.return_value = {"id": "backup-id"}
    assert service.backup_file(f) is True


def test_download_file_returns_false_when_not_found(service, mock_drive, tmp_path) -> None:
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    assert service.download_file("missing.csv", tmp_path / "out.csv") is False


def test_sync_files_push(service, mock_drive, tmp_path) -> None:
    f = tmp_path / "file.csv"
    f.write_text("data")
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    files_mock.create().execute.return_value = {"id": "sync-id"}
    results = service.sync_files([f], direction="push")
    assert results[f.name] is True


def test_sync_files_invalid_direction(service, mock_drive, tmp_path) -> None:
    f = tmp_path / "file.csv"
    f.write_text("data")
    results = service.sync_files([f], direction="sideways")
    assert results[f.name] is False


def test_file_exists_query_string_format(service, mock_drive) -> None:
    """Kills mutants that modify query syntax or trashed flag."""
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    service.file_exists("test'file.txt", folder_id="folder-999")

    called_kwargs = files_mock.list.call_args[1]
    expected_query = r"name = 'test\'file.txt' and trashed = false and 'folder-999' in parents"
    assert called_kwargs["q"] == expected_query


def test_upload_file_overwrite_branch_updates_existing(service, mock_drive, tmp_path) -> None:
    """Validates the overwrite path where file already exists."""
    f = tmp_path / "existing.txt"
    f.write_text("content")

    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": [{"id": "remote-file-id"}]}
    # Fix: use .return_value instead of invoking .update() during setup
    files_mock.update.return_value.execute.return_value = {"id": "remote-file-id"}

    res = service.upload_file(f, overwrite=True)

    assert res == "remote-file-id"
    files_mock.update.assert_called_once()
    files_mock.create.assert_not_called()


def test_download_file_chunk_loop_and_write(service, mock_drive, tmp_path) -> None:
    """Ensures chunk iterations and byte writing are executed."""
    target_out = tmp_path / "downloaded.bin"
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": [{"id": "remote-id"}]}

    with patch("core_lib.gdrive.gdrive_service.MediaIoBaseDownload") as mock_downloader_cls:
        downloader_inst = MagicMock()
        downloader_inst.next_chunk.side_effect = [(None, False), (None, True)]
        mock_downloader_cls.return_value = downloader_inst

        success = service.download_file("file.bin", target_out)

        assert success is True
        assert target_out.exists()


def test_sync_files_pull_success(service, mock_drive, tmp_path) -> None:
    """Covers the pull branch of sync_files."""
    target_file = tmp_path / "pulled.csv"
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": [{"id": "id-123"}]}

    with patch("core_lib.gdrive.gdrive_service.MediaIoBaseDownload") as mock_downloader_cls:
        downloader_inst = MagicMock()
        downloader_inst.next_chunk.return_value = (None, True)
        mock_downloader_cls.return_value = downloader_inst

        results = service.sync_files([target_file], direction="pull")

    assert results[target_file.name] is True


def test_get_service_handles_exception_gracefully(tmp_path) -> None:
    """Covers _get_service error path when credentials resolution throws."""
    svc = GDriveService()
    with patch("core_lib.gdrive.gdrive_service.get_google_service_credentials", side_effect=RuntimeError("Auth failed")):
        assert svc._get_service() is None
        assert svc.verify_folder_access() is False
def test_operations_return_falsy_when_service_is_none(tmp_path) -> None:
    """Kills mutants and covers guard clauses when _get_service returns None."""
    from core_lib.gdrive.gdrive_service import GDriveService
    svc = GDriveService(folder_id=None)
    with patch.object(svc, "_get_service", return_value=None):
        assert svc.verify_folder_access() is False
        assert svc.file_exists("test.csv") is False
        assert svc.list_files() == []
        assert svc.upload_file(tmp_path / "any.txt") is None
        assert svc.download_file("test.csv", tmp_path / "out.txt") is False


def test_service_operations_handle_api_exceptions(service, mock_drive, tmp_path) -> None:
    """Ensures robust exception handling across all CRUD operations."""
    files_mock = mock_drive.files.return_value
    f = tmp_path / "upload.bin"
    f.write_text("dummy")

    # file_exists exception path
    files_mock.list.side_effect = RuntimeError("API down")
    assert service.file_exists("upload.bin") is False

    # list_files exception path
    assert service.list_files() == []

    # upload_file exception path
    files_mock.create.side_effect = RuntimeError("Write forbidden")
    assert service.upload_file(f) is None

    # download_file exception path
    files_mock.list.side_effect = None
    files_mock.list().execute.return_value = {"files": [{"id": "id-123"}]}
    files_mock.get_media.side_effect = RuntimeError("Stream broken")
    assert service.download_file("upload.bin", tmp_path / "dest.bin") is False


def test_upload_file_parent_folder_metadata_injection(service, mock_drive, tmp_path) -> None:
    """Anti-mutation check for parents folder metadata."""
    f = tmp_path / "report.pdf"
    f.write_text("data")
    files_mock = mock_drive.files.return_value
    files_mock.create().execute.return_value = {"id": "created-id"}

    service.upload_file(f, folder_id="custom-folder-777")
    create_kwargs = files_mock.create.call_args[1]
    assert create_kwargs["body"] == {
        "name": "report.pdf",
        "parents": ["custom-folder-777"],
    }

def test_gdrive_service_additional_methods(tmp_path) -> None:
    from core_lib.gdrive.gdrive_service import GDriveService
    svc = GDriveService(folder_id="f123")
    
    # 1. verify folder access when service is None and when target is None
    with patch.object(svc, "_get_service", return_value=None):
        assert svc.verify_folder_access() is False
    
    svc_no_folder = GDriveService(folder_id=None)
    with patch.object(svc_no_folder, "_get_service", return_value=MagicMock()):
        assert svc_no_folder.verify_folder_access(folder_id=None) is False
        
    # 2. get_latest_file_id
    with patch.object(svc, "_get_service", return_value=None):
        assert svc.get_latest_file_id() is None
        
    mock_drive = MagicMock()
    with patch.object(svc, "_get_service", return_value=mock_drive):
        # empty files
        mock_drive.files().list().execute.return_value = {"files": []}
        assert svc.get_latest_file_id() is None
        
        # files found
        mock_drive.files().list().execute.return_value = {
            "files": [{"id": "id-latest", "name": "finances-2026.db", "modifiedTime": "2026-01-01"}]
        }
        assert svc.get_latest_file_id() == "id-latest"
        
        # exception
        mock_drive.files().list.side_effect = RuntimeError("API error")
        assert svc.get_latest_file_id() is None

    # 3. download_latest_file
    with patch.object(svc, "get_latest_file_id", return_value=None):
        assert svc.download_latest_file(tmp_path / "out.db") is False
        
    with patch.object(svc, "get_latest_file_id", return_value="id-123"):
        with patch.object(svc, "_get_service", return_value=None):
            assert svc.download_latest_file(tmp_path / "out.db") is False
            
        mock_drive = MagicMock()
        mock_drive.files.side_effect = None
        mock_drive.files().get_media.side_effect = RuntimeError("Media error")
        with patch.object(svc, "_get_service", return_value=mock_drive):
            assert svc.download_latest_file(tmp_path / "out.db") is False

    # 4. get_file_modified_time
    with patch.object(svc, "_get_service", return_value=None):
        assert svc.get_file_modified_time("finances.db") is None
        
    mock_drive = MagicMock()
    with patch.object(svc, "_get_service", return_value=mock_drive):
        # empty
        mock_drive.files().list().execute.return_value = {"files": []}
        assert svc.get_file_modified_time("finances.db") is None
        
        # found
        mock_drive.files().list().execute.return_value = {"files": [{"modifiedTime": "2026-11-19T20:00:00Z"}]}
        assert svc.get_file_modified_time("finances.db") == "2026-11-19T20:00:00Z"
        
        # exception
        mock_drive.files().list.side_effect = RuntimeError("Lookup failed")
        assert svc.get_file_modified_time("finances.db") is None


def test_get_service_warning_when_creds_none(tmp_path: Path) -> None:
    svc = GDriveService()
    with patch("core_lib.gdrive.gdrive_service.get_google_service_credentials", return_value=None):
        assert svc._get_service() is None


def test_get_service_build_success(tmp_path: Path) -> None:
    svc = GDriveService()
    mock_creds = MagicMock()
    with patch(
        "core_lib.gdrive.gdrive_service.get_google_service_credentials", return_value=mock_creds
    ):
        with patch("core_lib.gdrive.gdrive_service.build") as mock_build:
            mock_client = MagicMock()
            mock_build.return_value = mock_client
            assert svc._get_service() == mock_client
            mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds)


def test_list_files_root_without_folder_id(service: GDriveService, mock_drive: MagicMock) -> None:
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    service.folder_id = None
    result = service.list_files(folder_id=None)
    assert result == []
    called_kwargs = files_mock.list.call_args[1]
    assert called_kwargs["q"] == "trashed = false"


def test_upload_file_returns_none_when_service_is_none(tmp_path: Path) -> None:
    f = tmp_path / "test.csv"
    f.write_text("dummy")
    svc = GDriveService()
    with patch.object(svc, "_get_service", return_value=None):
        assert svc.upload_file(f) is None


def test_download_latest_file_success_atomic_swap(
    service: GDriveService, mock_drive: MagicMock, tmp_path: Path
) -> None:
    target_out = tmp_path / "latest.db"
    files_mock = mock_drive.files.return_value

    with patch.object(service, "get_latest_file_id", return_value="id-latest-999"):
        with patch("core_lib.gdrive.gdrive_service.MediaIoBaseDownload") as mock_downloader_cls:
            downloader_mock = MagicMock()
            downloader_mock.next_chunk.return_value = (None, True)
            mock_downloader_cls.return_value = downloader_mock

            assert service.download_latest_file(target_out) is True
            assert target_out.exists()
            files_mock.get_media.assert_called_once_with(fileId="id-latest-999")
            # Verify temp files cleaned up
            temp_files = list(tmp_path.glob("*.tmp.*"))
            assert len(temp_files) == 0


def test_download_latest_file_cleanup_on_exception(
    service: GDriveService, mock_drive: MagicMock, tmp_path: Path
) -> None:
    target_out = tmp_path / "latest_failed.db"

    with patch.object(service, "get_latest_file_id", return_value="id-latest-999"):
        with patch("core_lib.gdrive.gdrive_service.MediaIoBaseDownload") as mock_downloader_cls:
            downloader_mock = MagicMock()
            downloader_mock.next_chunk.side_effect = RuntimeError("Network stream error")
            mock_downloader_cls.return_value = downloader_mock

            assert service.download_latest_file(target_out) is False
            assert not target_out.exists()
            # Verify temp file cleaned up in finally block
            temp_files = list(tmp_path.glob("*.tmp.*"))
            assert len(temp_files) == 0


def test_download_file_cleanup_on_exception(
    service: GDriveService, mock_drive: MagicMock, tmp_path: Path
) -> None:
    target_out = tmp_path / "failed.db"
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": [{"id": "id-download-123"}]}

    with patch("core_lib.gdrive.gdrive_service.MediaIoBaseDownload") as mock_downloader_cls:
        downloader_mock = MagicMock()
        downloader_mock.next_chunk.side_effect = RuntimeError("Download interrupted")
        mock_downloader_cls.return_value = downloader_mock

        assert service.download_file("failed.db", target_out) is False
        assert not target_out.exists()
        temp_files = list(tmp_path.glob("*.tmp.*"))
        assert len(temp_files) == 0

