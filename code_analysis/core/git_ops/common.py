"""Shared helpers for the local git working-tree and history mutation operations
in code_analysis/core/git_ops/: a no-shell subprocess runner around git, a
local-repository availability check, and project-root path confinement for
path-consuming operations (stage, unstage, restore). Path confinement delegates
to the canonical project-scoped guard in
code_analysis/core/project_git/path_confinement.py. These operations act only
on the resolved local repository and never contact a remote.
"""

import os
import subprocess
from pathlib import Path

from code_analysis.core.project_git.path_confinement import confine_project_git_path


def run_git(
    root_dir: str, args: list[str], timeout_seconds: int = 60
) -> tuple[int, str, str]:
    """Run `git -C <root_dir> <args>` as a subprocess with no shell.

    Args:
        root_dir: Absolute path to the git working tree to operate on.
        args: The git subcommand and its arguments, e.g. ["add", "--", "file.py"].
        timeout_seconds: Local subprocess-safety timeout bound in seconds. This
            is a local safety bound only, not the C-023 remote-operation
            timeout; these operations never contact a remote.

    Returns:
        A tuple (returncode, stdout, stderr) with stdout and stderr decoded
        as text.

    Raises:
        subprocess.TimeoutExpired: if the git process does not complete
            within timeout_seconds.
    """
    completed = subprocess.run(
        ["git", "-C", root_dir] + list(args),
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return completed.returncode, completed.stdout, completed.stderr


def ensure_local_repo(root_dir: str) -> dict | None:
    """Confirm git is available and root_dir is a git work tree.

    Args:
        root_dir: Absolute path to the candidate git working tree.

    Returns:
        None when git is available and root_dir is a git work tree.
        Otherwise a failure outcome dict:
        {"success": False, "code": "GIT_NOT_AVAILABLE", "message": str} when
        the git executable is not available, or
        {"success": False, "code": "GIT_NOT_A_REPO", "message": str} when
        root_dir is not a git work tree.
    """
    try:
        availability = subprocess.run(
            ["git", "--version"],
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "success": False,
            "code": "GIT_NOT_AVAILABLE",
            "message": "git executable is not available on this system.",
        }
    if availability.returncode != 0:
        return {
            "success": False,
            "code": "GIT_NOT_AVAILABLE",
            "message": "git executable is not available on this system.",
        }
    returncode, stdout, _stderr = run_git(
        root_dir, ["rev-parse", "--is-inside-work-tree"]
    )
    if returncode != 0 or stdout.strip() != "true":
        return {
            "success": False,
            "code": "GIT_NOT_A_REPO",
            "message": f"{root_dir} is not a git work tree.",
        }
    return None


def confine_relative_path(
    root_dir: str, rel_path: str
) -> tuple[str | None, dict | None]:
    """Resolve a project-relative path under root_dir, rejecting paths outside it.

    Revision identifiers (branch names, commit refs, tag names) must never be
    passed to this function: refs are opaque and are not subject to path
    confinement.

    Delegates the confinement decision to the canonical guard
    confine_project_git_path (code_analysis/core/project_git/path_confinement.py)
    and adapts its (Path, ErrorResult) result to this module's (str, dict)
    outcome convention; it does not reimplement any path-escape check itself.

    Args:
        root_dir: Absolute path to the project root / git working tree.
        rel_path: A project-relative path supplied by the caller.

    Returns:
        A tuple (absolute_path_str, None) when the resolved path is inside
        root_dir. Otherwise (None, failure_outcome) where failure_outcome is
        {"success": False, "code": "GIT_PATH_OUTSIDE_PROJECT", "message": str}.
    """
    resolved_path, error = confine_project_git_path(Path(root_dir), rel_path)
    if error is not None:
        return None, {
            "success": False,
            "code": "GIT_PATH_OUTSIDE_PROJECT",
            "message": error.message,
        }
    return str(resolved_path), None
