import sys
from io import StringIO

import pytest

from core_lib.logger import Logger, logger


def test_info_outputs_to_stdout(capsys):
    logger.info("hello")
    out = capsys.readouterr().out
    assert "[INFO" in out
    assert "hello" in out


def test_success_outputs_to_stdout(capsys):
    logger.success("done")
    out = capsys.readouterr().out
    assert "SUCCESS" in out
    assert "done" in out


def test_warning_outputs_to_stdout(capsys):
    logger.warning("careful")
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "careful" in out


def test_error_outputs_to_stderr(capsys):
    logger.error("boom")
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "boom" in err


def test_error_with_exception_includes_exception(capsys):
    logger.error("bad", exception=ValueError("oops"))
    err = capsys.readouterr().err
    assert "oops" in err


def test_section_outputs_uppercased_title(capsys):
    logger.section("my section")
    out = capsys.readouterr().out
    assert "MY SECTION" in out


def test_subsection_outputs_message(capsys):
    logger.subsection("sub step")
    out = capsys.readouterr().out
    assert "sub step" in out


def test_print_outputs_message(capsys):
    logger.print("raw line")
    out = capsys.readouterr().out
    assert "raw line" in out


def test_logger_singleton_is_logger_instance():
    assert isinstance(logger, Logger)
