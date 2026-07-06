"""git_init MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.git_integration import is_git_available
from code_analysis.core.git_remote_ops import (
    GIT_NOT_AVAILABLE,
    git_remote_error_result,
    run_git_subprocess,
)

LOCAL_GIT_INIT_TIMEOUT_SECONDS = 30.0


class GitInitCommand(BaseMCPCommand):
    """Initialize or reinitialize a git repository."""

    name = "git_init"
    version = "1.0.0"
    descr = "Initialize or reinitialize a git repository, equivalent to git init."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_init"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "default": ".",
                    "description": (
                        "Optional filesystem path passed to git init. If omitted, "
                        "git init runs for '.'. If the path does not exist, git "
                        "creates it. If the path already contains a repository, "
                        "git reinitializes it, matching ordinary git init behavior."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["GitInitCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_init."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Initialize or reinitialize a local git repository through MCP. "
                "This command intentionally mirrors the ordinary 'git init' CLI "
                "semantics instead of requiring an existing project_id: with no "
                "path it runs 'git init' in the server process current directory; "
                "with path it runs 'git init <path>'. Git itself creates a missing "
                "directory, initializes an empty repository in a non-repository "
                "directory, and reinitializes metadata when the target is already "
                "a repository. The command uses a no-shell subprocess invocation "
                "and returns stdout/stderr so callers can distinguish "
                "'Initialized empty Git repository' from 'Reinitialized existing "
                "Git repository'.\n\n"
                "This command is also the behavior used by create_project after "
                "project registration and bootstrap: new projects get a .git "
                "directory without requiring a separate terminal-side git init."
            ),
            "parameters": {
                "path": {
                    "description": (
                        "Optional path argument for git init. Omit it to use '.', "
                        "or pass an absolute/relative path. Missing directories "
                        "and existing repositories follow git init's native behavior."
                    ),
                    "type": "string",
                    "required": False,
                    "default": ".",
                    "examples": [".", "/var/casmgr/watched/demo/project"],
                },
            },
            "return_value": {
                "success": {
                    "description": "git init completed with exit code 0.",
                    "data": {
                        "success": "Always True on success.",
                        "path": "Path argument supplied to git init.",
                        "resolved_path": "Absolute resolved path for reporting.",
                        "created_or_reinitialized": "True when git returned success.",
                        "output": "stdout from git init.",
                        "stderr": "stderr from git init.",
                    },
                    "example": {
                        "success": True,
                        "path": "/tmp/example",
                        "resolved_path": "/tmp/example",
                        "created_or_reinitialized": True,
                        "output": "Initialized empty Git repository in /tmp/example/.git/",
                        "stderr": "",
                    },
                },
                "error": {
                    "description": "git is unavailable, timed out, or returned non-zero.",
                    "code": "GIT_NOT_AVAILABLE | GIT_INIT_TIMEOUT | GIT_INIT_FAILED",
                    "details": "path, resolved_path, stderr, or timeout seconds.",
                },
            },
            "usage_examples": [
                {
                    "description": "Initialize the current directory",
                    "command": {},
                    "explanation": "Runs git init with no path argument, matching CLI default behavior.",
                },
                {
                    "description": "Initialize a specific path",
                    "command": {"path": "/var/casmgr/watched/demo/project"},
                    "explanation": "Creates the directory if needed and initializes .git inside it.",
                },
                {
                    "description": "Reinitialize an existing repository",
                    "command": {"path": "/var/casmgr/watched/demo/project"},
                    "explanation": "When .git already exists, git refreshes repository metadata and exits successfully.",
                },
            ],
            "error_cases": {
                "GIT_NOT_AVAILABLE": {
                    "description": "The git executable is not available to the server process.",
                    "solution": "Install git or fix PATH for the service process.",
                },
                "GIT_INIT_TIMEOUT": {
                    "description": "git init exceeded the local timeout.",
                    "solution": "Check filesystem responsiveness and retry.",
                },
                "GIT_INIT_FAILED": {
                    "description": "git init returned a non-zero exit code.",
                    "solution": "Inspect details.stderr for permission or filesystem errors.",
                },
            },
            "best_practices": [
                "Pass an explicit path for service-side workflows so the target is unambiguous.",
                "Use create_project for new registered projects; it now performs git initialization automatically.",
                "Run git_status after initializing a registered project to verify repository visibility.",
            ],
        }

    async def execute(
        self,
        path: str = ".",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute git_init."""
        _ = kwargs
        target = path or "."
        if not is_git_available():
            return git_remote_error_result(
                GIT_NOT_AVAILABLE, "git executable is not available", {}
            )
        resolved_path = str(Path(target).expanduser().resolve())
        args = ["git", "init"]
        if target != ".":
            args.append(target)
        returncode, stdout, stderr, timed_out = run_git_subprocess(
            args,
            cwd=Path.cwd(),
            env=None,
            timeout_seconds=LOCAL_GIT_INIT_TIMEOUT_SECONDS,
        )
        if timed_out:
            return git_remote_error_result(
                "GIT_INIT_TIMEOUT",
                (
                    "git init exceeded timeout of "
                    f"{LOCAL_GIT_INIT_TIMEOUT_SECONDS:.0f} seconds"
                ),
                {"path": target, "resolved_path": resolved_path},
            )
        if returncode != 0:
            return git_remote_error_result(
                "GIT_INIT_FAILED",
                f"git init failed with exit code {returncode}",
                {
                    "path": target,
                    "resolved_path": resolved_path,
                    "stderr": stderr.strip(),
                },
            )
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "path": target,
                    "resolved_path": resolved_path,
                    "created_or_reinitialized": True,
                    "output": stdout.strip(),
                    "stderr": stderr.strip(),
                },
            )
        )
