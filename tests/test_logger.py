import sys
from io import StringIO

import pytest

from core_lib.logger import Logger, get_logger, logger


def test_info_outputs_to_stdout(capsys) -> None:
    logger.info("hello")
    out = capsys.readouterr().out
    assert "[INFO" in out
    assert "hello" in out


def test_success_outputs_to_stdout(capsys) -> None:
    logger.success("done")
    out = capsys.readouterr().out
    assert "SUCCESS" in out
    assert "done" in out


def test_warning_outputs_to_stdout(capsys) -> None:
    logger.warning("careful")
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "careful" in out


def test_error_outputs_to_stderr(capsys) -> None:
    logger.error("boom")
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "boom" in err


def test_error_with_exception_includes_exception(capsys) -> None:
    logger.error("bad", exception=ValueError("oops"))
    err = capsys.readouterr().err
    assert "oops" in err


def test_section_outputs_uppercased_title(capsys) -> None:
    logger.section("my section")
    out = capsys.readouterr().out
    assert "MY SECTION" in out


def test_subsection_outputs_message(capsys) -> None:
    logger.subsection("sub step")
    out = capsys.readouterr().out
    assert "sub step" in out


def test_print_outputs_message(capsys) -> None:
    logger.print("raw line")
    out = capsys.readouterr().out
    assert "raw line" in out


def test_logger_singleton_is_logger_instance() -> None:
    assert isinstance(logger, Logger)


def test_get_logger_returns_singleton() -> None:
    assert get_logger() is logger


def test_exception_delegates_to_error(capsys) -> None:
    logger.exception("failure occurred", exception=RuntimeError("disk full"))
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "failure occurred" in err
    assert "disk full" in err


def test_logger_respects_tty_colors(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    tty_logger = Logger()
    assert tty_logger._colors_enabled is True

    tty_logger.success("Color test")
    out = capsys.readouterr().out
    assert "\033[92m" in out


def test_logger_strips_colors_in_non_tty(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    headless_logger = Logger()
    assert headless_logger._colors_enabled is False

    headless_logger.success("Clean test")
    out = capsys.readouterr().out
    assert "\033[92m" not in out
    assert "[SUCCESS" in out