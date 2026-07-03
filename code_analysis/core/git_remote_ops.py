"""Shared helpers for project-scoped git remote operations (C-014, C-015, C-016).

Used by git_fetch, git_pull, and git_push. Remote-timeout resolution is
delegated entirely to
code_analysis.core.project_git.remote_timeout.get_remote_timeout_seconds_from_config;
this module defines no timeout default of its own.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, cast

from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.core.project_git.remote_timeout import (
    get_remote_timeout_seconds_from_config,
)

GIT_REMOTE_NOT_CONFIGURED = "GIT_REMOTE_NOT_CONFIGURED"
GIT_CONFLICT = "GIT_CONFLICT"
GIT_PROTECTED_BRANCH = "GIT_PROTECTED_BRANCH"
GIT_FORCE_PUSH_DISABLED = "GIT_FORCE_PUSH_DISABLED"
GIT_REMOTE_TIMEOUT = "GIT_REMOTE_TIMEOUT"
GIT_NOT_A_REPO = "GIT_NOT_A_REPO"
GIT_NOT_AVAILABLE = "GIT_NOT_AVAILABLE"


def git_remote_error_result(
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> ErrorResult:
    """
    Build an ErrorResult with a string application error code.

    Args:
        code: String application-level outcome code.
        message: Human-readable error message.
        details: Optional structured error details.

    Returns:
        ErrorResult carrying the string application outcome code. The adapter
        types ErrorResult.code as an int JSON-RPC code, while this capability
        block uses string outcome codes.
    """
    return ErrorResult(message=message, code=cast(Any, code), details=details or {})


def load_git_remote_config(config_data: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Load remote git configuration from the raw server config.

    Args:
        config_data: Full raw config dict as returned by load_raw_config or
            BaseMCPCommand._get_raw_config.

    Returns:
        Dict with remote_enabled, ssh_key_path, known_hosts_path,
        protected_branches, allow_force_push, and remote_timeout_seconds.
        remote_timeout_seconds is resolved only by delegating config_data
        unchanged to get_remote_timeout_seconds_from_config, which applies the
        canonical default of 30 seconds when unset or invalid.
    """
    git_section: Mapping[str, Any] = {}
    section = (
        config_data.get("code_analysis") if isinstance(config_data, Mapping) else None
    )
    if isinstance(section, Mapping):
        candidate = section.get("git")
        if isinstance(candidate, Mapping):
            git_section = candidate
    protected = git_section.get("protected_branches")
    protected_branches = (
        [str(branch) for branch in protected] if isinstance(protected, list) else []
    )
    remote_timeout_seconds = float(get_remote_timeout_seconds_from_config(config_data))
    return {
        "remote_enabled": bool(git_section.get("remote_enabled")),
        "ssh_key_path": git_section.get("ssh_key_path"),
        "known_hosts_path": git_section.get("known_hosts_path"),
        "protected_branches": protected_branches,
        "allow_force_push": bool(git_section.get("allow_force_push")),
        "remote_timeout_seconds": remote_timeout_seconds,
    }


def evaluate_push_guards(
    target_branch: str,
    *,
    protected_branches: List[str],
    protected_override: bool,
    force: bool,
    allow_force_push_config: bool,
) -> Optional[Tuple[str, str]]:
    """
    Evaluate protected-branch and force-push guards for a push.

    Protected-branch is checked before force-push, so a push that both targets
    a protected branch and requests force reports the protected-branch
    rejection first.

    Args:
        target_branch: Branch being pushed.
        protected_branches: Configured protected branch names.
        protected_override: Explicit caller override for a protected branch.
        force: Whether the push requests force.
        allow_force_push_config: Whether configuration permits force push.

    Returns:
        None when push may proceed, otherwise (outcome_code, message).
    """
    if target_branch in protected_branches and not protected_override:
        return (
            GIT_PROTECTED_BRANCH,
            f"Push to protected branch {target_branch!r} rejected: "
            "no protected_override supplied",
        )
    if force and not allow_force_push_config:
        return (
            GIT_FORCE_PUSH_DISABLED,
            "Force push rejected: allow_force_push is not enabled in configuration",
        )
    return None


def build_full_subprocess_env(
    git_config: Mapping[str, Any],
) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, Any]]]:
    """
    Build the full subprocess environment for an authenticated git call.

    Wraps build_git_ssh_environment(git_config), merging its GIT_SSH_COMMAND
    overlay into a copy of the current process environment so PATH and other
    variables remain present.

    Args:
        git_config: The code_analysis.git configuration mapping.

    Returns:
        (env, None) on success, or (None, error) when SSH auth configuration
        is invalid.
    """
    from code_analysis.core.git_ssh_auth import build_git_ssh_environment

    overlay, error = build_git_ssh_environment(git_config)
    if error is not None:
        return None, error
    full_env = dict(os.environ)
    if overlay:
        full_env.update(overlay)
    return full_env, None


def run_git_subprocess(
    args: List[str],
    *,
    cwd: Path,
    env: Optional[Dict[str, str]],
    timeout_seconds: float,
) -> Tuple[Optional[int], str, str, bool]:
    """
    Run a git subprocess bounded by timeout_seconds.

    No in-operation retry is performed. This function performs its own
    subprocess.run call because it must accept a caller-supplied env for SSH
    authentication.

    Args:
        args: Full argv, e.g. ["git", "fetch", "origin"].
        cwd: Working directory, the resolved project root.
        env: Environment mapping for the subprocess, or None to inherit.
        timeout_seconds: Maximum seconds before timeout.

    Returns:
        Tuple (returncode, stdout, stderr, timed_out).
    """
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr, False
    except subprocess.TimeoutExpired as exc:
        raw_stdout = exc.stdout
        raw_stderr = exc.stderr
        stdout = (
            raw_stdout.decode() if isinstance(raw_stdout, bytes) else (raw_stdout or "")
        )
        stderr = (
            raw_stderr.decode() if isinstance(raw_stderr, bytes) else (raw_stderr or "")
        )
        return None, stdout, stderr, True
