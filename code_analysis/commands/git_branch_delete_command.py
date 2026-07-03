"""git_branch_delete MCP command: delete a local branch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.git_integration import is_git_available, is_git_repository
from code_analysis.core.git_remote_ops import (
    GIT_NOT_A_REPO,
    GIT_NOT_AVAILABLE,
    git_remote_error_result,
    run_git_subprocess,
)


class GitBranchDeleteCommand(BaseMCPCommand):
    """MCP command deleting a local git branch."""

    name = "git_branch_delete"
    version = "1.0.0"
    descr = "Delete a local branch in a project's git repository."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_delete"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "force": {"type": "boolean", "default": False},
            },
            "required": ["project_id", "name"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_branch_delete."""
        return {
            "name": "git_branch_delete",
            "description": "Delete a local branch. Uses safe -d unless force=true.",
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "force": {"type": "boolean", "required": False},
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "name": "feature/old"}},
                {
                    "command": {
                        "project_id": "<uuid>",
                        "name": "feature/old",
                        "force": True,
                    }
                },
            ],
        }

    async def execute(
        self,
        project_id: str,
        name: str,
        force: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_delete command."""
        _ = kwargs
        if not name.strip():
            return ErrorResult(
                message="Branch name must not be empty",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "name"},
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
        args = ["git", "branch", "-D" if force else "-d", name]
        returncode, stdout, stderr, timed_out = run_git_subprocess(
            args,
            cwd=root,
            env=None,
            timeout_seconds=30,
        )
        if timed_out:
            return git_remote_error_result(
                "GIT_BRANCH_DELETE_TIMEOUT",
                "git branch delete exceeded timeout of 30 seconds",
                {"name": name, "force": force},
            )
        if returncode != 0:
            return git_remote_error_result(
                "GIT_BRANCH_DELETE_FAILED",
                f"git branch delete failed with exit code {returncode}",
                {"name": name, "force": force, "stderr": stderr.strip()},
            )
        payload: Dict[str, Any] = {
            "success": True,
            "name": name,
            "force": force,
            "output": stdout.strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
