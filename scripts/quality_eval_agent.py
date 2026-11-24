"""Autonomous evaluation agent script powered by Gemini for test gap analysis.


This module inspects repository source code and test files, executes the test suite,
evaluates coverage across the 5 validation pillars and 6 mandatory code quality criteria,
and generates a structured gap analysis report using the modern Google GenAI SDK.
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

DEFAULT_MODEL: str = "gemini-2.5-flash"
REPORT_PATH: Path = Path("reports/validation_gap_report.md")


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
    return result.returncode, result.stdout + "\n" + result.stderr


def gather_codebase_context() -> str:
    """Collect structure and content samples from source and test directories."""
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
        "jopedro_core_lib.egg-info",
        "reports",
    }

    # Walk through source files
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
        for file in files:
            if file.endswith((".py", ".yml", ".yaml", ".md", ".toml")):
                filepath: str = os.path.join(root, file)
                try:
                    with open(filepath, encoding="utf-8") as f:
                        content: str = f.read()
                        context_parts.append(f"=== FILE: {filepath} ===\n{content}\n")
                except Exception:
                    pass
    return "\n".join(context_parts)


def evaluate_with_gemini(codebase_context: str, test_output: str) -> str:
    """Invoke Gemini API to analyze validation gaps across the 5 pillars and 6 audit criteria."""
    api_key: str | None = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    model_name: str = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    logger.info(f"Initializing Gemini client [{model_name}] for evaluation...")
    client: genai.Client = genai.Client(api_key=api_key)

    prompt: str = f"""
You are an expert Software Quality Assurance Agent auditing the 'core-lib' repository.
Analyze the provided codebase and test execution output.

Evaluate adherence to the following 5 Core Software Validation Pillars:
1. Unit Tests (Isolated verification of functions and classes using pytest)
2. Integration Tests (Component interaction, API clients, file I/O, network handling)
3. Static Code Analysis (Strict type safety with mypy --strict, linting with ruff)
4. Mutation Testing Readiness (Qualitative heuristic assessment of assertion sensitivity)
5. Black-Box Verification (Behavioral verification without internal mock mirroring)

Explicitly audit and report compliance with the 6 Mandatory Audit Criteria:
1. Mandatory Type Annotations: Full annotations on functions, methods, attributes, variables.
2. No 'Any' Type Annotations: Flag avoidable typing.Any; recommend concrete types/protocols.
3. No Suppression / Bypass Comments: Flag # type: ignore, # noqa, or @pytest.mark.skip.
4. Explicit Error & Edge-Case Handling: Check handling of empty/None inputs, missing paths.
5. Behavior & Failure-Path Test Depth: Verify tests exercise error branches and fallbacks.
6. Repository Conventions Compliance: Enforce English-only code, comments, and docstrings.

Test Output & Coverage Results:
{test_output}

Codebase Context:
{codebase_context}

Provide a rigorous markdown report formatted with:
- Executive Summary & Overall Quality Score
- Findings mapped to the 5 Validation Pillars
- Audit results for each of the 6 Mandatory Criteria (highlighting violations if present)
- Prioritized Action Plan / Concrete Recommendations for missing unit/integration tests
"""

    logger.info("Analyzing codebase and test gaps with Gemini...")
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    text_content: str | None = response.text
    return text_content if text_content is not None else ""


def build_fallback_report(test_output: str, error_message: str) -> str:
    """Generate a structured fallback report when Gemini evaluation cannot be completed."""
    return f"""# Code Quality & Test Gap Evaluation Report (Fallback)

> **Notice**: Automated Gemini AI analysis could not be completed.
> **Reason**: {error_message}

## Test Suite Execution Output
```text
{test_output}
```

## Recommended Actions
1. Ensure `GEMINI_API_KEY` is set in your `.env` or environment if full AI analysis is required.
2. Review test failures and coverage gaps from the output above.
3. Verify compliance with the 5 Validation Pillars and 6 Mandatory Audit Criteria manually.
"""


def main() -> None:
    """Execute the end-to-end evaluation agent workflow."""
    logger.info("Starting Autonomous Evaluation Agent...")

    # 1. Run tests
    exit_code, test_output = run_pytest()

    # 2. Gather context
    codebase_context: str = gather_codebase_context()

    # 3. Analyze via Gemini (or fallback gracefully)
    report: str
    try:
        report = evaluate_with_gemini(codebase_context, test_output)
    except Exception as e:
        logger.warning(f"Gemini analysis unavailable or failed: {e}")
        report = build_fallback_report(test_output, str(e))

    # 4. Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    logger.success(f"Evaluation complete. Report saved to {REPORT_PATH}")

    # Propagate pytest exit code or missing API key error
    if not os.environ.get("GEMINI_API_KEY"):
        logger.error("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    if exit_code != 0:
        logger.warning("Test suite reported failures.")
        sys.exit(exit_code)
    else:
        logger.success("Test suite passed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()