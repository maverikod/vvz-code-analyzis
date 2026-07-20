"""git_init MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.base_mcp_command_resolve_path import (
    resolve_under_project_root,
)
from code_analysis.core.exceptions import ValidationError
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
                "project_id": {
                    "type": "string",
                    "description": (
                        "Registered project id (UUID4, from create_project or "
                        "list_projects). Required: git_init never falls back to "
                        "the server process's working directory."
                    ),
                },
                "path": {
                    "type": "string",
                    "default": ".",
                    "description": (
                        "Optional path relative to the project root (POSIX "
                        "'/'). Defaults to the project root itself ('.'). Must "
                        "not be absolute and must not escape the project root "
                        "(rejected with a structured validation error). If the "
                        "resolved path does not exist, git creates it. If the "
                        "resolved path already contains a repository, git "
                        "reinitializes it, matching ordinary git init behavior."
                    ),
                },
            },
            "required": ["project_id"],
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
                "Initialize or reinitialize a local git repository through MCP, "
                "scoped strictly to a registered project. project_id is REQUIRED "
                "- this command NEVER falls back to the server process's working "
                "directory (a prior defect resolved 'path=.' with no project "
                "context against the server's cwd, e.g. /etc/casmgr, and tried "
                "to git-init it). The project root is resolved from project_id "
                "the same way every other project-scoped command resolves it "
                "(BaseMCPCommand._resolve_project_root); path (when given) is "
                "then resolved and validated strictly under that root using the "
                "same traversal/escape checks the project-relative file_path "
                "commands use (resolve_under_project_root): absolute paths and "
                "'..' segments are rejected, and the resolved path must stay "
                "inside the project root. Git itself creates a missing "
                "directory, initializes an empty repository in a non-repository "
                "directory, and reinitializes metadata when the target is already "
                "a repository. The command uses a no-shell subprocess invocation "
                "and returns stdout/stderr so callers can distinguish "
                "'Initialized empty Git repository' from 'Reinitialized existing "
                "Git repository'.\n\n"
                "create_project performs its own independent git init during "
                "project bootstrap and does not call this command; this command "
                "is for initializing/reinitializing git in an already-registered "
                "project (e.g. one created without git, or whose .git directory "
                "was removed)."
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Registered project id (UUID4). Required; the project "
                        "root is resolved from this id and path never escapes it."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "path": {
                    "description": (
                        "Optional path relative to the project root. Omit it "
                        "to init the project root itself ('.'). Absolute paths "
                        "and '..' traversal are rejected; the resolved path "
                        "must stay under the project root."
                    ),
                    "type": "string",
                    "required": False,
                    "default": ".",
                    "examples": [".", "subdir/nested_repo"],
                },
            },
            "return_value": {
                "success": {
                    "description": "git init completed with exit code 0.",
                    "data": {
                        "success": "Always True on success.",
                        "project_id": "Echoes the project_id argument.",
                        "path": "Path argument supplied to git init (project-relative).",
                        "resolved_path": "Absolute resolved path for reporting.",
                        "created_or_reinitialized": "True when git returned success.",
                        "output": "stdout from git init.",
                        "stderr": "stderr from git init.",
                    },
                    "example": {
                        "success": True,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "path": ".",
                        "resolved_path": "/var/casmgr/watched/demo/project",
                        "created_or_reinitialized": True,
                        "output": "Initialized empty Git repository in /var/casmgr/watched/demo/project/.git/",
                        "stderr": "",
                    },
                },
                "error": {
                    "description": (
                        "project_id missing/unknown, path escapes the project "
                        "root, git is unavailable, timed out, or returned "
                        "non-zero."
                    ),
                    "code": "VALIDATION_ERROR | GIT_NOT_AVAILABLE | GIT_INIT_TIMEOUT | GIT_INIT_FAILED",
                    "details": "field/path, resolved_path, stderr, or timeout seconds.",
                },
            },
            "usage_examples": [
                {
                    "description": "Initialize the project root",
                    "command": {"project_id": "550e8400-e29b-41d4-a716-446655440000"},
                    "explanation": "Runs git init in the resolved project root (no path argument).",
                },
                {
                    "description": "Initialize a subdirectory within the project",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "path": "vendor/nested_repo",
                    },
                    "explanation": "Creates the directory if needed and initializes .git inside it, still under the project root.",
                },
                {
                    "description": "Reinitialize an existing repository",
                    "command": {"project_id": "550e8400-e29b-41d4-a716-446655440000"},
                    "explanation": "When .git already exists in the project root, git refreshes repository metadata and exits successfully.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": (
                        "project_id is missing/unknown, or path is absolute, "
                        "contains '..', or resolves outside the project root."
                    ),
                    "solution": "Pass a registered project_id and a project-relative path.",
                },
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
                "Always pass project_id; git_init never falls back to the server process's working directory.",
                "Use create_project for new registered projects; it now performs git initialization automatically.",
                "Run git_status after initializing a registered project to verify repository visibility.",
            ],
        }

    async def execute(
        self,
        project_id: str = "",
        path: str = ".",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute git_init.

        project_id is mandatory: the project root is resolved via
        ``_resolve_project_root`` (database-backed, never a filesystem
        fallback), and ``path`` - when given - is resolved and validated
        strictly under that root via ``resolve_under_project_root`` (rejects
        absolute paths and '..' traversal, and rejects any resolved path that
        escapes the root). This command never resolves against the server
        process's current working directory.
        """
        _ = kwargs
        try:
            project_root = self._resolve_project_root(project_id).resolve()
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code=cast(Any, "VALIDATION_ERROR"),
                details=getattr(e, "details", None) or {},
            )
        target = path or "."
        try:
            resolved_path = (
                project_root
                if target == "."
                else resolve_under_project_root(
                    project_root, target, require_exists=False
                )
            )
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code=cast(Any, "VALIDATION_ERROR"),
                details=getattr(e, "details", None) or {},
            )
        try:
            if not is_git_available():
                return git_remote_error_result(
                    GIT_NOT_AVAILABLE, "git executable is not available", {}
                )
            args = ["git", "init"]
            if target != ".":
                args.append(str(resolved_path))
            returncode, stdout, stderr, timed_out = run_git_subprocess(
                args,
                cwd=project_root,
                env=None,
                timeout_seconds=LOCAL_GIT_INIT_TIMEOUT_SECONDS,
            )
        except Exception as e:
            return self._handle_error(e, "GIT_INIT_ERROR", "git_init")
        if timed_out:
            return git_remote_error_result(
                "GIT_INIT_TIMEOUT",
                (
                    "git init exceeded timeout of "
                    f"{LOCAL_GIT_INIT_TIMEOUT_SECONDS:.0f} seconds"
                ),
                {"path": target, "resolved_path": str(resolved_path)},
            )
        if returncode != 0:
            return git_remote_error_result(
                "GIT_INIT_FAILED",
                f"git init failed with exit code {returncode}",
                {
                    "path": target,
                    "resolved_path": str(resolved_path),
                    "stderr": stderr.strip(),
                },
            )
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "project_id": project_id,
                    "path": target,
                    "resolved_path": str(resolved_path),
                    "created_or_reinitialized": True,
                    "output": stdout.strip(),
                    "stderr": stderr.strip(),
                },
            )
        )
