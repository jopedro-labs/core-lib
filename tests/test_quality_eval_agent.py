"""Unit tests for scripts/quality_eval_agent.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.quality_eval_agent import (
    evaluate_with_gemini,
    gather_codebase_context,
    load_quality_specification,
    main,
    run_mypy,
    run_pytest,
    run_ruff,
)


def test_load_quality_specification_success(tmp_path: Path) -> None:
    spec_file: Path = tmp_path / "QUALITY_AGENT.MD"
    spec_file.write_text("# Test Spec Content", encoding="utf-8")

    content: str = load_quality_specification([spec_file])
    assert content == "# Test Spec Content"


def test_load_quality_specification_missing(tmp_path: Path) -> None:
    non_existent: Path = tmp_path / "NON_EXISTENT.MD"
    with pytest.raises(FileNotFoundError, match="Quality specification file not found"):
        load_quality_specification([non_existent])


def test_run_pytest_executes() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pytest"],
            returncode=0,
            stdout="collected 10 items\n10 passed",
            stderr="",
        )
        code: int
        output: str
        code, output = run_pytest()
        assert code == 0
        assert "10 passed" in output


def test_run_ruff_executes() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "ruff", "check", "."],
            returncode=0,
            stdout="All checks passed!",
            stderr="",
        )
        code: int
        output: str
        code, output = run_ruff()
        assert code == 0
        assert "All checks passed!" in output


def test_run_mypy_executes() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "mypy"],
            returncode=0,
            stdout="Success: no issues found",
            stderr="",
        )
        code: int
        output: str
        code, output = run_mypy()
        assert code == 0
        assert "Success: no issues found" in output


def test_gather_codebase_context() -> None:
    context: str = gather_codebase_context()
    assert isinstance(context, str)
    assert len(context) > 0
    assert "core_lib" in context
    file_headers: list[str] = [
        line for line in context.splitlines() if line.startswith("=== FILE: ")
    ]
    for header in file_headers:
        assert "/.venv/" not in header
        assert "/venv/" not in header
        assert "/__pycache__/" not in header
        assert "/.git/" not in header
        assert "/dist/" not in header
        assert "/build/" not in header
        assert "/reports/" not in header


def test_evaluate_with_gemini_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable is not set."):
        evaluate_with_gemini(
            quality_spec="spec",
            codebase_context="context",
            test_output="test output",
            ruff_output="ruff output",
            mypy_output="mypy output",
        )


def test_evaluate_with_gemini_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    mock_response: MagicMock = MagicMock()
    mock_response.text = "# Quality Evaluation Report\nAll pillars verified."

    mock_client: MagicMock = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client) as mock_client_cls:
        result: str = evaluate_with_gemini(
            quality_spec="Spec: 5 Pillars and Criteria",
            codebase_context="sample context",
            test_output="all tests passed",
            ruff_output="all lint passed",
            mypy_output="all types passed",
        )
        assert "All pillars verified." in result
        mock_client_cls.assert_called_once_with(api_key="fake-key")

        prompt_passed: str = mock_client.models.generate_content.call_args[1]["contents"]
        assert "Spec: 5 Pillars and Criteria" in prompt_passed
        assert "all tests passed" in prompt_passed
        assert "all lint passed" in prompt_passed
        assert "all types passed" in prompt_passed
        assert "sample context" in prompt_passed


def test_main_workflow_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    fake_spec: Path = tmp_path / "QUALITY_AGENT.MD"
    fake_spec.write_text("# Test Spec", encoding="utf-8")

    with (
        patch("scripts.quality_eval_agent.run_pytest", return_value=(0, "Tests OK")),
        patch("scripts.quality_eval_agent.run_ruff", return_value=(0, "Ruff OK")),
        patch("scripts.quality_eval_agent.run_mypy", return_value=(0, "Mypy OK")),
        patch("scripts.quality_eval_agent.gather_codebase_context", return_value="Context OK"),
        patch("scripts.quality_eval_agent.evaluate_with_gemini", return_value="# Report"),
    ):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
        report_file: Path = tmp_path / "reports" / "quality_agent_report.md"
        assert report_file.exists()
        assert report_file.read_text(encoding="utf-8") == "# Report"


def test_main_workflow_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    fake_spec: Path = tmp_path / "QUALITY_AGENT.MD"
    fake_spec.write_text("# Test Spec", encoding="utf-8")

    with (
        patch("scripts.quality_eval_agent.run_pytest", return_value=(2, "Tests Failed")),
        patch("scripts.quality_eval_agent.run_ruff", return_value=(0, "Ruff OK")),
        patch("scripts.quality_eval_agent.run_mypy", return_value=(0, "Mypy OK")),
        patch("scripts.quality_eval_agent.gather_codebase_context", return_value="Context OK"),
        patch("scripts.quality_eval_agent.evaluate_with_gemini", return_value="# Report Fail"),
    ):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
        report_file: Path = tmp_path / "reports" / "quality_agent_report.md"
        assert report_file.exists()
        assert report_file.read_text(encoding="utf-8") == "# Report Fail"


def test_main_workflow_missing_api_key_generates_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    fake_spec: Path = tmp_path / "QUALITY_AGENT.MD"
    fake_spec.write_text("# Test Spec", encoding="utf-8")

    with (
        patch("scripts.quality_eval_agent.run_pytest", return_value=(0, "Tests Output")),
        patch("scripts.quality_eval_agent.run_ruff", return_value=(0, "Ruff Output")),
        patch("scripts.quality_eval_agent.run_mypy", return_value=(0, "Mypy Output")),
        patch("scripts.quality_eval_agent.gather_codebase_context", return_value="Context OK"),
    ):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        report_file: Path = tmp_path / "reports" / "quality_agent_report.md"
        assert report_file.exists()
        content: str = report_file.read_text(encoding="utf-8")
        assert "Code Quality & Test Gap Evaluation Report (Fallback)" in content
        assert "Tests Output" in content
        assert "Ruff Output" in content
        assert "Mypy Output" in content
