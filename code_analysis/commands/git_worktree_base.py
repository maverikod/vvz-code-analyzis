"""Shared helpers for git working-tree MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, cast

from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.git_integration import is_git_available, is_git_repository
from code_analysis.core.git_remote_ops import (
    GIT_NOT_A_REPO,
    GIT_NOT_AVAILABLE,
    git_remote_error_result,
    run_git_subprocess,
)

LOCAL_GIT_TIMEOUT_SECONDS = 30.0


def string_list(value: Optional[Sequence[str]]) -> List[str]:
    """Return non-empty strings from an optional sequence."""
    if value is None:
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def validation_error(message: str, field: str) -> ErrorResult:
    """Build a validation ErrorResult with a string code."""
    return ErrorResult(
        message=message,
        code=cast(Any, "VALIDATION_ERROR"),
        details={"field": field},
    )


class GitWorktreeCommand(BaseMCPCommand):
    """Shared helpers for local working-tree git commands."""

    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"

    def _resolve_git_root_or_error(
        self,
        project_id: str,
    ) -> tuple[Any, Optional[ErrorResult]]:
        """Resolve project root and verify local git availability."""
        root = self._resolve_project_root(project_id)
        if not is_git_available():
            return None, git_remote_error_result(
                GIT_NOT_AVAILABLE, "git executable is not available", {}
            )
        if not is_git_repository(root):
            return None, git_remote_error_result(
                GIT_NOT_A_REPO,
                f"{root} is not a git repository",
                {"root": str(root)},
            )
        return root, None

    def _run_local_git(
        self,
        project_id: str,
        args: List[str],
        *,
        error_code: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[tuple[str, str]], Optional[ErrorResult]]:
        """Run a local git command after project and repository checks."""
        root, error = self._resolve_git_root_or_error(project_id)
        if error is not None:
            return None, error
        returncode, stdout, stderr, timed_out = run_git_subprocess(
            ["git", *args],
            cwd=root,
            env=None,
            timeout_seconds=LOCAL_GIT_TIMEOUT_SECONDS,
        )
        if timed_out:
            return None, git_remote_error_result(
                f"{error_code}_TIMEOUT",
                f"{action} exceeded timeout of {LOCAL_GIT_TIMEOUT_SECONDS:.0f} seconds",
                details or {},
            )
        if returncode != 0:
            payload = dict(details or {})
            payload["stderr"] = stderr.strip()
            return None, git_remote_error_result(
                error_code,
                f"{action} failed with exit code {returncode}",
                payload,
            )
        return (stdout, stderr), None
