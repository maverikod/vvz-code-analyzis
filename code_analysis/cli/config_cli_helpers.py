"""
Helpers for config CLI: DB path, process checks, server stop, worker flags.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _indexing_worker_enabled(args: argparse.Namespace) -> Optional[bool]:
    """Resolve indexing worker enabled from CLI (None = do not override)."""
    if hasattr(args, "indexing_worker_disabled") and args.indexing_worker_disabled:
        return False
    if hasattr(args, "indexing_worker_enabled") and args.indexing_worker_enabled:
        return True
    return None


def _file_watcher_enabled(args: argparse.Namespace) -> Optional[bool]:
    """Resolve file watcher enabled from CLI (None = do not override)."""
    if hasattr(args, "file_watcher_disabled") and args.file_watcher_disabled:
        return False
    if hasattr(args, "file_watcher_enabled") and args.file_watcher_enabled:
        return True
    return None


def _docs_indexing_enabled(args: argparse.Namespace) -> Optional[bool]:
    """Resolve docs_indexing.enabled from CLI (None = use generator default False)."""
    if getattr(args, "code_analysis_docs_indexing_disabled", False):
        return False
    if getattr(args, "code_analysis_docs_indexing_enabled", False):
        return True
    return None


def _docs_indexing_vectorize(args: argparse.Namespace) -> Optional[bool]:
    """Resolve docs_indexing.vectorize from CLI (None = default False in generated block)."""
    if getattr(args, "code_analysis_docs_indexing_no_vectorize", False):
        return False
    if getattr(args, "code_analysis_docs_indexing_vectorize", False):
        return True
    return None


def _stop_server(config_path: Path) -> bool:
    """Stop code-analysis server and workers. Return True if stopped or already stopped."""
    try:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "code_analysis.cli.server_manager_cli",
                "--config",
                str(config_path),
                "stop",
            ],
            capture_output=True,
            timeout=30,
            text=True,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False
