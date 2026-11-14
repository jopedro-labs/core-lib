"""
Automated GDrive Update Bot.

Queries Google's public discovery endpoint to detect Google Drive API revisions and changes.
Uses Python's standard library for core requests and core_lib.logger for structured output.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from core_lib.logger import logger

DISCOVERY_URL = "https://www.googleapis.com/discovery/v1/apis/drive/v3/rest"
STATE_FILE = Path(".github/api-revisions/gdrive-revision.json")
TIMEOUT = 30
MAX_RETRIES = 3
RETRIES_DELAY = 5


def fetch_discovery_data() -> dict[str, str]:
    """Fetches discovery JSON with retry logic and 30s timeout."""
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                DISCOVERY_URL,
                headers={"User-Agent": "jopedro-labs-monitor/1.0"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return {
                        "name": str(data.get("name", "unknown")),
                        "version": str(data.get("version", "unknown")),
                        "revision": str(data.get("revision", "unknown")),
                        "title": str(data.get("title", "Google Drive API")),
                    }
                raise RuntimeError(f"Unexpected HTTP status: {response.status}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as e:
            last_exc = e
            logger.warning(f"[gdrive update bot] Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRIES_DELAY * attempt)
    raise last_exc


def load_previous_revision() -> str | None:
    """Loads the previously recorded API revision from the state file."""
    if not STATE_FILE.exists():
        return None
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return state.get("revision")
    except Exception as e:
        logger.warning(f"[gdrive update bot] Could not parse state file: {e}")
        return None


def save_state(data: dict[str, str]) -> None:
    """Saves the current discovery data state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_github_output(key: str, value: str) -> None:
    """Writes a key=value pair to $GITHUB_OUTPUT if running in GitHub Actions."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def main() -> None:
    """Main execution entry point for the GDrive Update Bot."""
    logger.info("[gdrive update bot] Running Google Drive API Discovery check...")
    try:
        current_data = fetch_discovery_data()
        current_revision = current_data["revision"]
        logger.info(f"[gdrive update bot] API: {current_data['title']} ({current_data['name']}/{current_data['version']})")
        logger.info(f"[gdrive update bot] Current Revision: {current_revision}")

        previous_revision = load_previous_revision()
        logger.info(f"[gdrive update bot] Previous Recorded Revision: {previous_revision}")

        if previous_revision is not None and current_revision != previous_revision:
            logger.error(f"[gdrive update bot] Revision changed: {previous_revision} -> {current_revision}")
            save_state(current_data)
            write_github_output("result", "revision_changed")
            sys.exit(2)  # exit 2 = revision changed

        save_state(current_data)
        write_github_output("result", "ok")
        logger.success("[gdrive update bot] No API revision change detected.")

    except Exception as e:
        logger.error(f"[gdrive update bot] Monitor execution failed: {e}")
        write_github_output("result", "error")
        sys.exit(1)  # exit 1 = network/parse error


if __name__ == "__main__":
    main()