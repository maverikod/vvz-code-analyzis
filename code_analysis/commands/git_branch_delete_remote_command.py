"""git_branch_delete_remote MCP command: delete a remote branch.

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
    GIT_REMOTE_NOT_CONFIGURED,
    GIT_REMOTE_TIMEOUT,
    build_full_subprocess_env,
    git_remote_error_result,
    load_git_remote_config,
    run_git_subprocess,
)
from code_analysis.core.git_ssh_auth import GIT_AUTH_FAILED, classify_ssh_auth_stderr


class GitBranchDeleteRemoteCommand(BaseMCPCommand):
    """MCP command deleting a branch from a remote."""

    name = "git_branch_delete_remote"
    version = "1.0.0"
    descr = "Delete a branch from a remote repository."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_delete_remote"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "branch": {"type": "string"},
                "remote": {"type": "string"},
                "force_confirm": {"type": "boolean"},
            },
            "required": ["project_id", "branch", "force_confirm"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata."""
        return {
            "name": "git_branch_delete_remote",
            "description": (
                "Delete a branch from a remote repository. Requires "
                "force_confirm=true."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "branch": {"type": "string", "required": True},
                "remote": {"type": "string", "required": False},
                "force_confirm": {"type": "boolean", "required": True},
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "branch": "feature/old",
                        "force_confirm": True,
                    }
                }
            ],
        }

    async def execute(
        self,
        project_id: str,
        branch: str,
        force_confirm: bool,
        remote: str = "origin",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_delete_remote command."""
        _ = kwargs
        if not branch.strip():
            return ErrorResult(
                message="Branch name must not be empty",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "branch"},
            )
        if not force_confirm:
            return ErrorResult(
                message="force_confirm=true is required to delete a remote branch",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "force_confirm"},
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
        config_data = self._get_raw_config()
        git_config = load_git_remote_config(config_data)
        if not git_config["remote_enabled"]:
            return git_remote_error_result(
                GIT_REMOTE_NOT_CONFIGURED,
                "Remote git operations are not enabled in configuration",
                {},
            )
        env, auth_error = build_full_subprocess_env(git_config)
        if auth_error is not None:
            return git_remote_error_result(
                GIT_AUTH_FAILED,
                str(auth_error.get("message", "SSH authentication is not configured")),
                {},
            )
        args = ["git", "push", remote, "--delete", branch]
        returncode, stdout, stderr, timed_out = run_git_subprocess(
            args,
            cwd=root,
            env=env,
            timeout_seconds=git_config["remote_timeout_seconds"],
        )
        if timed_out:
            return git_remote_error_result(
                GIT_REMOTE_TIMEOUT,
                (
                    "git remote branch delete exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote, "branch": branch},
            )
        if returncode != 0:
            auth_code = classify_ssh_auth_stderr(stderr)
            if auth_code == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during remote branch delete",
                    {"remote": remote, "branch": branch},
                )
            return git_remote_error_result(
                "GIT_BRANCH_DELETE_REMOTE_FAILED",
                f"git remote branch delete failed with exit code {returncode}",
                {"remote": remote, "branch": branch, "stderr": stderr.strip()},
            )
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "remote": remote,
                    "branch": branch,
                    "output": stdout.strip(),
                },
            )
        )
