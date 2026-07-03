"""git_branch_checkout MCP command: switch branches.

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


class GitBranchCheckoutCommand(BaseMCPCommand):
    """MCP command checking out a local branch."""

    name = "git_branch_checkout"
    version = "1.0.0"
    descr = "Check out an existing branch or create and check out a new local branch."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_checkout"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "create": {"type": "boolean", "default": False},
                "start_point": {"type": "string"},
            },
            "required": ["project_id", "name"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_branch_checkout."""
        return {
            "name": "git_branch_checkout",
            "description": (
                "Check out an existing branch, or create and check out a new "
                "branch when create=true."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "create": {"type": "boolean", "required": False},
                "start_point": {"type": "string", "required": False},
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "name": "main"}},
                {
                    "command": {
                        "project_id": "<uuid>",
                        "name": "feature/new",
                        "create": True,
                        "start_point": "origin/main",
                    }
                },
            ],
        }

    async def execute(
        self,
        project_id: str,
        name: str,
        create: bool = False,
        start_point: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_checkout command."""
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

        args = ["git", "checkout"]
        if create:
            args.extend(["-b", name])
            if start_point:
                args.append(start_point)
        else:
            args.append(name)
        returncode, stdout, stderr, timed_out = run_git_subprocess(
            args,
            cwd=root,
            env=None,
            timeout_seconds=30,
        )
        if timed_out:
            return git_remote_error_result(
                "GIT_BRANCH_CHECKOUT_TIMEOUT",
                "git branch checkout exceeded timeout of 30 seconds",
                {"name": name, "create": create, "start_point": start_point},
            )
        if returncode != 0:
            return git_remote_error_result(
                "GIT_BRANCH_CHECKOUT_FAILED",
                f"git branch checkout failed with exit code {returncode}",
                {
                    "name": name,
                    "create": create,
                    "start_point": start_point,
                    "stderr": stderr.strip(),
                },
            )
        payload: Dict[str, Any] = {
            "success": True,
            "name": name,
            "created": create,
            "start_point": start_point,
            "output": stdout.strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
