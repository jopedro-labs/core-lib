"""Autonomous evaluation agent script powered by Gemini for test and quality gap analysis.

This module inspects repository source code and test files, executes the test suite
alongside static analysis tools (ruff, mypy), evaluates coverage and quality against
the specification defined in QUALITY_AGENT.MD, and generates a structured report
using the Google GenAI SDK.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from core_lib.logger import logger

load_dotenv()

DEFAULT_MODEL: str = "gemini-3.8-flash"
REPORT_PATH: Path = Path("reports/quality_agent_report.md")
QUALITY_SPEC_PATHS: list[Path] = [
    Path("QUALITY_AGENT.MD"),
    Path(".gemini/QUALITY_AGENT.MD"),
]


def load_quality_specification(paths: list[Path] | None = None) -> str:
    """Load the quality specification markdown file acting as the single source of truth.

    Searches across provided candidate paths. Raises FileNotFoundError if none exist.
    """
    candidate_paths: list[Path] = paths if paths is not None else QUALITY_SPEC_PATHS
    for path in candidate_paths:
        if path.is_file():
            logger.info(f"Loaded quality specification from {path}")
            return path.read_text(encoding="utf-8")

    searched: str = ", ".join(str(p) for p in candidate_paths)
    raise FileNotFoundError(
        f"Quality specification file not found. Looked in: {searched}"
    )


def run_pytest() -> tuple[int, str]:
    """Execute the pytest test suite via current python interpreter and capture output."""
    logger.info("Running test suite via pytest...")
    cmd: list[str] = [sys.executable, "-m", "pytest"]
    if importlib.util.find_spec("pytest_cov") is not None:
        cmd.extend(["--cov=core_lib", "--cov-report=term-missing"])
    cmd.append("-v")

    result: subprocess.CompletedProcess[str] = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    combined_output: str = result.stdout + ("\n" + result.stderr if result.stderr else "")
    return result.returncode, combined_output


def run_ruff() -> tuple[int, str]:
    """Execute ruff linter checks via current python interpreter and capture output."""
    logger.info("Running static lint checks via ruff...")
    cmd: list[str] = [sys.executable, "-m", "ruff", "check", "."]
    result: subprocess.CompletedProcess[str] = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    combined_output: str = result.stdout + ("\n" + result.stderr if result.stderr else "")
    return result.returncode, combined_output


def run_mypy() -> tuple[int, str]:
    """Execute static type checks via mypy and capture output."""
    logger.info("Running static type checks via mypy...")
    cmd: list[str] = [sys.executable, "-m", "mypy"]
    result: subprocess.CompletedProcess[str] = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    combined_output: str = result.stdout + ("\n" + result.stderr if result.stderr else "")
    return result.returncode, combined_output


def gather_codebase_context() -> str:
    """Collect repository context without artificial truncation, excluding cache/build dirs."""
    context_parts: list[str] = []
    ignored_dirs: set[str] = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "reports",
    }

    allowed_extensions: tuple[str, ...] = (
        ".py",
        ".yml",
        ".yaml",
        ".md",
        ".toml",
        ".json",
    )

    for root, dirs, files in os.walk("."):
        dirs[:] = [
            d
            for d in dirs
            if d not in ignored_dirs
            and not d.endswith(".egg-info")
            and (root != "." or not d.startswith("."))
        ]
        for file in files:
            if file.endswith(allowed_extensions):
                filepath: str = os.path.join(root, file)
                try:
                    with open(filepath, encoding="utf-8") as f:
                        content: str = f.read()
                        context_parts.append(f"=== FILE: {filepath} ===\n{content}\n")
                except Exception as exc:
                    logger.warning(f"Could not read {filepath}: {exc}")

    return "\n".join(context_parts)


def evaluate_with_gemini(
    quality_spec: str,
    codebase_context: str,
    test_output: str,
    ruff_output: str,
    mypy_output: str,
) -> str:
    """Invoke Gemini API to analyze gaps based on QUALITY_AGENT.MD as the single source of truth."""
    api_key: str | None = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    model_name: str = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    logger.info(f"Initializing Gemini client [{model_name}] for evaluation...")
    client: genai.Client = genai.Client(api_key=api_key)

    prompt: str = f"""
You are an expert Software Quality Assurance Agent auditing the 'core-lib' repository.
Your audit is strictly governed by the following Quality Specification (`QUALITY_AGENT.MD`),
which serves as your single source of truth for validation pillars, code quality criteria,
and audit expectations.

================================================================================
QUALITY SPECIFICATION (QUALITY_AGENT.MD):
================================================================================
{quality_spec}

================================================================================
EVALUATION DATA INPUTS:
================================================================================

--- 1. Pytest & Coverage Results ---
{test_output}

--- 2. Ruff Linting Results ---
{ruff_output}

--- 3. Mypy Type Checking Results ---
{mypy_output}

--- 4. Codebase Context ---
{codebase_context}

================================================================================
INSTRUCTIONS:
================================================================================
- Strictly follow the validation pillars and mandatory criteria defined in QUALITY_AGENT.MD.
- Provide a rigorous, structured Markdown evaluation report covering:
  1. Executive Summary & Overall Quality Score (0-100%).
  2. Adherence to each of the 5 Core Validation Pillars.
  3. Findings mapped to each Mandatory Code Quality & Test Audit Criterion.
  4. Static Analysis & Test Suite Summary (incorporating pytest, ruff, and mypy outcomes).
  5. Prioritized, actionable recommendations for remediation.
"""

    logger.info("Analyzing codebase, tests, and static analysis outputs with Gemini...")
    response: genai.types.GenerateContentResponse = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    text_content: str | None = response.text
    return text_content if text_content is not None else ""


def build_fallback_report(
    test_output: str,
    ruff_output: str,
    mypy_output: str,
    error_message: str,
) -> str:
    """Generate a structured fallback report when Gemini evaluation cannot be completed."""
    return f"""# Code Quality & Test Gap Evaluation Report (Fallback)

> **Notice**: Automated Gemini AI analysis could not be completed.
> **Reason**: {error_message}

## Test Suite Execution Output (pytest)
```text
{test_output}
```

## Static Linting Output (ruff)
```text
{ruff_output}
```

## Static Type Checking Output (mypy)
```text
{mypy_output}
```

## Recommended Actions
1. Ensure `GEMINI_API_KEY` is set in your `.env` or environment if full AI analysis is required.
2. Review test failures, lint findings, and type check outputs above.
3. Consult `QUALITY_AGENT.MD` manually for validation pillars and mandatory criteria compliance.
"""


def main() -> None:
    """Execute the end-to-end evaluation agent workflow."""
    logger.info("Starting Autonomous Evaluation Agent...")

    # 1. Load single source of truth
    try:
        quality_spec: str = load_quality_specification()
    except FileNotFoundError as err:
        logger.error(str(err))
        sys.exit(1)

    # 2. Run test suite and static checks
    test_code, test_output = run_pytest()
    ruff_code, ruff_output = run_ruff()
    mypy_code, mypy_output = run_mypy()

    # 3. Gather full codebase context
    codebase_context: str = gather_codebase_context()

    # 4. Analyze via Gemini (or fallback gracefully)
    report: str
    try:
        report = evaluate_with_gemini(
            quality_spec=quality_spec,
            codebase_context=codebase_context,
            test_output=test_output,
            ruff_output=ruff_output,
            mypy_output=mypy_output,
        )
    except Exception as exc:
        logger.warning(f"Gemini analysis unavailable or failed: {exc}")
        report = build_fallback_report(
            test_output=test_output,
            ruff_output=ruff_output,
            mypy_output=mypy_output,
            error_message=str(exc),
        )

    # 5. Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    logger.success(f"Evaluation complete. Report saved to {REPORT_PATH}")

    # Propagate failures or missing API key
    if not os.environ.get("GEMINI_API_KEY"):
        logger.error("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    if test_code != 0:
        logger.warning("Test suite reported failures.")
        sys.exit(test_code)

    if ruff_code != 0 or mypy_code != 0:
        logger.warning("Static analysis checks (ruff or mypy) reported issues.")

    logger.success("Evaluation workflow concluded successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()