# Autonomous Code Quality & Test Gap Evaluation Agent

## Objective
This agent acts as an autonomous quality assurance auditor within the repository. It inspects the codebase, evaluates implementation adherence against the **5 Core Software Validation Types**, runs the existing test suite, analyzes test coverage, and identifies gaps or missing assertions.

---

## The 5 Core Validation Pillars

1. **Unit Tests**: Isolated verification of individual functions, classes, and methods using mocking where necessary (e.g., `pytest`).
2. **Integration Tests**: Verification of component interactions, database adapters, API clients, and network request handling under realistic or mocked conditions.
3. **Static Code Analysis**: Automated verification of type safety (`mypy`), linting (`flake8`/`eslint`), and code style consistency.
4. **Mutation Testing**: Assessment of test suite robustness by introducing code mutations and verifying that existing tests fail accordingly.
5. **Black-Box Verification**: Functional and behavioral validation based on expected inputs and outputs without relying on internal implementation details (e.g., BDD scenarios, end-to-end execution checks).

---

## Agent Workflow & Execution

When invoked, the evaluation agent performs the following sequential steps:
1. **Codebase Scan**: Discovers source files (`src/`, `finance_data/`) and test suites (`tests/`).
2. **Validation Mapping**: Evaluates which of the 5 validation pillars are covered for each module.
3. **Test Suite Execution**: Runs pytest and collects execution results, coverage metrics, and failures.
4. **Gemini AI Analysis**: Sends module structure and test metadata to the Gemini API to identify logic gaps, missing edge cases, and unverified validation pillars.
5. **Report Generation**: Outputs a structured markdown report (`reports/validation_gap_report.md`) detailing identified gaps and recommendations.

---

## Required Environment Variables
- `GEMINI_API_KEY`: API key authorized to invoke the Gemini model for code reasoning.