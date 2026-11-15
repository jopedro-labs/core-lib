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


def test_raises_when_credentials_file_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        GDriveService(credentials_path=tmp_path / "missing.json")


def test_uses_env_var_for_folder_id(monkeypatch):
    monkeypatch.setenv("GDRIVE_DATA_FOLDER_ID", "env-folder-id")
    svc = GDriveService()
    assert svc.folder_id == "env-folder-id"


def test_folder_id_param_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("GDRIVE_DATA_FOLDER_ID", "env-folder-id")
    svc = GDriveService(folder_id="explicit-id")
    assert svc.folder_id == "explicit-id"


def test_verify_folder_access_returns_true_for_valid_folder(service, mock_drive):
    files_mock = mock_drive.files.return_value
    files_mock.get().execute.return_value = {
        "id": "folder-123",
        "mimeType": "application/vnd.google-apps.folder",
    }
    assert service.verify_folder_access("folder-123") is True


def test_verify_folder_access_returns_false_for_non_folder(service, mock_drive):
    files_mock = mock_drive.files.return_value
    files_mock.get().execute.return_value = {
        "id": "file-id",
        "mimeType": "text/plain",
    }
    assert service.verify_folder_access("folder-123") is False


def test_verify_folder_access_returns_false_on_exception(service, mock_drive):
    files_mock = mock_drive.files.return_value
    files_mock.get().execute.side_effect = Exception("API error")
    assert service.verify_folder_access("folder-123") is False


def test_file_exists_returns_true_when_found(service, mock_drive):
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": [{"id": "file-id"}]}
    assert service.file_exists("report.csv") is True


def test_file_exists_returns_false_when_not_found(service, mock_drive):
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    assert service.file_exists("report.csv") is False


def test_list_files_returns_list(service, mock_drive):
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {
        "files": [{"id": "1", "name": "a.csv"}, {"id": "2", "name": "b.csv"}]
    }
    result = service.list_files()
    assert len(result) == 2
    assert result[0]["name"] == "a.csv"


def test_upload_file_returns_none_when_file_missing(service):
    assert service.upload_file("/tmp/__nonexistent__.csv") is None


def test_upload_file_returns_file_id_on_success(service, mock_drive, tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b,c")
    files_mock = mock_drive.files.return_value
    files_mock.create().execute.return_value = {"id": "new-file-id"}
    result = service.upload_file(f)
    assert result == "new-file-id"


def test_backup_file_returns_true_on_success(service, mock_drive, tmp_path):
    f = tmp_path / "backup.csv"
    f.write_text("data")
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    files_mock.create().execute.return_value = {"id": "backup-id"}
    assert service.backup_file(f) is True


def test_download_file_returns_false_when_not_found(service, mock_drive, tmp_path):
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    assert service.download_file("missing.csv", tmp_path / "out.csv") is False


def test_sync_files_push(service, mock_drive, tmp_path):
    f = tmp_path / "file.csv"
    f.write_text("data")
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    files_mock.create().execute.return_value = {"id": "sync-id"}
    results = service.sync_files([f], direction="push")
    assert results[f.name] is True


def test_sync_files_invalid_direction(service, mock_drive, tmp_path):
    f = tmp_path / "file.csv"
    f.write_text("data")
    results = service.sync_files([f], direction="sideways")
    assert results[f.name] is False


def test_file_exists_query_string_format(service, mock_drive):
    """Kills mutants that modify query syntax or trashed flag."""
    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": []}
    service.file_exists("test'file.txt", folder_id="folder-999")

    called_kwargs = files_mock.list.call_args[1]
    expected_query = r"name = 'test\'file.txt' and trashed = false and 'folder-999' in parents"
    assert called_kwargs["q"] == expected_query


def test_upload_file_overwrite_branch_updates_existing(service, mock_drive, tmp_path):
    """Validates the overwrite path where file already exists."""
    f = tmp_path / "existing.txt"
    f.write_text("content")

    files_mock = mock_drive.files.return_value
    files_mock.list().execute.return_value = {"files": [{"id": "remote-file-id"}]}
    # Correção: usar .return_value em vez de chamar .update() na configuração
    files_mock.update.return_value.execute.return_value = {"id": "remote-file-id"}

    res = service.upload_file(f, overwrite=True)

    assert res == "remote-file-id"
    files_mock.update.assert_called_once()
    files_mock.create.assert_not_called()


def test_download_file_chunk_loop_and_write(service, mock_drive, tmp_path):
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


def test_sync_files_pull_success(service, mock_drive, tmp_path):
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


def test_get_service_handles_exception_gracefully(tmp_path):
    """Covers _get_service error path when credentials resolution throws."""
    svc = GDriveService()
    with patch("core_lib.gdrive.gdrive_service.get_google_service_credentials", side_effect=RuntimeError("Auth failed")):
        assert svc._get_service() is None
        assert svc.verify_folder_access() is False