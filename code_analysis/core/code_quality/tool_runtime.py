"""
Shared runtime for code-quality tools (flake8, mypy, black, isort, bandit).

Every tool is resolved and run **via the server's own interpreter**
(``sys.executable -m <tool>``), never a bare binary on PATH. The bug class this
avoids: the server runs from a venv whose ``bin`` may not be on the subprocess
PATH, so a bare ``flake8`` lookup silently fails (FileNotFoundError) and the
check "degrades" to a false-clean result. Running ``python -m flake8`` uses the
exact interpreter the tool is installed against.

``is_tool_available`` is the single availability probe used by the
comprehensive_analysis hard-fail contract; results are cached per process.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# The quality tools this project knows how to run, each as an importable module.
QUALITY_TOOL_MODULES = ("flake8", "mypy", "black", "isort", "bandit")

# First dotted version token in a `--version` banner (handles all five tools'
# differing formats: "7.3.0 (...)", "mypy 1.20.2", "VERSION 6.1.0", etc.).
_VERSION_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")

_availability_cache: Dict[str, bool] = {}
_version_cache: Dict[str, Optional[str]] = {}


def sanitized_env() -> Dict[str, str]:
    """Process env with ``PYTHONPATH`` stripped.

    The server injects command paths into ``PYTHONPATH`` for child processes,
    and this project ships a ``code_analysis.commands.ast`` package that can
    shadow the stdlib ``ast`` module the tools import. Strip it for tool runs.
    """
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


def tool_command(tool: str, *args: str) -> List[str]:
    """Build a ``[python, -m, <tool>, *args]`` argv for the server interpreter."""
    return [sys.executable, "-m", tool, *args]


def module_missing(stderr: str, tool: str) -> bool:
    """True when stderr indicates the tool module is not installed."""
    if not stderr:
        return False
    low = stderr.lower()
    return (
        f"no module named {tool}" in low
        or f"no module named '{tool}'" in low
        or "/bin/python: no module named" in low
    )


def run_quality_tool(
    tool: str, args: List[str], *, timeout: int = 60
) -> subprocess.CompletedProcess:
    """Run ``python -m <tool> <args>`` with a sanitized env and a timeout."""
    return subprocess.run(
        tool_command(tool, *args),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=sanitized_env(),
    )


def is_tool_available(tool: str, *, use_cache: bool = True) -> bool:
    """True when ``python -m <tool> --version`` succeeds from the server interpreter.

    Result is cached per process (tools don't appear/disappear mid-run). This is
    the canonical probe for the hard-fail contract — NOT a PATH ``which``.
    """
    if use_cache and tool in _availability_cache:
        return _availability_cache[tool]
    available = False
    try:
        proc = run_quality_tool(tool, ["--version"], timeout=20)
        available = proc.returncode == 0 and not module_missing(proc.stderr, tool)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("availability probe for %s failed: %s", tool, exc)
        available = False
    _availability_cache[tool] = available
    return available


def reset_availability_cache(tool: Optional[str] = None) -> None:
    """Clear the availability + version caches (tests / after an image rebuild check)."""
    if tool is None:
        _availability_cache.clear()
        _version_cache.clear()
    else:
        _availability_cache.pop(tool, None)
        _version_cache.pop(tool, None)


def tool_version(tool: str, *, use_cache: bool = True) -> Optional[str]:
    """Parsed version string from ``python -m <tool> --version``, or None if absent."""
    if use_cache and tool in _version_cache:
        return _version_cache[tool]
    version: Optional[str] = None
    try:
        proc = run_quality_tool(tool, ["--version"], timeout=20)
        if proc.returncode == 0 and not module_missing(proc.stderr, tool):
            text = f"{proc.stdout or ''} {proc.stderr or ''}"
            m = _VERSION_RE.search(text)
            version = m.group(0) if m else None
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("version probe for %s failed: %s", tool, exc)
    _version_cache[tool] = version
    return version


def quality_tool_report(*, use_cache: bool = True) -> Dict[str, Dict[str, object]]:
    """Availability + version for every quality tool, keyed by tool name.

    Shape: ``{tool: {"available": bool, "version": str | None}}``. Used by the
    boot self-check and the ``health`` command so a missing/old tool is visible
    without shelling into the container.
    """
    report: Dict[str, Dict[str, object]] = {}
    for tool in QUALITY_TOOL_MODULES:
        available = is_tool_available(tool, use_cache=use_cache)
        report[tool] = {
            "available": available,
            "version": tool_version(tool, use_cache=use_cache) if available else None,
        }
    return report
