"""Argparse tests for postgres_setup_from_env_config.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "postgres_setup_from_env_config.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Return run."""
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_config_after_subcommand_is_accepted() -> None:
    """Verify test config after subcommand is accepted."""
    result = _run(
        "set-superuser-password",
        "--config",
        "/no/such/casmgr-config.json",
    )
    combined = f"{result.stdout}\n{result.stderr}"
    assert "unrecognized arguments" not in combined
    assert "not found" in combined


def test_config_before_subcommand_is_accepted() -> None:
    """Verify test config before subcommand is accepted."""
    result = _run(
        "--config",
        "/no/such/casmgr-config.json",
        "set-superuser-password",
    )
    combined = f"{result.stdout}\n{result.stderr}"
    assert "unrecognized arguments" not in combined
    assert "not found" in combined
