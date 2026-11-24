#!/usr/bin/env python3
"""Validation script to enforce AUDIT.md structural integrity and change-sync coherence."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# Ensure workspace root is in sys.path when invoked directly
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from core_lib.logger import logger

EXPECTED_SECTIONS: list[str] = [
    "## 1. Missing Local Files & Environment Setup",
    "## 2. Bugs & Code Fragilities",
    "## 3. Test Coverage Gaps",
]

MONITORED_PATHS: tuple[str, ...] = (
    "core_lib/",
    "scripts/",
    "pyproject.toml",
    ".github/workflows/",
)

CHECKBOX_PATTERN = re.compile(r"^-\s*\[([ xX])\]\s*\*\*(.*?)\*\*:")
MALFORMED_CHECKBOX_PATTERN = re.compile(r"^(?:-|\*)\s*\[[^ xX]\].*|^-\s*\[\s{2,}\].*")


def validate_structure(audit_path: Path) -> tuple[bool, int, int]:
    """Validates header structure and checkbox syntax in AUDIT.md.

    Returns:
        tuple of (is_valid, completed_count, open_count)
    """
    if not audit_path.exists():
        logger.error(f"Error: {audit_path} does not exist.")
        return False, 0, 0

    content = audit_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # 1. Verify required sections exist
    missing_sections = [sec for sec in EXPECTED_SECTIONS if sec not in content]
    if missing_sections:
        logger.error("Error: Missing required section headers in AUDIT.md:")
        for sec in missing_sections:
            logger.error(f"  - {sec}")
        return False, 0, 0

    # 2. Check for malformed checkbox markers
    malformed_lines: list[tuple[int, str]] = []
    completed_items = 0
    open_items = 0

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if MALFORMED_CHECKBOX_PATTERN.match(stripped):
            malformed_lines.append((idx, stripped))
            continue

        match = CHECKBOX_PATTERN.match(stripped)
        if match:
            state, _ = match.groups()
            if state in ("x", "X"):
                completed_items += 1
            else:
                open_items += 1

    if malformed_lines:
        logger.error("Error: Malformed checkbox syntax found in AUDIT.md:")
        for line_no, text in malformed_lines:
            logger.error(f"  Line {line_no}: {text}")
        return False, completed_items, open_items

    logger.info(
        f"AUDIT.md structure verified: {completed_items} completed items, "
        f"{open_items} open items."
    )
    return True, completed_items, open_items


def get_changed_files(base_ref: str | None = None) -> list[str]:
    """Retrieves changed files relative to base ref or unstaged/staged working tree."""
    cmd = ["git", "diff", "--name-only"]
    if base_ref:
        cmd.append(base_ref)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return files
    except Exception as e:
        logger.warning(f"Could not compute git diff ({e}).")
        return []


def validate_change_sync(base_ref: str | None = None, bypass: bool = False) -> bool:
    """Enforces that AUDIT.md is modified when monitored code paths are modified."""
    if bypass or os.getenv("BYPASS_AUDIT_SYNC") == "1":
        logger.info("Change-sync check bypassed via flag or BYPASS_AUDIT_SYNC env variable.")
        return True

    changed_files = get_changed_files(base_ref)
    if not changed_files:
        logger.info("No changed files detected for change-sync check.")
        return True

    code_changed = any(
        f.startswith(MONITORED_PATHS) or f == "pyproject.toml"
        for f in changed_files
    )
    audit_changed = "AUDIT.md" in changed_files

    if code_changed and not audit_changed:
        logger.error("Error: Repository code/workflows were modified without updating AUDIT.md.")
        logger.error("Modified files:")
        for f in changed_files:
            if f.startswith(MONITORED_PATHS) or f == "pyproject.toml":
                logger.error(f"  - {f}")
        logger.error("Please update AUDIT.md to reflect the changes, or set BYPASS_AUDIT_SYNC=1 if intentional.")
        return False

    logger.success("Change-sync check passed: AUDIT.md aligns with modified files.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validates AUDIT.md structural integrity and synchronization."
    )
    parser.add_argument(
        "--audit-file",
        type=Path,
        default=Path("AUDIT.md"),
        help="Path to AUDIT.md file.",
    )
    parser.add_argument(
        "--enforce-sync",
        action="store_true",
        help="Enforce that AUDIT.md is updated when monitored code paths change.",
    )
    parser.add_argument(
        "--base-ref",
        type=str,
        default=os.getenv("GITHUB_BASE_REF"),
        help="Base git reference or branch to compare against (e.g. origin/main).",
    )
    parser.add_argument(
        "--bypass-sync",
        action="store_true",
        help="Bypass change-sync enforcement.",
    )

    args = parser.parse_args()

    # 1. Structure & Syntax Validation
    struct_ok, _, _ = validate_structure(args.audit_file)
    if not struct_ok:
        return 1

    # 2. Change-Sync Validation (if requested or in PR mode)
    if args.enforce_sync:
        sync_ok = validate_change_sync(base_ref=args.base_ref, bypass=args.bypass_sync)
        if not sync_ok:
            return 1

    logger.success("AUDIT.md validation completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
