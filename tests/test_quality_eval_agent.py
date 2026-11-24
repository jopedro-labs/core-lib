"""Unit tests for scripts/quality_eval_agent.py."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from scripts.quality_eval_agent import (
    evaluate_with_gemini,
    gather_codebase_context,
    main,
    run_pytest,
)


def test_run_pytest_executes():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "pytest"],
            returncode=0,
            stdout="collected 10 items\n10 passed",
            stderr="",
        )
        code, output = run_pytest()
        assert code == 0
        assert "10 passed" in output


def test_gather_codebase_context():
    context = gather_codebase_context()
    assert isinstance(context, str)
    assert len(context) > 0
    # Must contain files from core_lib
    assert "core_lib" in context
    file_headers = [line for line in context.splitlines() if line.startswith("=== FILE: ")]
    for header in file_headers:
        assert "/.venv/" not in header
        assert "/venv/" not in header
        assert "/__pycache__/" not in header
        assert "/.git/" not in header


def test_evaluate_with_gemini_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        evaluate_with_gemini("context", "test output")
    assert exc.value.code == 1


def test_evaluate_with_gemini_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "# Quality Evaluation Report\nAll pillars verified."
    mock_model.generate_content.return_value = mock_response

    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
        with patch("google.generativeai.configure"):
            result = evaluate_with_gemini("sample context", "all tests passed")
            assert "All pillars verified." in result


def test_main_workflow_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    with patch("scripts.quality_eval_agent.run_pytest", return_value=(0, "Tests OK")):
        with patch("scripts.quality_eval_agent.gather_codebase_context", return_value="Context OK"):
            with patch("scripts.quality_eval_agent.evaluate_with_gemini", return_value="# Report"):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0
                report_file = tmp_path / "reports" / "validation_gap_report.md"
                assert report_file.exists()
                assert report_file.read_text(encoding="utf-8") == "# Report"


def test_main_workflow_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    with patch("scripts.quality_eval_agent.run_pytest", return_value=(2, "Tests Failed")):
        with patch("scripts.quality_eval_agent.gather_codebase_context", return_value="Context OK"):
            with patch("scripts.quality_eval_agent.evaluate_with_gemini", return_value="# Report Fail"):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 2
