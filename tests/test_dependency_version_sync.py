"""Dependency version metadata must stay synchronized."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_dependency_versions_are_synchronized() -> None:
    """Verify generated dependency version literals match pyproject.toml."""
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "sync_dependency_versions.py"),
            "--repo-root",
            str(root),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
