"""Unit tests for scripts/validate_audit_sync.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validate_audit_sync import (
    EXPECTED_SECTIONS,
    get_changed_files,
    main,
    validate_change_sync,
    validate_structure,
)


SAMPLE_VALID_AUDIT: str = """# Repository Audit & Hygiene Tracking

This document provides a factual, read-only comprehensive audit of the `core-lib` repository.

## 1. Missing Local Files & Environment Setup
- [x] **Missing Environment Variables Configuration**:
  - Sample details.
- [ ] **Optional Open Item**:
  - Open details.

## 2. Bugs & Code Fragilities
- [x] **Fragile Dynamic Attribute Exports**:
  - Handled properly.

## 3. Test Coverage Gaps
- [x] **Uncovered Error Scenarios in GDrive**:
  - Fully covered.
"""


def test_validate_structure_file_missing(tmp_path: Path) -> None:
    non_existent: Path = tmp_path / "NON_EXISTENT.md"
    is_valid, completed, opened = validate_structure(non_existent)
    assert is_valid is False
    assert completed == 0
    assert opened == 0


def test_validate_structure_valid_content(tmp_path: Path) -> None:
    audit_file: Path = tmp_path / "AUDIT.md"
    audit_file.write_text(SAMPLE_VALID_AUDIT, encoding="utf-8")

    is_valid, completed, opened = validate_structure(audit_file)
    assert is_valid is True
    assert completed == 3
    assert opened == 1


def test_validate_structure_missing_required_section(tmp_path: Path) -> None:
    audit_file: Path = tmp_path / "AUDIT.md"
    # Omit section 3
    incomplete_content: str = f"""
## 1. Missing Local Files & Environment Setup
- [x] **Task 1**: done

## 2. Bugs & Code Fragilities
- [x] **Task 2**: done
"""
    audit_file.write_text(incomplete_content, encoding="utf-8")

    is_valid, completed, opened = validate_structure(audit_file)
    assert is_valid is False
    assert completed == 0
    assert opened == 0


def test_validate_structure_malformed_checkbox(tmp_path: Path) -> None:
    audit_file: Path = tmp_path / "AUDIT.md"
    malformed_content: str = f"""{EXPECTED_SECTIONS[0]}
- [?] **Invalid Checkbox Item**: description

{EXPECTED_SECTIONS[1]}
- [x] **Valid Item**: description

{EXPECTED_SECTIONS[2]}
- [ ] **Another Item**: description
"""
    audit_file.write_text(malformed_content, encoding="utf-8")

    is_valid, _, _ = validate_structure(audit_file)
    assert is_valid is False


def test_validate_structure_no_items_detected(tmp_path: Path) -> None:
    audit_file: Path = tmp_path / "AUDIT.md"
    empty_sections: str = "\n\n".join(EXPECTED_SECTIONS)
    audit_file.write_text(empty_sections, encoding="utf-8")

    is_valid, completed, opened = validate_structure(audit_file)
    assert is_valid is False
    assert completed == 0
    assert opened == 0


def test_get_changed_files_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "diff", "--name-only"],
            returncode=0,
            stdout="core_lib/gdrive/types.py\nAUDIT.md\n",
            stderr="",
        )
        files = get_changed_files()
        assert files == ["core_lib/gdrive/types.py", "AUDIT.md"]


def test_get_changed_files_with_base_ref() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "diff", "--name-only", "origin/main"],
            returncode=0,
            stdout="scripts/validate_audit_sync.py\n",
            stderr="",
        )
        files = get_changed_files(base_ref="origin/main")
        assert files == ["scripts/validate_audit_sync.py"]
        mock_run.assert_called_once_with(
            ["git", "diff", "--name-only", "origin/main"],
            capture_output=True,
            text=True,
            check=True,
        )


def test_get_changed_files_exception_handled() -> None:
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["git"])):
        files = get_changed_files()
        assert files == []


def test_validate_change_sync_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    assert validate_change_sync(bypass=True) is True

    monkeypatch.setenv("BYPASS_AUDIT_SYNC", "1")
    assert validate_change_sync(bypass=False) is True


def test_validate_change_sync_no_changes() -> None:
    with patch("scripts.validate_audit_sync.get_changed_files", return_value=[]):
        assert validate_change_sync() is True


def test_validate_change_sync_code_changed_without_audit() -> None:
    with patch(
        "scripts.validate_audit_sync.get_changed_files",
        return_value=["core_lib/gdrive/gdrive_service.py", "README.md"],
    ):
        assert validate_change_sync() is False


def test_validate_change_sync_code_and_audit_changed() -> None:
    with patch(
        "scripts.validate_audit_sync.get_changed_files",
        return_value=["core_lib/gdrive/gdrive_service.py", "AUDIT.md"],
    ):
        assert validate_change_sync() is True


def test_validate_change_sync_non_monitored_changes_only() -> None:
    with patch(
        "scripts.validate_audit_sync.get_changed_files",
        return_value=["README.md", "docs/index.md"],
    ):
        assert validate_change_sync() is True


def test_main_cli_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit_file = tmp_path / "AUDIT.md"
    audit_file.write_text(SAMPLE_VALID_AUDIT, encoding="utf-8")

    test_args = ["validate_audit_sync.py", "--audit-file", str(audit_file)]
    monkeypatch.setattr("sys.argv", test_args)
    assert main() == 0


def test_main_cli_structure_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_file = tmp_path / "AUDIT.md"
    empty_file.write_text("invalid content", encoding="utf-8")

    test_args = ["validate_audit_sync.py", "--audit-file", str(empty_file)]
    monkeypatch.setattr("sys.argv", test_args)
    assert main() == 1


def test_main_cli_enforce_sync_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit_file = tmp_path / "AUDIT.md"
    audit_file.write_text(SAMPLE_VALID_AUDIT, encoding="utf-8")

    test_args = [
        "validate_audit_sync.py",
        "--audit-file",
        str(audit_file),
        "--enforce-sync",
    ]
    monkeypatch.setattr("sys.argv", test_args)
    with patch(
        "scripts.validate_audit_sync.get_changed_files",
        return_value=["core_lib/logger/logger.py"],
    ):
        assert main() == 1
