"""git_fetch MCP command (C-014): fetch remote refs and objects for a project's git repository.

Fetch only updates remote-tracking refs; it never mutates the working
tree. Requires remote operations to be enabled in configuration
(code_analysis.git.remote_enabled); when absent, fails fast with
GIT_REMOTE_NOT_CONFIGURED while local and read operations remain unaffected.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type, cast

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


class GitFetchCommand(BaseMCPCommand):
    """MCP command fetching remote refs and objects for a project's git repository."""

    name = "git_fetch"
    version = "1.0.0"
    descr = (
        "Fetch remote refs and objects for a project's git repository without "
        "changing the working tree."
    )
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_fetch"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "remote": {"type": "string"},
                "refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitFetchCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_fetch."""
        return {
            "name": "git_fetch",
            "description": (
                "Fetch remote refs and objects for a project's git repository. "
                "Updates remote-tracking refs only; never changes the working tree."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "remote": {"type": "string", "required": False},
                "refs": {"type": "array", "required": False},
            },
            "examples": [{"command": {"project_id": "<uuid>", "remote": "origin"}}],
        }

    async def execute(
        self,
        project_id: str,
        remote: str = "origin",
        refs: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_fetch command."""
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
        ref_list = refs or []
        args = ["git", "fetch", remote] + ref_list
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
                    "git fetch exceeded timeout of "
                    f"{git_config['remote_timeout_seconds']} seconds"
                ),
                {"remote": remote, "refs": ref_list},
            )
        if returncode != 0:
            auth_code = classify_ssh_auth_stderr(stderr)
            if auth_code == GIT_AUTH_FAILED:
                return git_remote_error_result(
                    GIT_AUTH_FAILED,
                    "SSH authentication failed during git fetch",
                    {"remote": remote},
                )
            return git_remote_error_result(
                "GIT_FETCH_FAILED",
                f"git fetch failed with exit code {returncode}",
                {"remote": remote, "refs": ref_list, "stderr": stderr.strip()},
            )
        payload: Dict[str, Any] = {
            "success": True,
            "remote": remote,
            "refs": ref_list,
            "outcome": "OK",
            "updated_tracking_refs": True,
            "output": stdout.strip(),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
