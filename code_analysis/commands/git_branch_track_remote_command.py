"""git_branch_track_remote MCP command: create a local tracking branch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.git_integration import is_git_available, is_git_repository
from code_analysis.core.git_remote_ops import (
    GIT_NOT_A_REPO,
    GIT_NOT_AVAILABLE,
    git_remote_error_result,
    run_git_subprocess,
)


class GitBranchTrackRemoteCommand(BaseMCPCommand):
    """MCP command creating a local branch that tracks a remote branch."""

    name = "git_branch_track_remote"
    version = "1.0.0"
    descr = "Create a local branch tracking a remote-tracking branch."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_track_remote"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote_branch": {"type": "string"},
                "local_branch": {"type": "string"},
                "checkout": {"type": "boolean", "default": True},
            },
            "required": ["project_id", "remote_branch"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata."""
        return {
            "name": "git_branch_track_remote",
            "description": (
                "Create a local branch that tracks a remote-tracking branch. "
                "If local_branch is omitted, the final path segment is used."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote_branch": {"type": "string", "required": True},
                "local_branch": {"type": "string", "required": False},
                "checkout": {"type": "boolean", "required": False},
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "remote_branch": "origin/feature/new",
                        "local_branch": "feature/new",
                    }
                }
            ],
        }

    async def execute(
        self,
        project_id: str,
        remote_branch: str,
        local_branch: Optional[str] = None,
        checkout: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_track_remote command."""
        _ = kwargs
        if not remote_branch.strip():
            return ErrorResult(
                message="remote_branch must not be empty",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "remote_branch"},
            )
        target_local = local_branch or _default_local_branch(remote_branch)
        if not target_local:
            return ErrorResult(
                message="local_branch could not be inferred",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "local_branch"},
            )
        root = self._resolve_project_root(project_id)
        if not is_git_available():
            return git_remote_error_result(
                GIT_NOT_AVAILABLE, "git executable is not available", {}
            )
        if not is_git_repository(root):
            return git_remote_error_result(
                GIT_NOT_A_REPO,
                f"{root} is not a git repository",
                {"root": str(root)},
            )
        args = ["git", "checkout" if checkout else "branch", "--track"]
        if checkout:
            args.extend(["-b", target_local, remote_branch])
        else:
            args.extend([target_local, remote_branch])
        returncode, stdout, stderr, timed_out = run_git_subprocess(
            args,
            cwd=root,
            env=None,
            timeout_seconds=30,
        )
        if timed_out:
            return git_remote_error_result(
                "GIT_BRANCH_TRACK_REMOTE_TIMEOUT",
                "git branch track remote exceeded timeout of 30 seconds",
                {"remote_branch": remote_branch, "local_branch": target_local},
            )
        if returncode != 0:
            return git_remote_error_result(
                "GIT_BRANCH_TRACK_REMOTE_FAILED",
                f"git branch track remote failed with exit code {returncode}",
                {
                    "remote_branch": remote_branch,
                    "local_branch": target_local,
                    "stderr": stderr.strip(),
                },
            )
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "remote_branch": remote_branch,
                    "local_branch": target_local,
                    "checked_out": checkout,
                    "output": stdout.strip(),
                },
            )
        )


def _default_local_branch(remote_branch: str) -> Optional[str]:
    """Infer a local branch from a remote branch short name."""
    if "/" not in remote_branch:
        return None
    return remote_branch.split("/", 1)[1]
