# core-lib

![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-58a6ff?style=flat-square)
![CI](https://github.com/jopedro-labs/core-lib/actions/workflows/ci.yml/badge.svg?branch=main)
![Monitor GDrive API](https://github.com/jopedro-labs/core-lib/actions/workflows/gdrive_bot.yml/badge.svg)
<br />
![Linter](https://img.shields.io/badge/linter-Ruff-000000?style=flat-square&logo=python&logoColor=white)
![Type Check](https://img.shields.io/badge/types-mypy%20strict-2A6DB2?style=flat-square&logo=python&logoColor=white)
![GNU Make](https://img.shields.io/badge/env-GNU%20Make-active?style=flat-square&logo=gnu-make&logoColor=white)
![MIT License](https://img.shields.io/badge/license-MIT-607D8B?style=flat-square)

Shared Python support library. Provides common utilities (logging, file I/O) and service integrations for internal projects.

---

## Installation

Add to your project's `requirements.txt` or `pyproject.toml`:

```txt
# requirements.txt — core utilities only
core-lib @ git+https://github.com/jopedro-labs/core-lib.git

# with Google Drive support
core-lib[gdrive] @ git+https://github.com/jopedro-labs/core-lib.git
```

```toml
# pyproject.toml
dependencies = [
    "core-lib @ git+https://github.com/jopedro-labs/core-lib.git",
    # or with Google Drive support:
    # "core-lib[gdrive] @ git+https://github.com/jopedro-labs/core-lib.git",
]
```

Pin to a specific version:

```txt
core-lib @ git+https://github.com/jopedro-labs/core-lib.git@v0.1.0
```

---

## Modules

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
* **Scopes:** `https://www.googleapis.com/auth/drive.file`

**Automated API Monitoring (GDrive Update Bot):**
* **Schedule:** Runs automatically every Monday at 08:00 UTC (and supports manual workflow dispatch).
* **Mechanism:** Queries Google's public Discovery Service using standard libraries (`scripts/gdrive_update_bot.py`) with built-in retry logic and linear backoff.
* **Resilience & Alerts:** Persists revision states locally (`.github/api-revisions/gdrive-revision.json`), committing updates on success and opening targeted GitHub Issues if a breaking API revision change or network failure occurs. Can also be run manually: `python scripts/gdrive_update_bot.py`.

**Environment variables (optional — can be overridden per instance):**

| Variable | Default | Description |
|---|---|---|
| `GDRIVE_CREDENTIALS_PATH` | `credentials.json` | Path to the OAuth2 credentials file |
| `GDRIVE_TOKEN_PATH` | `token.json` | Path to the token file |
| `GDRIVE_DATA_FOLDER_ID` | `None` | Default target folder ID |

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
```

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

| Command       | Description                    |
|---------------|--------------------------------|
| `make lint`   | Lint with ruff                 |
| `make type`   | Type check with mypy           |
| `make test`   | Run tests with pytest          |
| `make check`  | Run all three in sequence      |

---

## License

Distributed under the MIT License.

Developed and maintained by **João Pedro** ([@JoPedro15](https://github.com/JoPedro15)).

> *Fueled by Espresso, CrossFit WODs, and powered by Gemini AI.* ☕🏋️‍♂️🤖
