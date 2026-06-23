"""
Formatting-drift checks via black and isort, run through the server interpreter.

Both are read-only ``--check`` runs (no file is ever rewritten; the existing
``format_code_with_black`` is the mutating path and is unrelated). They mirror
the ``lint_with_flake8`` / ``type_check_with_mypy`` contract:
``(success, error_message, errors)`` where ``success`` is True only when the file
has no drift, and a missing tool yields ``"<Tool> not installed"`` (the
comprehensive_analysis hard-fail contract probes availability separately).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from .tool_runtime import module_missing, run_quality_tool

logger = logging.getLogger(__name__)


def check_with_black(file_path: Path) -> Tuple[bool, Optional[str], List[str]]:
    """Report black formatting drift for a single file (``black --check --diff``)."""
    try:
        result = run_quality_tool(
            "black", ["--check", "--diff", str(file_path)], timeout=30
        )
        if module_missing(result.stderr, "black"):
            logger.warning("Black module not importable from server interpreter")
            return (False, "Black not installed", [])

        if result.returncode == 0:
            return (True, None, [])

        # rc==1 → would reformat. black prints "would reformat <file>" to stderr
        # and the unified diff to stdout; surface both as findings.
        if result.returncode == 1:
            errors = [
                ln
                for ln in (result.stderr.splitlines() + result.stdout.splitlines())
                if ln.strip()
            ]
            return (False, "black would reformat the file", errors)

        # rc >= 123 → black internal error (e.g. syntax error in target).
        msg = (
            result.stderr or f"black failed with exit code {result.returncode}"
        ).strip()
        return (False, msg, [ln for ln in result.stderr.splitlines() if ln.strip()])
    except subprocess.TimeoutExpired:
        logger.warning("Black check timed out")
        return (False, "Black check timed out", [])
    except OSError as exc:
        logger.warning("Error running black: %s", exc)
        return (False, str(exc), [])


def check_with_isort(file_path: Path) -> Tuple[bool, Optional[str], List[str]]:
    """Report import-order drift for a single file (``isort --check-only --diff``)."""
    try:
        result = run_quality_tool(
            "isort", ["--check-only", "--diff", str(file_path)], timeout=30
        )
        if module_missing(result.stderr, "isort"):
            logger.warning("Isort module not importable from server interpreter")
            return (False, "Isort not installed", [])

        if result.returncode == 0:
            return (True, None, [])

        # isort prints "ERROR: <file> Imports are incorrectly sorted..." to stderr
        # and the diff to stdout.
        errors = [
            ln
            for ln in (result.stderr.splitlines() + result.stdout.splitlines())
            if ln.strip()
        ]
        return (False, "imports are incorrectly sorted/formatted", errors)
    except subprocess.TimeoutExpired:
        logger.warning("Isort check timed out")
        return (False, "Isort check timed out", [])
    except OSError as exc:
        logger.warning("Error running isort: %s", exc)
        return (False, str(exc), [])
