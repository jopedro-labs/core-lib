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
  - [ ] `token.json`: Expected locally at project root for cached tokens (generated in `secrets/token.json` with `https://www.googleapis.com/auth/drive` scope and configured via `GDRIVE_TOKEN_PATH`).
  - [x] `secrets/`: Gitignored directory created locally and initialized with `credentials.json` and `token.json`.
- [x] **Missing State Directory Fixtures**:
  - `.github/api-revisions/`: The required state files (`gdrive-revision.json`, `gdrive-revision.previous.json`, `drive-v3-discovery.json`, and `drive-v3-discovery.previous.json`) are present locally in the gitignored directory for `scripts/gdrive_diff.py` and `scripts/gdrive_update_bot.py` (originally sourced/maintained via the remote `bot-state` branch).
- [x] **Missing Output Directory for Generated Reports**:
  - `reports/`: Ignored in `.gitignore`. Required when running `scripts/gemini_gdrive_advisor.py` (`reports/gdrive_revision_analysis.md`) and `scripts/quality_eval_agent.py` (`reports/validation_gap_report.md`).
- [ ] **Undeclared Dependencies in `pyproject.toml`**:
  - `scripts/gemini_gdrive_advisor.py` requires `google-genai` (`from google import genai`), which is not declared in `pyproject.toml` (neither under `dependencies` nor `optional-dependencies`).
  - `scripts/quality_eval_agent.py` requires `google-generativeai` (`import google.generativeai as genai`) and `python-dotenv` (`from dotenv import load_dotenv`), neither of which are declared in `pyproject.toml`.
  - Inconsistent SDKs used across scripts (`google-genai` in `gemini_gdrive_advisor.py` vs legacy `google-generativeai` in `quality_eval_agent.py`).
  - `make quality-eval-agent` fails in environments installed via `make install` (`pip install -e ".[gdrive,dev]"`) due to missing `google-generativeai` and `python-dotenv`.
  - `pytest-cov` is executed via `scripts/quality_eval_agent.py` (`--cov=.`), but `pytest-cov` is absent from `dev` dependencies in `pyproject.toml`.

---

## 2. Bugs & Code Fragilities

- [ ] **Version Mismatch across Project Metadata (`pyproject.toml` vs `core_lib/__init__.py`)**:
  - `pyproject.toml` specifies `version = "0.1.1"`.
  - `core_lib/__init__.py` specifies `__version__ = "0.1.0"`.
  - `README.md` references badge version `0.1.0`.
  - This discrepancy leads to inconsistent package releases and confusion regarding installed versions.
- [ ] **Case-Sensitivity Docstring / Variable Name Bug in `GDriveService.__init__`**:
  - In `core_lib/gdrive/gdrive_service.py` docstrings (lines 30-34): mentions `gdrive_CREDENTIALS_PATH`, `gdrive_TOKEN_PATH`, and `gdrive_DATA_FOLDER_ID` in lowercase prefix, but `core_lib/gdrive/gdrive_auth.py` and `GDriveService.__init__` inspect uppercase `GDRIVE_CREDENTIALS_PATH`, `GDRIVE_TOKEN_PATH`, and `GDRIVE_DATA_FOLDER_ID`.
- [ ] **Brittle Query Injection Vulnerability in GDrive Queries (`core_lib/gdrive/gdrive_service.py`)**:
  - Methods `file_exists()`, `upload_file()`, `download_file()`, and `get_file_modified_time()` sanitize single quotes using `.replace("'", "\\'")`.
  - However, `get_latest_file_id()` (lines 249-251) uses unescaped string formatting:
    `query = f"name contains '{prefix}' and trashed = false"`. If `prefix` contains single quotes, backslashes, or control characters, the query fails or causes query injection.
  - None of the methods validate or escape `folder_id` in `f"'{target_folder}' in parents"`, risking malformed query errors if an unsanitized folder ID is supplied.
- [ ] **Silent Exception Swallowing & Loss of Tracebacks**:
  - `core_lib/file_utils/file_utils.py`: `load_file_content()` catches broad `Exception` and logs an error, returning `""`. Callers cannot distinguish between a missing file, permission denial, or encoding errors.
  - `core_lib/gdrive/gdrive_service.py`: `_get_service()`, `verify_folder_access()`, `file_exists()`, `list_files()`, `upload_file()`, `download_file()`, `sync_files()`, `get_latest_file_id()`, `download_latest_file()`, and `get_file_modified_time()` catch broad `Exception`, log it, and return `False`, `None`, or `[]`. Callers receive falsy values with no programmatically inspectable error details or status codes.
- [ ] **Non-Atomic and Unbounded Memory Usage in File Operations**:
  - `GDriveService.download_file()` (lines 189-195) and `download_latest_file()` (lines 296-302): download entire files into memory via `io.BytesIO()` before writing to disk with `dest.write_bytes(fh.getvalue())`. For large files (e.g. database snapshots, multi-gigabyte archives), this triggers high memory consumption or `MemoryError`.
  - Neither download operation writes to a temporary file before renaming, leaving partially written files if the transfer or process is interrupted.
- [ ] **Infinite Loop Risk in `download_file` Chunk Iteration**:
  - In `core_lib/gdrive/gdrive_service.py` (lines 192-194):
    ```python
    while not downloader.next_chunk()[1]:
        pass
    ```
    If `downloader.next_chunk()` returns status or progress where the second element is not strictly truthy upon completion, or if an unexpected state occurs, this loop can hang. In contrast, `download_latest_file()` (lines 298-300) properly unpacks `status, done`.
- [ ] **Missing Type Annotations on Protected Attributes and Module Attributes**:
  - In `core_lib/gdrive/gdrive_service.py`: `self._service: Any | None = None` is untyped beyond `Any`.
  - In `core_lib/gdrive/gdrive_auth.py`: `SCOPES: list[str]` is defined, but `creds = Credentials.from_authorized_user_file(...)` uses `# type: ignore[no-untyped-call]`, bypassing strict type checking.
  - In `scripts/gdrive_diff.py`: functions take `dict[str, Any]` but nested structures (methods, parameters, schemas) lack `TypedDict` schemas.
- [ ] **Subprocess Hardcoding and Failure to Propagate Exit Codes in Scripts**:
  - `scripts/quality_eval_agent.py`: `run_pytest()` captures output but runs `[sys.executable, "-m", "pytest", "--cov=.", "--cov-report=term-missing", "-v"]`. If `pytest-cov` is not installed, pytest immediately fails with unrecognized argument `--cov`.
  - In `scripts/quality_eval_agent.py`, `gather_codebase_context()` walks the entire filesystem without filtering `dist`, `build`, `.mypy_cache`, `.ruff_cache`, or binary files, which can cause excessive context size or encoding read issues.
- [ ] **Hardcoded Discord API Version in `DiscordNotifier`**:
  - In `core_lib/discord/discord_service.py`: `API_BASE_URL` is hardcoded as `"https://discord.com/api/v10"`.
  - In line 93, the URL is hardcoded again as string literal `f"https://discord.com/api/v10/channels/{channel_id}/messages"` instead of utilizing `self.API_BASE_URL`.
- [ ] **Language Inconsistency in Test File Comments**:
  - In `tests/test_gdrive_service.py` (line 147): comment written in Portuguese (`# Correção: usar .return_value em vez de chamar .update() na configuração`), violating the rule that all code comments must strictly be in English.
- [ ] **Typo in `TODO.md`**:
  - `TODO.md` contains typos: `Serach for text im portuguese and transalate do english`.
- [ ] **Missing Typed Wrappers for Google API Client Resources**:
  - Google API client resources are currently handled as untyped or loosely typed dictionaries/objects instead of dedicated typed wrappers (`TypedDict` / protocols / wrapper classes), making field access and API responses harder to verify statically.
---

## 3. Test Coverage Gaps

- [ ] **Missing Tests for `scripts/gdrive_diff.py`**:
  - `scripts/gdrive_diff.py` contains deterministic diffing logic (`compare_discovery_docs`, `_flatten_methods`, `generate_diff_summary`, `format_markdown_diff`).
  - There is zero test coverage (`tests/test_gdrive_diff.py` does not exist).
  - Edge cases such as added methods, removed methods, type changes, added/removed enums, breaking parameter requirements, and schema property changes are completely untested.
- [ ] **Missing Tests for `scripts/gemini_gdrive_advisor.py`**:
  - `scripts/gemini_gdrive_advisor.py` implements authority ceiling logic (`resolve_impact_level`), AST/text method scanning (`scan_local_gdrive_usage`), markdown generation (`build_markdown_report`), and fallback behavior.
  - No unit tests exist for `scripts/gemini_gdrive_advisor.py`.
  - The critical authority rule (`LOW` baseline cannot be escalated, `MEDIUM` can only stay or downgrade, `HIGH` can stay or downgrade) has no unit test validation.
- [ ] **Missing Tests for `scripts/quality_eval_agent.py`**:
  - No unit tests verify `gather_codebase_context`, handling of `GEMINI_API_KEY` absence, or behavior when pytest fails.
- [ ] **Untested Edge Cases in `core_lib.logger`**:
  - `core_lib/logger/logger.py`:
    - No tests verify `logger.print(..., color=...)` with ANSI color values passed in.
    - No tests verify handling when message contains non-ASCII or multi-line strings.
- [ ] **Untested Edge Cases in `core_lib.file_utils`**:
  - `load_file_content()`:
    - No tests for files with non-UTF-8 encodings (e.g. latin-1, binary files) to verify error logging and graceful return.
    - No tests for symbolic links (broken symlinks, circular symlinks).
- [ ] **Untested Edge Cases in `core_lib.discord`**:
  - `send_message()`:
    - Missing tests for malformed JSON responses on rate-limiting (`429` with invalid JSON or non-numeric `retry_after`).
    - Missing tests for payload limits (e.g. Discord 2000 character limit on `content` or 6000 character aggregate embed limit).
    - Missing tests verifying `max_retries` configuration on `HTTPAdapter`.
- [ ] **Untested Edge Cases in `core_lib.gdrive`**:
  - `upload_file()`:
    - Missing test for `overwrite=True` when multiple remote files exist with the same name.
    - Missing test for custom `mime_type` passing to `MediaFileUpload`.
    - Missing test for empty/0-byte file uploads.
  - `download_file()` and `download_latest_file()`:
    - Missing test verifying behavior when remote file is empty (0 bytes).
    - Missing test verifying behavior when parent destination folder does not exist (verifying `dest.parent.mkdir(parents=True, exist_ok=True)`).
  - `get_latest_file_id()`:
    - Missing test for ordering when multiple files share the exact same `modifiedTime`.
    - Missing test for prefixes with special regex/SQL characters (`%`, `_`, `'`).
  - `get_file_modified_time()`:
    - Missing test when `modifiedTime` key is missing from API file resource dictionary (returns `None`).
  - `get_google_service_credentials()`:
    - Missing test when credentials file contains invalid JSON.
    - Missing test verifying file permissions or directory creation failure on `tok_path.parent.mkdir()`.
- [ ] **Missing Integration / Real Adapter Tests**:
  - All existing Google Drive and Discord tests rely strictly on unit mocks (`MagicMock`).
  - No end-to-end integration tests exist with real or local mock HTTP servers (such as `responses`, `requests-mock`, or local OAuth redirect server testing).
- [ ] **Lack of Loopback Integration Fixtures Instead of `unittest.mock`**:
  - Tests rely heavily on `unittest.mock` (`MagicMock`) rather than local loopback integration fixtures/servers where feasible, reducing confidence in real HTTP/protocol serialization and response handling.
  