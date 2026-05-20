"""
casmgr sessions/locks subcommand help (subprocess smoke).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
import sys


def test_casmgr_sessions_help_exits_zero() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_analysis.cli.server_manager_cli",
            "sessions",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "sessions" in proc.stdout.lower() or "usage" in proc.stdout.lower()


def test_casmgr_locks_help_exits_zero() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_analysis.cli.server_manager_cli",
            "locks",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "locks" in proc.stdout.lower() or "usage" in proc.stdout.lower()
