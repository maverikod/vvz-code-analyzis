"""git_pull MCP command (C-014, C-015): integrate a remote branch into the current branch.

Defaults to a fast-forward-only merge (git pull --ff-only). When rebase is
requested, uses git pull --rebase instead and never combines it with --ff-only.
A pull that cannot complete cleanly aborts back to a clean working tree and
reports GIT_CONFLICT. Requires remote operations to be enabled in configuration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Type, cast

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


def _abort_pull_best_effort(
    rebase: bool,
    cwd: Path,
    env: Optional[Dict[str, str]],
) -> None:
    """Best-effort abort of an in-progress merge or rebase after a failed pull."""
    abort_args = ["git", "rebase", "--abort"] if rebase else ["git", "merge", "--abort"]
    try:
        run_git_subprocess(abort_args, cwd=cwd, env=env, timeout_seconds=30.0)
    except Exception:
        return


class GitPullCommand(BaseMCPCommand):
    """MCP command integrating a remote branch into the current branch."""

    name = "git_pull"
    version = "1.0.0"
    descr = (
        "Integrate a remote branch into the current branch (fast-forward-only "
        "by default, or rebase)."
    )
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_pull"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote": {"type": "string"},
                "ref": {"type": "string"},
                "rebase": {"type": "boolean"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitPullCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_pull."""
        return {
            "name": "git_pull",
            "description": (
                "Integrate a remote branch into the current branch. "
                "Fast-forward-only by default; pass rebase=true to rebase instead."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote": {"type": "string", "required": False},
                "ref": {"type": "string", "required": False},
                "rebase": {"type": "boolean", "required": False},
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "remote": "origin", "ref": "main"}}
            ],
        }

    async def execute(
        self,
        project_id: str,
        remote: str = "origin",
        ref: Optional[str] = None,
        rebase: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_pull command."""
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
        if rebase:
            args = ["git", "pull", "--rebase", remote] + ([ref] if ref else [])
        else:
            args = ["git", "pull", "--ff-only", remote] + ([ref] if ref else [])
        returncode, stdout, stderr, timed_out = run_git_subprocess(
            args,
            cwd=root,
            env=env,
            timeout_seconds=git_config["remote_timeout_seconds"],
        )
        if timed_out:
            _abort_pull_best_effort(rebase, root, env)
            return git_remote_error_result(
                GIT_REMOTE_TIMEOUT,
                (
                    "git pull exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote, "ref": ref, "rebase": rebase},
            )
        if returncode != 0:
            auth_code = classify_ssh_auth_stderr(stderr)
            if auth_code == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during git pull",
                    {"remote": remote, "ref": ref},
                )
            _abort_pull_best_effort(rebase, root, env)
            return git_remote_error_result(
                GIT_CONFLICT,
                (
                    f"git pull could not complete cleanly (exit code {returncode}); "
                    "working tree restored to a clean state"
                ),
                {
                    "remote": remote,
                    "ref": ref,
                    "rebase": rebase,
                    "stderr": stderr.strip(),
                },
            )
        payload: Dict[str, Any] = {
            "success": True,
            "remote": remote,
            "ref": ref,
            "rebase": rebase,
            "outcome": "OK",
            "output": stdout.strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
