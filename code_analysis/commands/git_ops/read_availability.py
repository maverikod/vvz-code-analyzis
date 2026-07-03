"""
Uniform repository-resolution and availability-outcome protocol shared by
every read-only git operation (C-009, GitReadOps).

Before any read-only git operation reports its result, it resolves the
project's repository root and confirms the root is usable for git reads.
When the root is not a git repository, or is a git repository with no
commits yet, the operation returns a distinct, non-error availability
outcome that names the condition rather than raising as though the call
were malformed. This module defines that shared outcome and the
read-only subprocess runner used to detect it, so every read operation
in the read set applies the identical uniform outcome.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.core.git_integration import is_git_available, is_git_repository

GIT_NOT_AVAILABLE = "GIT_NOT_AVAILABLE"
GIT_NOT_A_REPO = "GIT_NOT_A_REPO"
GIT_NO_COMMITS = "GIT_NO_COMMITS"


def run_git_read(
    resolved_root: Path, args: List[str], timeout: int = 30
) -> Tuple[int, str, str]:
    """Run a read-only git subcommand against the resolved repository root.

    Args:
        resolved_root: The project root resolved per G-006, treated as
            the single repository under inspection.
        args: The git subcommand and its arguments, e.g.
            ["status", "--porcelain"]. Callers must pass only read-only
            git subcommands; this function does not enforce
            read-only-ness itself, it is the callers' contract.
        timeout: Seconds to wait for the git subprocess before treating
            the call as timed out. Defaults to 30.

    Returns:
        A tuple (returncode, stdout, stderr) from the git invocation.
        When the subprocess exceeds timeout, returns
        (124, "", "git operation timed out") instead of raising.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(resolved_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (124, "", "git operation timed out")


def check_read_availability(resolved_root: Path) -> Optional[Dict[str, Any]]:
    """Check whether the resolved repository is usable for git reads.

    Args:
        resolved_root: The project root resolved per G-006, treated as
            the single repository under inspection.

    Returns:
        None when the repository is usable for reads. Otherwise a
        non-error availability outcome dict with keys "success" (True),
        "available" (False), "reason" (one of GIT_NOT_AVAILABLE,
        GIT_NOT_A_REPO, GIT_NO_COMMITS), and "message" (a human-readable
        sentence naming the condition).
    """
    if not is_git_available():
        return {
            "success": True,
            "available": False,
            "reason": GIT_NOT_AVAILABLE,
            "message": "Git is not available on this system.",
        }
    if not is_git_repository(resolved_root):
        return {
            "success": True,
            "available": False,
            "reason": GIT_NOT_A_REPO,
            "message": "The resolved project root is not a git repository.",
        }
    returncode, _stdout, _stderr = run_git_read(
        resolved_root, ["rev-parse", "--verify", "HEAD"]
    )
    if returncode != 0:
        return {
            "success": True,
            "available": False,
            "reason": GIT_NO_COMMITS,
            "message": "The git repository has no commits yet.",
        }
    return None


def availability_success_result(outcome: Dict[str, Any]) -> SuccessResult:
    """Wrap a non-error availability outcome as a SuccessResult.

    Args:
        outcome: The availability outcome dict produced by
            check_read_availability.

    Returns:
        A SuccessResult wrapping the outcome dict as its data payload.
    """
    return SuccessResult(data=outcome)
