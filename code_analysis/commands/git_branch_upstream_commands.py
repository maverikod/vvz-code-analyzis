"""git branch upstream MCP commands.

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


class GitBranchSetUpstreamCommand(BaseMCPCommand):
    """MCP command setting a local branch upstream."""

    name = "git_branch_set_upstream"
    version = "1.0.0"
    descr = "Set upstream tracking for a local branch."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_set_upstream"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "branch": {"type": "string"},
                "upstream": {"type": "string"},
            },
            "required": ["project_id", "branch", "upstream"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata."""
        return {
            "name": "git_branch_set_upstream",
            "description": "Set upstream tracking for a local branch.",
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "branch": {"type": "string", "required": True},
                "upstream": {"type": "string", "required": True},
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "branch": "main",
                        "upstream": "origin/main",
                    }
                }
            ],
        }

    async def execute(
        self,
        project_id: str,
        branch: str,
        upstream: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_set_upstream command."""
        _ = kwargs
        return await _run_upstream_command(
            project_id=project_id,
            command=self,
            args=["git", "branch", "--set-upstream-to", upstream, branch],
            payload={"branch": branch, "upstream": upstream},
            error_prefix="SET_UPSTREAM",
        )


class GitBranchUnsetUpstreamCommand(BaseMCPCommand):
    """MCP command removing local branch upstream tracking."""

    name = "git_branch_unset_upstream"
    version = "1.0.0"
    descr = "Unset upstream tracking for a local branch."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_unset_upstream"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "branch": {"type": "string"},
            },
            "required": ["project_id", "branch"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata."""
        return {
            "name": "git_branch_unset_upstream",
            "description": "Unset upstream tracking for a local branch.",
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "branch": {"type": "string", "required": True},
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "branch": "feature/local"}}
            ],
        }

    async def execute(
        self,
        project_id: str,
        branch: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_unset_upstream command."""
        _ = kwargs
        return await _run_upstream_command(
            project_id=project_id,
            command=self,
            args=["git", "branch", "--unset-upstream", branch],
            payload={"branch": branch, "upstream": None},
            error_prefix="UNSET_UPSTREAM",
        )


async def _run_upstream_command(
    *,
    project_id: str,
    command: BaseMCPCommand,
    args: list[str],
    payload: Dict[str, Any],
    error_prefix: str,
) -> SuccessResult | ErrorResult:
    """Run a local upstream mutation command."""
    branch = payload.get("branch")
    if not isinstance(branch, str) or not branch.strip():
        return ErrorResult(
            message="Branch name must not be empty",
            code=cast(Any, "VALIDATION_ERROR"),
            details={"field": "branch"},
        )
    root = command._resolve_project_root(project_id)
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
    returncode, stdout, stderr, timed_out = run_git_subprocess(
        args,
        cwd=root,
        env=None,
        timeout_seconds=30,
    )
    if timed_out:
        return git_remote_error_result(
            f"GIT_BRANCH_{error_prefix}_TIMEOUT",
            "git branch upstream operation exceeded timeout of 30 seconds",
            payload,
        )
    if returncode != 0:
        return git_remote_error_result(
            f"GIT_BRANCH_{error_prefix}_FAILED",
            f"git branch upstream operation failed with exit code {returncode}",
            {**payload, "stderr": stderr.strip()},
        )
    return SuccessResult(
        data=cast(
            Dict[str, Any],
            {
                "success": True,
                **payload,
                "output": stdout.strip(),
            },
        )
    )
