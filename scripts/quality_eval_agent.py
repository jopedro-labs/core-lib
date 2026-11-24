"""Autonomous evaluation agent script powered by Gemini for test gap analysis.

This module inspects repository source code and test files, executes the test suite,
evaluates coverage across the 5 validation pillars, and generates a structured
gap analysis report using the Gemini API.
"""

from __future__ import annotations

import os
import subprocess
import sys

import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()


def run_pytest() -> tuple[int, str]:
    """Execute the pytest test suite via current python interpreter and capture output."""
    print("🧪 Running test suite via pytest...")
    # Check if pytest-cov is available before adding cov flags
    cmd = [sys.executable, "-m", "pytest"]
    try:
        import pytest_cov  # noqa: F401
        cmd.extend(["--cov=.", "--cov-report=term-missing"])
    except ImportError:
        pass
    cmd.append("-v")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + "\n" + result.stderr


def gather_codebase_context() -> str:
    """Collect structure and content samples from source and test directories."""
    context_parts: list[str] = []
    ignored_dirs = {
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
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, encoding="utf-8") as f:
                        content = f.read()
                        context_parts.append(f"=== FILE: {filepath} ===\n{content}\n")
                except Exception:
                    pass
    return "\n".join(context_parts)


def evaluate_with_gemini(codebase_context: str, test_output: str) -> str:
    """Invoke Gemini API to analyze validation gaps across the 5 pillars."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    genai.configure(api_key=api_key)

    # Read model name from .env or fallback to gemini-3.1-pro-preview
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
    print(f"🤖 Initializing Gemini model [{model_name}] for evaluation...")
    model = genai.GenerativeModel(model_name)

    prompt = f"""
You are an expert Software Quality Assurance and Test Engineering Agent.
Analyze the provided codebase and test execution output.

Evaluate adherence to the following 5 validation types:
1. Unit Tests
2. Integration Tests
3. Static Code Analysis (Type safety & linting)
4. Mutation Testing readiness
5. Black-Box / Functional Verification

Test Output & Coverage Results:
{test_output}

Codebase Context:
{codebase_context}

Provide a rigorous markdown report identifying:
- Current validation coverage for each of the 5 pillars.
- Specific testing gaps or missing edge cases.
- Concrete recommendations for new unit/integration tests to reach robust coverage.
"""

    print("🤖 Analyzing codebase and test gaps with Gemini...")
    response = model.generate_content(prompt)
    return response.text


def main() -> None:
    """Execute the end-to-end evaluation agent workflow."""
    print("🚀 Starting Autonomous Evaluation Agent...")

    # 1. Run tests
    exit_code, test_output = run_pytest()

    # 2. Gather context
    codebase_context = gather_codebase_context()

    # 3. Analyze via Gemini
    report = evaluate_with_gemini(codebase_context, test_output)

    # 4. Save report
    os.makedirs("reports", exist_ok=True)
    report_path = "reports/validation_gap_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"✅ Evaluation complete. Report saved to {report_path}")

    if exit_code != 0:
        print("⚠️ Test suite reported failures.")
        sys.exit(exit_code)
    else:
        print("✅ Test suite passed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()