# core-lib

![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.1-58a6ff?style=flat-square)
![CI](https://github.com/jopedro-labs/core-lib/actions/workflows/ci.yml/badge.svg?branch=main)
![Monitor GDrive API](https://github.com/jopedro-labs/core-lib/actions/workflows/gdrive_bot.yml/badge.svg)
<br />
![Linter](https://img.shields.io/badge/linter-Ruff-000000?style=flat-square&logo=python&logoColor=white)
![Type Check](https://img.shields.io/badge/types-mypy%20strict-2A6DB2?style=flat-square&logo=python&logoColor=white)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)
![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen?style=flat-square)
![Gemini AI](https://img.shields.io/badge/Gemini_AI-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)
![GNU Make](https://img.shields.io/badge/env-GNU%20Make-active?style=flat-square&logo=gnu-make&logoColor=white)
![MIT License](https://img.shields.io/badge/license-MIT-607D8B?style=flat-square)

Shared Python support library. Provides common utilities (logging, file I/O), service integrations, and autonomous code quality evaluation tools for internal projects.

---

## Installation

Add to your project's `requirements.txt` / `pyproject.toml` via Git reference:

```text
core-lib @ git+https://github.com/jopedro-labs/core-lib.git@v0.1.1
```

---

## Modules & Tools

### `core_lib.logger`

ANSI-colored terminal logger. Outputs to stdout (or stderr for errors) with timestamps. No file persistence.

```python
from core_lib.logger import logger

logger.info("Starting job")
logger.success("Job completed")
logger.warning("Retrying...")
logger.error("Something failed", exception=ValueError("details"))
logger.section("Phase 1")       # bold header
logger.subsection("Step 1.1")   # bold subheader
logger.print("raw output")
```

You can also instantiate `Logger` directly if you need an isolated instance:

```python
from core_lib.logger import Logger

my_logger = Logger()
```

### `core_lib.file_utils`

Safe file reading utilities. Always returns a string — never raises.

```python
from core_lib.file_utils import load_file_content

content = load_file_content("/path/to/file.txt")  # "" if missing or unreadable
```

---

### `core_lib.gdrive`

Google Drive client using OAuth2 and the **Google Drive API v3**. Requires the `[gdrive]` extra.

**Underlying API & Dependencies:**
* **API Version:** Google Drive API v3 (`https://www.googleapis.com/discovery/v1/apis/drive/v3/rest`)
* **Python Client Library:** `google-api-python-client >= 2.0`
* **Authentication:** `google-auth >= 2.0`, `google-auth-oauthlib >= 1.0`
* **Scopes:** `https://www.googleapis.com/auth/drive`

**Automated API Monitoring & Gemini Revision Advisor (`gdrive_bot.yml`):**
* **Schedule:** Runs automatically every Monday and Thursday at 20:00 UTC (and supports manual `workflow_dispatch` with optional `force_advisor` test flag).
* **Deterministic Structural Diff First:** Compares full Discovery JSON documents (`scripts/gdrive_diff.py`), calculating exact deltas across methods, parameters, types, enums, and schemas to establish an authoritative baseline impact level (`LOW`, `MEDIUM`, `HIGH`).
* **Gemini AI Revision Advisor:** When an API revision change is detected, the agent (`scripts/gemini_gdrive_advisor.py`) analyzes the deterministic delta against the active methods in `core_lib/gdrive/` using the official `google-genai` SDK (`gemini-2.5-flash`), enforcing anti-hallucination guardrails and authority ceiling rules.
* **Refined GitHub Issues & Aligned Discord Alerts:** Generates an actionable, structured Markdown report directly in the GitHub Issue and sends aligned Discord notifications sharing the same severity and executive summary.
* **State Persistence & Resilience:** Persists Discovery states and revision numbers in the `bot-state` branch with automated rebase-retry loops before issue creation. Can also be executed locally:
  ```bash
  python scripts/gdrive_update_bot.py
  python scripts/gemini_gdrive_advisor.py
  ```

**Environment variables (optional — can be overridden per instance):**

| Variable                  | Default            | Description                         |
|---------------------------|--------------------|-------------------------------------|
| `GDRIVE_CREDENTIALS_PATH` | `credentials.json` | Path to the OAuth2 credentials file |
| `GDRIVE_TOKEN_PATH`       | `token.json`       | Path to the token file              |
| `GDRIVE_DATA_FOLDER_ID`   | `None`             | Default target folder ID            |

```python
from core_lib.gdrive import GDriveService, sanitize_gdrive_folder_id

# uses env vars or defaults
drive = GDriveService()

# or inject explicitly
drive = GDriveService(
    credentials_path="/secrets/credentials.json",
    token_path="/secrets/token.json",
    folder_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
)

drive.verify_folder_access()
drive.upload_file("report.csv", overwrite=True)
drive.download_file("report.csv", destination_path="/tmp/report.csv")
drive.list_files()
drive.backup_file("data.db")
drive.sync_files(["a.csv", "b.csv"], direction="push")
drive.get_latest_file_id(prefix="finances")
drive.download_latest_file(destination_path="finances.db", prefix="finances")
drive.get_file_modified_time("xtb_screenshot.png")
```

---

### `core_lib.discord`

Discord notification client supporting both Bot API (with dynamic channel targeting) and Webhook URLs. Requires the `[discord]` extra.

**Features:**
* **Dynamic Channel Targeting:** Send messages or embeds to specific channels dynamically using a Discord Bot Token (`channel_id` argument)
* **Webhook Fallback:** Support for traditional fixed-channel Webhook URLs
* **Rate-Limit Awareness:** Explicit handling of HTTP 429 responses with `retry_after` extraction
* **Context Manager Support:** Clean resource management using `with` statements

```python
from core_lib.discord import DiscordNotifier, DiscordNotificationError

# Using a Bot Token for dynamic channel targeting
try:
    with DiscordNotifier(bot_token="YOUR_BOT_TOKEN") as notifier:
        notifier.send_message(
            content="🚨 **Alert**: Automated job completed successfully.",
            channel_id="123456789012345678"
        )
except DiscordNotificationError as e:
    print(f"Failed to notify: {e}")

# Using a traditional Webhook URL
notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/...")
notifier.send_message(content="Hello from core-lib!")
notifier.close()
```

---

### Autonomous Quality Assurance & Test Gap Evaluation Agent

An internal developer utility (`scripts/quality_eval_agent.py`) powered by Gemini AI that acts as an autonomous quality assurance auditor within the repository.

**Core Validation Pillars Evaluated:**
1. **Unit Tests:** Isolated verification and mocking via `pytest`.
2. **Integration Tests:** Component and adapter interaction verification.
3. **Static Code Analysis:** Type safety (`mypy`) and linting (`ruff`).
4. **Mutation Testing Readiness:** Assessment of test suite robustness against code changes.
5. **Black-Box Verification:** Functional and behavioral validation.

**Execution:**
```bash
make quality-eval-agent
```

The agent automatically executes the test suite with coverage, gathers repository context, analyzes coverage gaps and validation metrics via the configured Gemini model (`GEMINI_MODEL`), and generates a structured markdown report under `reports/validation_gap_report.md`.

---

## Requirements

- Python >= 3.10
- Core utilities (logging, file I/O): No external dependencies.
- Google Drive extra (`[gdrive]`): Requires Google API client libraries (`google-api-python-client`, `google-auth`, `google-auth-oauthlib`).
- Discord extra (`[discord]`): Requires `requests`.
- AI Advisors & Evaluation Agents: Requires `google-genai`, `python-dotenv`, `pytest-cov`, and an active `GEMINI_API_KEY`.

---

## Development

```bash
git clone https://github.com/jopedro-labs/core-lib.git
cd core-lib
make install
```

Run all checks (lint, types, tests): 

```bash
make check
```

Individual commands:

| Command                   | Description                              |
|---------------------------|------------------------------------------|
| `make lint`               | Lint with ruff                           |
| `make type`               | Type check with mypy                     |
| `make test`               | Run tests with pytest                    |
| `make quality-eval-agent` | Run AI quality audit & test gap analysis |
| `make check`              | Run all three in sequence                |

---

## License

Distributed under the MIT License.

Developed and maintained by **João Pedro** ([@JoPedro15](https://github.com/JoPedro15)).

> *Fueled by Espresso, CrossFit WODs, and powered by Gemini AI.* ☕🏋️‍♂️🤖
