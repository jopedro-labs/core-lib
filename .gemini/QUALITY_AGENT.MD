# Autonomous Code Quality & Test Gap Evaluation Agent

## Objective
This agent acts as a local, on-demand quality assurance auditor within the **`finances-data`** repository (`make quality-eval-agent`). It serves a dual purpose:
1. **Primary Focus — Test Coverage & Suite Quality**: Inspects the test suite, executes `pytest` with coverage tracking, evaluates adherence against the **5 Core Software Validation Pillars**, and identifies missing assertions, edge cases, and failure-path gaps.
2. **Complementary Focus — Code Quality & Static Hygiene**: Runs static checks (`ruff`, `mypy`) and audits source modules (`finances_data/`, `data/`, and `scripts/`) for type safety, suppression bypasses, error-handling robustness, and repository convention compliance.

> **Execution Policy**: This agent is strictly a **local developer tool** invoked on demand via `make quality-eval-agent` (or `python scripts/quality_eval_agent.py`). It is **not** executed inside GitHub Actions CI workflows, avoiding external API latency, token costs, and secret dependencies during automated CI runs.

---

## The 5 Core Validation Pillars

1. **Unit Tests**: Isolated verification of individual functions, classes, and methods using mocking where necessary (`pytest`).
2. **Integration Tests**: Verification of component interactions, API clients, file I/O, and network request handling under realistic, loopback, or controlled conditions.
3. **Static Code Analysis**: Execution and evaluation of `ruff` and `mypy` (per repository configuration) alongside code hygiene checks.
4. **Mutation Testing Readiness (Qualitative Assessment)**: Heuristic evaluation of assertion strength and test sensitivity to subtle logic mutations (assessed analytically by the LLM rather than executing live mutation tools).
5. **Black-Box Verification**: Functional and behavioral validation based on expected inputs, outputs, and error contracts without over-relying on internal mock mirroring.

---

## Mandatory Code Quality & Test Audit Criteria

When analyzing `finances_data/`, `data/`, `scripts/`, and `tests/`, the agent must explicitly check for and report violations of the following repository rules:

1. **Mandatory Type Annotations**: All functions, methods, class/instance attributes, and relevant local variables must include explicit type annotations.
2. **No `Any` Type Annotations**: Flag avoidable uses of `typing.Any` and recommend concrete types, explicit unions, `TypedDict`, `Protocol`, or `TypeVar`.
3. **No Suppression / Bypass Comments**: Flag `# type: ignore`, `# noqa`, or `@pytest.mark.skip` used to silence lint, type, or test failures without a clear, documented technical justification.
4. **Explicit Error & Edge-Case Handling**: Check how functions handle empty/`None` inputs, missing paths, network timeouts, malformed/non-JSON payloads, and ensure broad exceptions are not silently swallowed.
5. **Behavior & Failure-Path Test Depth**: Verify that tests exercise error branches, retries, and fallback logic (e.g., rate-limit backoff/retries, missing credentials/API keys, malformed responses) rather than only happy-path mock call assertions.
6. **Logger Usage & `print()` Review**: Flag `print()` calls across the codebase, evaluating code context to distinguish intentional CLI piping (such as stdout JSON output) from logging candidates, and provide findings as input for developer/Continue review rather than blind removal.
7. **No Exposed Secrets or Sensitive Paths**: Flag hardcoded secrets, credentials, tokens, or sensitive local paths in source code or diagnostic output.
8. **Modularity & Data Contract Hygiene**: Flag overly long or tightly coupled functions, duplicated logic, and missing validation of input/data contracts.
9. **Repository Conventions Compliance**: Enforce English-only code, comments, and docstrings across the entire repository, and alignment with `ruff` and `mypy` configurations.

---

## Agent Workflow & Execution

When invoked locally, the evaluation agent performs the following sequential steps:
1. **Codebase Scan**: Discovers relevant source files (`finances_data/`, `data/`, `scripts/`) and test suites (`tests/`), excluding cache/build/artifact directories (`.git`, `.venv`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `reports`, `dist`, `build`) without artificial context truncation.
2. **Test & Static Tool Execution**: Runs `pytest` (using `pytest-cov` when available) as well as `ruff` and `mypy` to collect pass/fail outcomes, failure tracebacks, static analysis findings, and coverage metrics.
3. **Validation & Code Quality Mapping**: Cross-references source modules, test suites, and tool outputs against the **5 Core Validation Pillars** and the **Mandatory Code Quality & Test Audit Criteria** defined in this document as the source of truth.
4. **Gemini AI Analysis**: Sends the collected repository context, quality criteria, `pytest` results, and `ruff`/`mypy` outputs to the Gemini API via the official `google-genai` SDK (`GEMINI_MODEL`).
5. **Report Generation**: Writes a structured, actionable markdown report to `reports/quality_agent_report.md` (gitignored) categorizing findings by severity and module.

---

## Configuration & Environment Variables

| Variable | Required | Description | Default |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | API key authorized to invoke the Gemini API (loaded from `.env` or shell environment). | *Required* |
| `GEMINI_MODEL` | No | Gemini model identifier used for code and test gap reasoning. | `gemini-3.8-flash` |
