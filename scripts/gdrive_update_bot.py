"""
Automated GDrive Update Bot.

Queries Google's public discovery endpoint to detect Google Drive API revisions and changes.
Prepares previous and current discovery/revision files for deterministic diffing in runner.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request
import uuid

# Ensure workspace root is in sys.path when invoked directly
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from core_lib.logger import logger

DISCOVERY_URL = "https://www.googleapis.com/discovery/v1/apis/drive/v3/rest"
STATE_DIR = Path(".github/api-revisions")
STATE_FILE = STATE_DIR / "gdrive-revision.json"
PREVIOUS_STATE_FILE = STATE_DIR / "gdrive-revision.previous.json"
DISCOVERY_FILE = STATE_DIR / "drive-v3-discovery.json"
PREVIOUS_DISCOVERY_FILE = STATE_DIR / "drive-v3-discovery.previous.json"

TIMEOUT = 30
MAX_RETRIES = 3
RETRIES_DELAY = 5


def fetch_discovery_data() -> tuple[dict[str, str], dict[str, Any]]:
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
                    raw_content = response.read().decode("utf-8")
                    data = json.loads(raw_content)
                    metadata = {
                        "name": str(data.get("name", "unknown")),
                        "version": str(data.get("version", "unknown")),
                        "revision": str(data.get("revision", "unknown")),
                        "title": str(data.get("title", "Google Drive API")),
                    }
                    return metadata, data
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


def stage_runner_files(metadata: dict[str, str], full_discovery: dict[str, Any]) -> None:
    """Preserves existing state as previous and stages newly fetched state in runner filesystem."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if DISCOVERY_FILE.exists():
        shutil.copyfile(DISCOVERY_FILE, PREVIOUS_DISCOVERY_FILE)
    if STATE_FILE.exists():
        shutil.copyfile(STATE_FILE, PREVIOUS_STATE_FILE)

    DISCOVERY_FILE.write_text(json.dumps(full_discovery, indent=2), encoding="utf-8")
    STATE_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def write_github_output(key: str, value: str) -> None:
    """Writes a key=value pair to $GITHUB_OUTPUT using EOF delimiter for multiline safety."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        delimiter = f"EOF_{uuid.uuid4().hex}"
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def main() -> None:
    """Main execution entry point for the GDrive Update Bot."""
    logger.info("[gdrive update bot] Running Google Drive API Discovery check...")
    try:
        current_metadata, full_discovery = fetch_discovery_data()
        current_revision = current_metadata["revision"]
        logger.info(
            f"[gdrive update bot] API: {current_metadata['title']} "
            f"({current_metadata['name']}/{current_metadata['version']})"
        )
        logger.info(f"[gdrive update bot] Current Revision: {current_revision}")

        previous_revision = load_previous_revision()
        logger.info(f"[gdrive update bot] Previous Recorded Revision: {previous_revision}")

        write_github_output("previous_revision", previous_revision or "none")
        write_github_output("current_revision", current_revision)

        stage_runner_files(current_metadata, full_discovery)

        if previous_revision is not None and current_revision != previous_revision:
            logger.error(f"[gdrive update bot] Revision changed: {previous_revision} -> {current_revision}")
            write_github_output("result", "revision_changed")
            sys.exit(2)  # exit 2 = revision changed

        write_github_output("result", "ok")
        logger.success("[gdrive update bot] No API revision change detected.")

    except Exception as e:
        logger.error(f"[gdrive update bot] Monitor execution failed: {e}")
        write_github_output("result", "error")
        sys.exit(1)  # exit 1 = network/parse error


if __name__ == "__main__":
    main()
