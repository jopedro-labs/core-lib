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
    mock_drive.files().get().execute.return_value = {
        "id": "folder-123",
        "mimeType": "application/vnd.google-apps.folder",
    }
    assert service.verify_folder_access("folder-123") is True


def test_verify_folder_access_returns_false_for_non_folder(service, mock_drive):
    mock_drive.files().get().execute.return_value = {
        "id": "file-id",
        "mimeType": "text/plain",
    }
    assert service.verify_folder_access("folder-123") is False


def test_verify_folder_access_returns_false_on_exception(service, mock_drive):
    mock_drive.files().get().execute.side_effect = Exception("API error")
    assert service.verify_folder_access("folder-123") is False


def test_file_exists_returns_true_when_found(service, mock_drive):
    mock_drive.files().list().execute.return_value = {"files": [{"id": "file-id"}]}
    assert service.file_exists("report.csv") is True


def test_file_exists_returns_false_when_not_found(service, mock_drive):
    mock_drive.files().list().execute.return_value = {"files": []}
    assert service.file_exists("report.csv") is False


def test_list_files_returns_list(service, mock_drive):
    mock_drive.files().list().execute.return_value = {
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
    mock_drive.files().create().execute.return_value = {"id": "new-file-id"}
    result = service.upload_file(f)
    assert result == "new-file-id"


def test_backup_file_returns_true_on_success(service, mock_drive, tmp_path):
    f = tmp_path / "backup.csv"
    f.write_text("data")
    mock_drive.files().list().execute.return_value = {"files": []}
    mock_drive.files().create().execute.return_value = {"id": "backup-id"}
    assert service.backup_file(f) is True


def test_download_file_returns_false_when_not_found(service, mock_drive, tmp_path):
    mock_drive.files().list().execute.return_value = {"files": []}
    assert service.download_file("missing.csv", tmp_path / "out.csv") is False


def test_sync_files_push(service, mock_drive, tmp_path):
    f = tmp_path / "file.csv"
    f.write_text("data")
    mock_drive.files().list().execute.return_value = {"files": []}
    mock_drive.files().create().execute.return_value = {"id": "sync-id"}
    results = service.sync_files([f], direction="push")
    assert results[f.name] is True


def test_sync_files_invalid_direction(service, mock_drive, tmp_path):
    f = tmp_path / "file.csv"
    f.write_text("data")
    results = service.sync_files([f], direction="sideways")
    assert results[f.name] is False
