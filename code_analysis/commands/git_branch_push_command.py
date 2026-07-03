"""git_branch_push MCP command: push a branch to a remote.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.git_integration import is_git_available, is_git_repository
from code_analysis.core.git_remote_ops import (
    GIT_FORCE_PUSH_DISABLED,
    GIT_NOT_A_REPO,
    GIT_NOT_AVAILABLE,
    GIT_PROTECTED_BRANCH,
    GIT_REMOTE_NOT_CONFIGURED,
    GIT_REMOTE_TIMEOUT,
    build_full_subprocess_env,
    evaluate_push_guards,
    git_remote_error_result,
    load_git_remote_config,
    run_git_subprocess,
)
from code_analysis.core.git_ssh_auth import GIT_AUTH_FAILED, classify_ssh_auth_stderr


class GitBranchPushCommand(BaseMCPCommand):
    """MCP command pushing a branch to a remote."""

    name = "git_branch_push"
    version = "1.0.0"
    descr = "Push a local branch to a remote repository."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_push"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "branch": {"type": "string"},
                "remote": {"type": "string"},
                "set_upstream": {"type": "boolean", "default": False},
                "force": {"type": "boolean", "default": False},
                "force_with_lease": {"type": "boolean", "default": False},
                "protected_override": {"type": "boolean", "default": False},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_branch_push."""
        return {
            "name": "git_branch_push",
            "description": (
                "Push a local branch to a remote repository. Defaults to the "
                "current branch and origin."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "branch": {"type": "string", "required": False},
                "remote": {"type": "string", "required": False},
                "set_upstream": {"type": "boolean", "required": False},
                "force": {"type": "boolean", "required": False},
                "force_with_lease": {"type": "boolean", "required": False},
                "protected_override": {"type": "boolean", "required": False},
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "branch": "feature/new",
                        "set_upstream": True,
                    }
                }
            ],
        }

    async def execute(
        self,
        project_id: str,
        branch: Optional[str] = None,
        remote: str = "origin",
        set_upstream: bool = False,
        force: bool = False,
        force_with_lease: bool = False,
        protected_override: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_push command."""
        _ = kwargs
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
        target_branch = branch or _current_branch(root)
        if not target_branch:
            return ErrorResult(
                message="branch is required when HEAD is detached",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "branch"},
            )

        config_data = self._get_raw_config()
        git_config = load_git_remote_config(config_data)
        if not git_config["remote_enabled"]:
            return git_remote_error_result(
                GIT_REMOTE_NOT_CONFIGURED,
                "Remote git operations are not enabled in configuration",
                {},
            )
        guard = evaluate_push_guards(
            target_branch,
            protected_branches=git_config["protected_branches"],
            protected_override=protected_override,
            force=force or force_with_lease,
            allow_force_push_config=git_config["allow_force_push"],
        )
        if guard is not None:
            code, message = guard
            return git_remote_error_result(code, message, {"branch": target_branch})
        env, auth_error = build_full_subprocess_env(git_config)
        if auth_error is not None:
            return git_remote_error_result(
                GIT_AUTH_FAILED,
                str(auth_error.get("message", "SSH authentication is not configured")),
                {},
            )

        args = ["git", "push"]
        if set_upstream:
            args.append("--set-upstream")
        if force:
            args.append("--force")
        if force_with_lease:
            args.append("--force-with-lease")
        args.extend([remote, target_branch])
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
                    "git branch push exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote, "branch": target_branch},
            )
        if returncode != 0:
            auth_code = classify_ssh_auth_stderr(stderr)
            if auth_code == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during git branch push",
                    {"remote": remote, "branch": target_branch},
                )
            return git_remote_error_result(
                "GIT_BRANCH_PUSH_FAILED",
                f"git branch push failed with exit code {returncode}",
                {
                    "remote": remote,
                    "branch": target_branch,
                    "stderr": stderr.strip(),
                },
            )
        payload: Dict[str, Any] = {
            "success": True,
            "remote": remote,
            "branch": target_branch,
            "set_upstream": set_upstream,
            "force": force,
            "force_with_lease": force_with_lease,
            "outcome": "OK",
            "output": stdout.strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


def _current_branch(root: Any) -> Optional[str]:
    """Return current branch name, or None for detached HEAD."""
    returncode, stdout, _stderr, _timed_out = run_git_subprocess(
        ["git", "branch", "--show-current"],
        cwd=root,
        env=None,
        timeout_seconds=30,
    )
    if returncode != 0:
        return None
    branch = stdout.strip()
    return branch or None
