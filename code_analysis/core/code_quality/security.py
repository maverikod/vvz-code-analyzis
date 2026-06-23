"""
Security findings via bandit, run through the server interpreter.

Read-only static scan; mirrors the ``(success, error_message, errors)`` contract
of the other quality helpers. ``success`` is True only when bandit reports no
findings; each finding is rendered as a single line carrying severity and
confidence. A missing tool yields ``"Bandit not installed"`` (the
comprehensive_analysis hard-fail contract probes availability separately).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from .tool_runtime import module_missing, run_quality_tool

logger = logging.getLogger(__name__)


def check_with_bandit(
    file_path: Path, config_file: Optional[Path] = None
) -> Tuple[bool, Optional[str], List[str]]:
    """Run bandit on a single file and return its findings.

    Args:
        file_path: Python file to scan.
        config_file: Optional bandit config (``-c``); INI/YAML/TOML per bandit.
    """
    try:
        args = ["-f", "json"]
        if config_file is not None:
            args += ["-c", str(config_file)]
        args.append(str(file_path))
        result = run_quality_tool("bandit", args, timeout=60)

        if module_missing(result.stderr, "bandit"):
            logger.warning("Bandit module not importable from server interpreter")
            return (False, "Bandit not installed", [])

        # bandit prints JSON to stdout regardless of exit code (0 = no issues,
        # 1 = issues found). Parse it rather than trusting the return code.
        stdout = result.stdout or ""
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            msg = (
                result.stderr or "bandit produced no parseable JSON output"
            ).strip()
            return (False, msg, [])

        findings = payload.get("results", []) or []
        if not findings:
            return (True, None, [])

        errors: List[str] = []
        for f in findings:
            line = f.get("line_number", "?")
            test_id = f.get("test_id", "?")
            sev = f.get("issue_severity", "?")
            conf = f.get("issue_confidence", "?")
            text = (f.get("issue_text") or "").strip()
            errors.append(f"L{line}: [{test_id} severity={sev} confidence={conf}] {text}")
        return (False, f"bandit found {len(errors)} security issue(s)", errors)
    except subprocess.TimeoutExpired:
        logger.warning("Bandit scan timed out")
        return (False, "Bandit scan timed out", [])
    except OSError as exc:
        logger.warning("Error running bandit: %s", exc)
        return (False, str(exc), [])
