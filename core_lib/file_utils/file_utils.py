"""Utility functions for safe file input/output operations."""

from __future__ import annotations

from pathlib import Path

from core_lib.logger import logger


def load_file_content(filepath: Path | str) -> str:
    """Safely reads a text file if it exists and is accessible.

    Returns the content as a string, or an empty string if the file
    does not exist, is not a file, or fails to read.
    """
    path = Path(filepath)

    if not path.exists():
        return ""

    if not path.is_file():
        logger.warning(f"[file utils] Path is not a valid file: '{path}'.")
        return ""

    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"[file utils] Failed to read file '{path}'", exception=e)
        return ""
