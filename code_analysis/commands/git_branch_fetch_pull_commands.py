"""Branch-focused fetch and pull MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.git_integration import is_git_available, is_git_repository
from code_analysis.core.git_remote_ops import (
    GIT_CONFLICT,
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


class GitBranchFetchCommand(BaseMCPCommand):
    """MCP command fetching one branch or all branches from a remote."""

    name = "git_branch_fetch"
    version = "1.0.0"
    descr = "Fetch remote branch refs without changing the working tree."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_fetch"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote": {"type": "string"},
                "branch": {"type": "string"},
                "prune": {"type": "boolean", "default": False},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata."""
        return {
            "name": "git_branch_fetch",
            "description": "Fetch remote branch refs without changing the working tree.",
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote": {"type": "string", "required": False},
                "branch": {"type": "string", "required": False},
                "prune": {"type": "boolean", "required": False},
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "branch": "main"}},
                {"command": {"project_id": "<uuid>", "prune": True}},
            ],
        }

    async def execute(
        self,
        project_id: str,
        remote: str = "origin",
        branch: Optional[str] = None,
        prune: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_fetch command."""
        _ = kwargs
        args = ["git", "fetch"]
        if prune:
            args.append("--prune")
        args.append(remote)
        if branch:
            args.append(branch)
        return await _run_remote_branch_command(
            command=self,
            project_id=project_id,
            args=args,
            timeout_code=GIT_REMOTE_TIMEOUT,
            failure_code="GIT_BRANCH_FETCH_FAILED",
            failure_label="git branch fetch",
            payload={"remote": remote, "branch": branch, "prune": prune},
        )


class GitBranchPullCommand(BaseMCPCommand):
    """MCP command pulling one branch from a remote."""

    name = "git_branch_pull"
    version = "1.0.0"
    descr = "Pull a remote branch into the current branch."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_pull"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote": {"type": "string"},
                "branch": {"type": "string"},
                "rebase": {"type": "boolean", "default": False},
                "ff_only": {"type": "boolean", "default": True},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata."""
        return {
            "name": "git_branch_pull",
            "description": "Pull a remote branch into the current branch.",
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote": {"type": "string", "required": False},
                "branch": {"type": "string", "required": False},
                "rebase": {"type": "boolean", "required": False},
                "ff_only": {"type": "boolean", "required": False},
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "branch": "main"}},
                {
                    "command": {
                        "project_id": "<uuid>",
                        "branch": "main",
                        "rebase": True,
                    }
                },
            ],
        }

    async def execute(
        self,
        project_id: str,
        remote: str = "origin",
        branch: Optional[str] = None,
        rebase: bool = False,
        ff_only: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_pull command."""
        _ = kwargs
        args = ["git", "pull"]
        if rebase:
            args.append("--rebase")
        elif ff_only:
            args.append("--ff-only")
        args.append(remote)
        if branch:
            args.append(branch)
        return await _run_remote_branch_command(
            command=self,
            project_id=project_id,
            args=args,
            timeout_code=GIT_REMOTE_TIMEOUT,
            failure_code=GIT_CONFLICT,
            failure_label="git branch pull",
            payload={
                "remote": remote,
                "branch": branch,
                "rebase": rebase,
                "ff_only": ff_only,
            },
        )


async def _run_remote_branch_command(
    *,
    command: BaseMCPCommand,
    project_id: str,
    args: list[str],
    timeout_code: str,
    failure_code: str,
    failure_label: str,
    payload: Dict[str, Any],
) -> SuccessResult | ErrorResult:
    """Run a remote branch operation with standard remote config guards."""
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
    config_data = command._get_raw_config()
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
    returncode, stdout, stderr, timed_out = run_git_subprocess(
        args,
        cwd=root,
        env=env,
        timeout_seconds=git_config["remote_timeout_seconds"],
    )
    if timed_out:
        return git_remote_error_result(
            timeout_code,
            f"{failure_label} exceeded timeout of {git_config['remote_timeout_seconds']} seconds",
            payload,
        )
    if returncode != 0:
        auth_code = classify_ssh_auth_stderr(stderr)
        if auth_code == GIT_AUTH_FAILED:
            return git_remote_error_result(
                GIT_AUTH_FAILED,
                f"SSH authentication failed during {failure_label}",
                payload,
            )
        return git_remote_error_result(
            failure_code,
            f"{failure_label} failed with exit code {returncode}",
            {**payload, "stderr": stderr.strip()},
        )
    return SuccessResult(
        data=cast(
            Dict[str, Any],
            {
                "success": True,
                **payload,
                "outcome": "OK",
                "output": stdout.strip(),
            },
        )
    )
