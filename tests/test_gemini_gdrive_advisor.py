"""Unit tests for scripts/gemini_gdrive_advisor.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.gemini_gdrive_advisor import (
    build_markdown_report,
    query_gemini,
    resolve_impact_level,
    scan_local_gdrive_usage,
    write_github_output,
)


def test_resolve_impact_level_authority_ceiling() -> None:
    """Validates the strict authority ceiling rules:
    - LOW baseline can NEVER be escalated to HIGH, but may be upgraded to MEDIUM.
    - MEDIUM baseline cannot jump to HIGH (remains MEDIUM or downgrades to LOW).
    - HIGH baseline can stay HIGH or downgrade to MEDIUM/LOW.
    """
    # Baseline LOW: ceiling is MEDIUM, cannot jump to HIGH
    assert resolve_impact_level("LOW", "LOW") == "LOW"
    assert resolve_impact_level("LOW", "MEDIUM") == "MEDIUM"
    assert resolve_impact_level("LOW", "HIGH") == "LOW"
    assert resolve_impact_level("LOW", "UNKNOWN") == "LOW"

    # Baseline MEDIUM: ceiling is MEDIUM
    assert resolve_impact_level("MEDIUM", "LOW") == "LOW"
    assert resolve_impact_level("MEDIUM", "MEDIUM") == "MEDIUM"
    assert resolve_impact_level("MEDIUM", "HIGH") == "MEDIUM"

    # Baseline HIGH: can stay HIGH or downgrade
    assert resolve_impact_level("HIGH", "HIGH") == "HIGH"
    assert resolve_impact_level("HIGH", "MEDIUM") == "MEDIUM"
    assert resolve_impact_level("HIGH", "LOW") == "LOW"
    assert resolve_impact_level("HIGH", "INVALID") == "HIGH"


def test_scan_local_gdrive_usage() -> None:
    methods = scan_local_gdrive_usage()
    assert isinstance(methods, list)
    assert len(methods) > 0
    assert any("files()" in m for m in methods)


def test_scan_local_gdrive_usage_missing_dir(tmp_path) -> None:
    with patch("scripts.gemini_gdrive_advisor.Path.exists", return_value=False):
        methods = scan_local_gdrive_usage()
        assert len(methods) > 0


def test_build_markdown_report() -> None:
    report = build_markdown_report(
        prev_rev="100",
        curr_rev="101",
        impact_level="LOW",
        summary="Minor doc change",
        analysis_status="ok",
        diff_markdown="No changes",
        ai_evaluation="All good",
        run_id="999",
        model_name="gemini-2.5-flash",
    )
    assert "Google Drive API Revision Changed: `100` ➔ `101`" in report
    assert "Impact Level**: `LOW`" in report
    assert "Full AI Analysis (gemini-2.5-flash)" in report
    assert "Run #999" in report


def test_build_markdown_report_fallback() -> None:
    report = build_markdown_report(
        prev_rev="100",
        curr_rev="101",
        impact_level="MEDIUM",
        summary="Changed schema",
        analysis_status="fallback_diff_only",
        diff_markdown="Schema changed",
        ai_evaluation="Review needed",
        run_id="123",
        model_name="gemini-2.5-flash",
    )
    assert "Fallback (Deterministic Diff Only)" in report


def test_write_github_output(tmp_path, monkeypatch) -> None:
    out_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    write_github_output("status", "success")
    content = out_file.read_text(encoding="utf-8")
    assert "status<<" in content
    assert "success" in content


def test_query_gemini_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable is not configured"):
        query_gemini({}, [], "100", "101")


def test_query_gemini_success(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    mock_client = MagicMock()
    mock_model_response = MagicMock()
    mock_model_response.text = json.dumps({
        "impact_level": "LOW",
        "summary": "Non-breaking revision update",
        "codebase_impact_analysis": "No active methods affected.",
        "action_checklist": ["Run tests"],
    })
    mock_client.models.generate_content.return_value = mock_model_response

    with patch("google.genai.Client", return_value=mock_client):
        impact, summary, md_eval = query_gemini(
            diff_data={"impact_baseline": "LOW"},
            local_methods=["files().get"],
            prev_rev="100",
            curr_rev="101",
        )
        assert impact == "LOW"
        assert summary == "Non-breaking revision update"
        assert "No active methods affected." in md_eval
        assert "- [ ] Run tests" in md_eval


def test_main_fallback_diff_only(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies main() execution under fallback conditions (no API key)."""
    from pathlib import Path
    from scripts.gemini_gdrive_advisor import main

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    out_file: Path = Path(str(tmp_path)) / "github_output.txt"
    report_file: Path = Path(str(tmp_path)) / "reports" / "gdrive_revision_analysis.md"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    with (
        patch("scripts.gemini_gdrive_advisor.REPORT_PATH", report_file),
        patch("scripts.gemini_gdrive_advisor.generate_diff_summary", return_value={"impact_baseline": "LOW"}),
    ):
        main()

    assert report_file.exists()
    content: str = report_file.read_text(encoding="utf-8")
    assert "Fallback (Deterministic Diff Only)" in content

    output_text: str = out_file.read_text(encoding="utf-8")
    assert "impact_level" in output_text
    assert "fallback_diff_only" in output_text
    assert "summary" in output_text
    assert "report_file" in output_text


def test_main_successful_enrichment(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies main() execution when Gemini enrichment succeeds."""
    from pathlib import Path
    from scripts.gemini_gdrive_advisor import main

    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")
    out_file: Path = Path(str(tmp_path)) / "github_output.txt"
    report_file: Path = Path(str(tmp_path)) / "reports" / "gdrive_revision_analysis.md"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

    mock_enrichment = ("MEDIUM", "Added optional query flag for drive list", "Analysis details")

    with (
        patch("scripts.gemini_gdrive_advisor.REPORT_PATH", report_file),
        patch("scripts.gemini_gdrive_advisor.generate_diff_summary", return_value={"impact_baseline": "LOW"}),
        patch("scripts.gemini_gdrive_advisor.query_gemini", return_value=mock_enrichment),
    ):
        main()

    assert report_file.exists()
    content: str = report_file.read_text(encoding="utf-8")
    assert "Full AI Analysis" in content
    assert "Impact Level**: `MEDIUM`" in report_file.read_text(encoding="utf-8")

    output_text: str = out_file.read_text(encoding="utf-8")
    assert "impact_level" in output_text
    assert "ok" in output_text
    assert "Added optional query flag" in output_text
