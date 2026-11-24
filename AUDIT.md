# Codebase Audit Report: `core-lib`

## Executive Summary
This document provides a factual, read-only comprehensive audit of the `core-lib` repository. It identifies missing runtime and test configurations, local environment dependencies, potential bugs, type annotations and code fragilities, brittle assumptions, and test coverage gaps across all modules and automated scripts.

---

## 1. Missing Local Files & Environment Setup

- [x] **Missing Root `.env` / Secret Templates (`.env.example`)**:
  - The repository relies heavily on environment variables across `core_lib`, `scripts/`, and GitHub Actions workflows, but provides no `.env.example` or documented configuration template.
  - Missing tracked example file for configuring local runs:
    - `GDRIVE_CREDENTIALS_PATH`: Path to OAuth2 client secrets (defaults to `credentials.json`).
    - `GDRIVE_TOKEN_PATH`: Path to saved OAuth2 user tokens (defaults to `token.json`).
    - `GDRIVE_DATA_FOLDER_ID`: Default Google Drive target folder ID for backups and synchronization.
    - `GEMINI_API_KEY`: API key for `google-genai` and `google-generativeai` scripts (`scripts/gemini_gdrive_advisor.py`, `scripts/quality_eval_agent.py`).
    - `GEMINI_MODEL`: Gemini model identifier (defaults to `gemini-2.5-flash` in `scripts/gemini_gdrive_advisor.py` and `gemini-3.1-pro-preview` in `scripts/quality_eval_agent.py`).
    - `INFRA_ALERTS_DISCORD_WEBHOOK`: Webhook URL for alert notifications in CI workflows.
    - `GITHUB_OUTPUT`: Path to runner step output file in CI/local execution.
- [x] **Missing OAuth2 Credential Fixtures / Mock Files**:
  - [x] `credentials.json`: Expected locally at project root by default when calling `core_lib.gdrive.get_google_service_credentials` without arguments (configured via `GDRIVE_CREDENTIALS_PATH` inside `secrets/`).
  - [x] `token.json`: Expected locally at project root for cached tokens (generated in `secrets/token.json` with `https://www.googleapis.com/auth/drive` scope and configured via `GDRIVE_TOKEN_PATH`).
  - [x] `secrets/`: Gitignored directory created locally and initialized with `credentials.json` and `token.json`.
- [x] **Missing State Directory Fixtures**:
  - `.github/api-revisions/`: The required state files (`gdrive-revision.json`, `gdrive-revision.previous.json`, `drive-v3-discovery.json`, and `drive-v3-discovery.previous.json`) are present locally in the gitignored directory for `scripts/gdrive_diff.py` and `scripts/gdrive_update_bot.py` (originally sourced/maintained via the remote `bot-state` branch).
- [x] **Missing Output Directory for Generated Reports**:
  - `reports/`: Ignored in `.gitignore`. Required when running `scripts/gemini_gdrive_advisor.py` (`reports/gdrive_revision_analysis.md`) and `scripts/quality_eval_agent.py` (`reports/validation_gap_report.md`).
- [x] **Undeclared Dependencies in `pyproject.toml`**:
  - `scripts/gemini_gdrive_advisor.py` requires `google-genai` (`from google import genai`), declared under `dev` optional-dependencies in `pyproject.toml`.
  - `scripts/quality_eval_agent.py` requires `google-generativeai` (`import google.generativeai as genai`) and `python-dotenv` (`from dotenv import load_dotenv`), declared under `dev` optional-dependencies in `pyproject.toml`.
  - Inconsistent SDKs used across scripts (`google-genai` in `gemini_gdrive_advisor.py` vs legacy `google-generativeai` in `quality_eval_agent.py`); `google-generativeai` is deprecated by Google and should be migrated to `google-genai` in a subsequent refactoring issue.
  - `make quality-eval-agent` executes cleanly in environments installed via `make install` (`pip install -e ".[gdrive,dev]"`).
  - `pytest-cov` is executed via `scripts/quality_eval_agent.py` (`--cov=.`) and is declared under `dev` dependencies in `pyproject.toml`.

---

## 2. Bugs & Code Fragilities

- [x] **Version Mismatch across Project Metadata (`pyproject.toml` vs `core_lib/__init__.py`)**:
  - `pyproject.toml` specifies `version = "0.1.1"`.
  - `core_lib/__init__.py` specifies `__version__ = "0.1.1"`.
  - `README.md` references badge version `0.1.1`.
  - Package version aligned across all files.
- [x] **Case-Sensitivity Docstring / Variable Name Bug in `GDriveService.__init__`**:
  - In `core_lib/gdrive/gdrive_service.py` docstrings: updated to uppercase `GDRIVE_CREDENTIALS_PATH`, `GDRIVE_TOKEN_PATH`, and `GDRIVE_DATA_FOLDER_ID` matching environment variables and runtime inspection.
- [x] **Brittle Query Injection Vulnerability in GDrive Queries (`core_lib/gdrive/gdrive_service.py`)**:
  - Implemented `_escape_query_str()` and `_format_parents_clause()` across all methods including `get_latest_file_id()`, escaping single quotes and backslashes.
  - Added character sanitation to folder IDs via `sanitize_gdrive_folder_id()`.
- [x] **Silent Exception Swallowing & Loss of Tracebacks**:
  - Broad exceptions are captured with explicit error/warning logs and structured fallbacks across `core_lib.file_utils` and `core_lib.gdrive.gdrive_service`.
- [x] **Non-Atomic and Unbounded Memory Usage in File Operations**:
  - Refactored `download_file()` and `download_latest_file()` to stream directly into temporary files on disk and atomically replace destination files (`temp_dest.replace(dest)`), preventing in-memory unbounded buffering.
- [x] **Infinite Loop Risk in `download_file` Chunk Iteration**:
  - Refactored chunk iteration in `download_file()` to explicitly unpack `status, done = downloader.next_chunk()`, preventing infinite loops.
- [x] **Missing Type Annotations on Protected Attributes and Module Attributes**:
  - `self._service` is annotated as `GoogleDriveClient | None`.
  - `core_lib/gdrive/gdrive_auth.py` type checks cleanly with explicit typing.
  - `scripts/gdrive_diff.py` defines and uses `TypedDict` schemas (`DiscoveryDiffResult`, `MethodParameterChange`, etc.).
- [x] **Subprocess Hardcoding and Failure to Propagate Exit Codes in Scripts**:
  - In `scripts/quality_eval_agent.py`, `run_pytest()` dynamically checks for `pytest_cov` before passing coverage arguments.
  - Directory filtering excludes `dist`, `build`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, and virtual environments.
- [x] **Hardcoded Discord API Version in `DiscordNotifier`**:
  - Replaced hardcoded literal with `f"{self.API_BASE_URL}/channels/{channel_id}/messages"`.
- [x] **Language Inconsistency in Test File Comments**:
  - Translated Portuguese test comments in `tests/test_gdrive_service.py` to English.
- [x] **Typo in `TODO.md`**:
  - Fixed typos in `TODO.md` to proper English.
- [x] **Missing Typed Wrappers for Google API Client Resources**:
  - Introduced `core_lib.gdrive.types` defining structural `TypedDict` schemas (`DriveFileResource`, `DriveFileListResponse`) and client protocols (`GoogleDriveClient`, `GoogleDriveFilesResource`, `GoogleDriveExecutable`).

---

## 3. Test Coverage Gaps

- [x] **Missing Tests for `scripts/gdrive_diff.py`**:
  - Added comprehensive test suite `tests/test_gdrive_diff.py` covering method additions, removals, parameter modifications, type changes, enums, schemas, and markdown rendering.
- [x] **Missing Tests for `scripts/gemini_gdrive_advisor.py`**:
  - Added test suite `tests/test_gemini_gdrive_advisor.py` thoroughly validating the authority ceiling rules (`LOW`, `MEDIUM`, `HIGH`), usage scanning, Gemini queries, and markdown report generation.
- [x] **Missing Tests for `scripts/quality_eval_agent.py`**:
  - Added test suite `tests/test_quality_eval_agent.py` testing context collection, pytest execution, missing API key handling, and exit code propagation.
- [x] **Untested Edge Cases in `core_lib.logger`**:
  - Added edge case tests in `tests/test_edge_cases_and_fixtures.py` for custom ANSI colors, disabled color mode, and multiline non-ASCII exceptions.
- [x] **Untested Edge Cases in `core_lib.file_utils`**:
  - Added tests in `tests/test_edge_cases_and_fixtures.py` for non-UTF-8 binary data, broken symlinks, and directories.
- [x] **Untested Edge Cases in `core_lib.discord`**:
  - Added tests covering HTTP 429 rate-limiting with non-JSON bodies and numeric `retry_after`, oversized message limits, and retry adapter configuration.
- [x] **Untested Edge Cases in `core_lib.gdrive`**:
  - Added tests for 0-byte file uploads, multiple overwrite matches, parent directory creation, atomic download replace, prefix query escaping, and missing `modifiedTime`.
- [x] **Missing Integration / Real Adapter Tests**:
  - Added loopback HTTP fixtures in `tests/test_edge_cases_and_fixtures.py` using a real local `HTTPServer` validating real HTTP transport serialization and response handling.
- [x] **Lack of Loopback Integration Fixtures Instead of `unittest.mock`**:
  - Implemented local loopback server fixtures in `tests/test_edge_cases_and_fixtures.py` demonstrating integration testing without relying solely on `MagicMock`.
  