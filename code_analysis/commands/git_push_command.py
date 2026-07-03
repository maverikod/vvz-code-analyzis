"""git_push MCP command (C-014, C-016): publish local commits to a remote branch.

Guarded: a push to a branch listed in configured protected_branches is rejected
with GIT_PROTECTED_BRANCH unless protected_override is true; a force push is
rejected with GIT_FORCE_PUSH_DISABLED unless configuration allows it. A dry-run
push performs no remote write.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.git_integration import is_git_available, is_git_repository
from code_analysis.core.git_remote_ops import (
    GIT_NOT_A_REPO,
    GIT_NOT_AVAILABLE,
    GIT_REMOTE_NOT_CONFIGURED,
    GIT_REMOTE_TIMEOUT,
    build_full_subprocess_env,
    evaluate_push_guards,
    git_remote_error_result,
    load_git_remote_config,
    run_git_subprocess,
)
from code_analysis.core.git_ssh_auth import GIT_AUTH_FAILED, classify_ssh_auth_stderr


class GitPushCommand(BaseMCPCommand):
    """MCP command publishing local commits to a remote branch."""

    name = "git_push"
    version = "1.0.0"
    descr = (
        "Publish local commits to a remote branch, guarded by protected-branch "
        "and force-push policy."
    )
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_push"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "branch": {"type": "string"},
                "remote": {"type": "string"},
                "force": {"type": "boolean"},
                "protected_override": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["project_id", "branch"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitPushCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_push."""
        return {
            "name": "git_push",
            "description": (
                "Publish local commits to a remote branch. Rejects "
                "protected-branch pushes without protected_override and force "
                "pushes unless configuration allows force. dry_run performs no "
                "remote write."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "branch": {"type": "string", "required": True},
                "remote": {"type": "string", "required": False},
                "force": {"type": "boolean", "required": False},
                "protected_override": {"type": "boolean", "required": False},
                "dry_run": {"type": "boolean", "required": False},
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "branch": "feature-x",
                        "remote": "origin",
                    }
                }
            ],
        }

    async def execute(
        self,
        project_id: str,
        branch: str,
        remote: str = "origin",
        force: bool = False,
        protected_override: bool = False,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_push command."""
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
        config_data = self._get_raw_config()
        git_config = load_git_remote_config(config_data)
        if not git_config["remote_enabled"]:
            return git_remote_error_result(
                GIT_REMOTE_NOT_CONFIGURED,
                "Remote git operations are not enabled in configuration",
                {},
            )
        guard = evaluate_push_guards(
            branch,
            protected_branches=git_config["protected_branches"],
            protected_override=protected_override,
            force=force,
            allow_force_push_config=git_config["allow_force_push"],
        )
        if guard is not None:
            guard_code, guard_message = guard
            return git_remote_error_result(
                guard_code, guard_message, {"remote": remote, "branch": branch}
            )
        env, auth_error = build_full_subprocess_env(git_config)
        if auth_error is not None:
            return git_remote_error_result(
                GIT_AUTH_FAILED,
                str(
                    auth_error.get(
                        "message", "SSH authentication is not configured correctly"
                    )
                ),
                {},
            )
        args = ["git", "push"]
        if dry_run:
            args.append("--dry-run")
        if force:
            args.append("--force")
        args += [remote, branch]
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
                    "git push exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote, "branch": branch},
            )
        if returncode != 0:
            auth_code = classify_ssh_auth_stderr(stderr)
            if auth_code == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during git push",
                    {"remote": remote, "branch": branch},
                )
            return git_remote_error_result(
                "GIT_PUSH_FAILED",
                f"git push failed with exit code {returncode}",
                {"remote": remote, "branch": branch, "stderr": stderr.strip()},
            )
        payload: Dict[str, Any] = {
            "success": True,
            "remote": remote,
            "branch": branch,
            "refs": [branch],
            "force": force,
            "dry_run": dry_run,
            "outcome": "OK",
            "output": stdout.strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
