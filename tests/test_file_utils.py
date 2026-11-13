import pytest

from core_lib.file_utils import load_file_content


def test_returns_content_for_existing_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world", encoding="utf-8")
    assert load_file_content(f) == "hello world"


def test_returns_empty_string_for_nonexistent_file():
    assert load_file_content("/tmp/__nonexistent_core_lib_test__.txt") == ""


def test_returns_empty_string_for_directory(tmp_path):
    assert load_file_content(tmp_path) == ""


def test_accepts_string_path(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("ok", encoding="utf-8")
    assert load_file_content(str(f)) == "ok"


def test_returns_empty_string_on_read_error(tmp_path, monkeypatch):
    f = tmp_path / "locked.txt"
    f.write_text("data", encoding="utf-8")

    def boom(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("pathlib.Path.read_text", boom)
    assert load_file_content(f) == ""
