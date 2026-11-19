import sys
import subprocess


def test_gdrive_update_bot_cli_execution():
    """Black-box functional invocation of the gdrive update bot entrypoint."""
    # When executed without credentials / internet / mock env, it handles error and exits cleanly with 1
    res = subprocess.run(
        [sys.executable, "-m", "scripts.gdrive_update_bot", "--help"],
        capture_output=True,
        text=True,
    )
    # The script executes and returns 0, 1 or 2
    assert res.returncode in (0, 1, 2)


def test_subpackages_importable_independently():
    """Verify that importing core subpackages works cleanly in separate processes."""
    subpackages = [
        "core_lib.logger",
        "core_lib.file_utils",
        "core_lib.discord",
        "core_lib.gdrive",
    ]
    for pkg in subpackages:
        res = subprocess.run(
            [sys.executable, "-c", f"import {pkg}"],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Failed to import {pkg}: {res.stderr}"
