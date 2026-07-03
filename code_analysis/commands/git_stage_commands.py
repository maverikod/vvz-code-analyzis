"""Git staging, commit, and restore MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_stage_metadata import (
    get_git_add_metadata,
    get_git_commit_metadata,
    get_git_restore_metadata,
)
from code_analysis.commands.git_worktree_base import (
    GitWorktreeCommand,
    string_list,
    validation_error,
)


class GitAddCommand(GitWorktreeCommand):
    """Stage files in a project's git repository."""

    name = "git_add"
    version = "1.0.0"
    descr = "Stage file changes in a project's git repository."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_add"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID. Use list_projects to discover valid "
                        "project_id values."
                    ),
                },
                "paths": {
                    "type": "array",
                    "description": (
                        "Optional literal project-relative git pathspecs to stage. "
                        "Passed after '--'."
                    ),
                    "items": {"type": "string"},
                },
                "all": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Stage all additions, modifications, and deletions in the "
                        "repository. Mutually exclusive with update=true."
                    ),
                },
                "update": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Stage tracked-file modifications and deletions only; does "
                        "not add untracked files."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_add."""
        return get_git_add_metadata(cls)

    async def execute(
        self,
        project_id: str,
        paths: Optional[List[str]] = None,
        all: bool = False,
        update: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_add command."""
        _ = kwargs
        pathspecs = string_list(paths)
        if all and update:
            return validation_error("all and update are mutually exclusive", "all")
        if not (all or update or pathspecs):
            return validation_error(
                "Provide paths, all=true, or update=true",
                "paths",
            )
        args = ["add"]
        if all:
            args.append("--all")
        elif update:
            args.append("--update")
        if pathspecs:
            args.extend(["--", *pathspecs])
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_ADD_FAILED",
            action="git add",
            details={"paths": pathspecs, "all": all, "update": update},
        )
        if error is not None:
            return error
        stdout, _stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "paths": pathspecs,
                    "all": all,
                    "update": update,
                    "output": stdout.strip(),
                },
            )
        )


class GitCommitCommand(GitWorktreeCommand):
    """Create a commit in a project's git repository."""

    name = "git_commit"
    version = "1.0.0"
    descr = "Create a git commit from staged changes."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_commit"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID. Use list_projects to discover valid "
                        "project_id values."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": (
                        "Commit message passed to git commit -m. Must not be empty."
                    ),
                },
                "amend": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, amend the current HEAD commit instead of creating "
                        "a new commit."
                    ),
                },
                "allow_empty": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, allow a commit even when no staged changes exist."
                    ),
                },
            },
            "required": ["project_id", "message"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_commit."""
        return get_git_commit_metadata(cls)

    async def execute(
        self,
        project_id: str,
        message: str,
        amend: bool = False,
        allow_empty: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_commit command."""
        _ = kwargs
        if not message.strip():
            return validation_error("Commit message must not be empty", "message")
        args = ["commit", "-m", message]
        if amend:
            args.append("--amend")
        if allow_empty:
            args.append("--allow-empty")
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_COMMIT_FAILED",
            action="git commit",
            details={"amend": amend, "allow_empty": allow_empty},
        )
        if error is not None:
            return error
        stdout, _stderr = result or ("", "")
        hash_result, hash_error = self._run_local_git(
            project_id,
            ["rev-parse", "--short", "HEAD"],
            error_code="GIT_COMMIT_HASH_FAILED",
            action="git rev-parse HEAD",
        )
        if hash_error is not None:
            return hash_error
        commit_hash = (hash_result or ("", ""))[0].strip()
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "commit": commit_hash,
                    "amend": amend,
                    "allow_empty": allow_empty,
                    "output": stdout.strip(),
                },
            )
        )


class GitRestoreCommand(GitWorktreeCommand):
    """Restore worktree or index paths in a project's git repository."""

    name = "git_restore"
    version = "1.0.0"
    descr = "Restore worktree or staged changes for selected paths."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_restore"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID. Use list_projects to discover valid "
                        "project_id values."
                    ),
                },
                "paths": {
                    "type": "array",
                    "description": (
                        "Optional literal project-relative git pathspecs to restore. "
                        "Passed after '--'."
                    ),
                    "items": {"type": "string"},
                },
                "all": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Restore all files under the repository root by passing '.' "
                        "after '--'. Use carefully."
                    ),
                },
                "staged": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, restore the index, equivalent to git restore --staged."
                    ),
                },
                "worktree": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "If true, restore worktree files, equivalent to git restore "
                        "--worktree. May discard uncommitted file content."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_restore."""
        return get_git_restore_metadata(cls)

    async def execute(
        self,
        project_id: str,
        paths: Optional[List[str]] = None,
        all: bool = False,
        staged: bool = False,
        worktree: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_restore command."""
        _ = kwargs
        pathspecs = string_list(paths)
        if not (all or pathspecs):
            return validation_error("Provide paths or all=true", "paths")
        if not (staged or worktree):
            return validation_error(
                "At least one of staged or worktree must be true",
                "worktree",
            )
        args = ["restore"]
        if staged:
            args.append("--staged")
        if worktree:
            args.append("--worktree")
        args.extend(["--", "."] if all else ["--", *pathspecs])
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_RESTORE_FAILED",
            action="git restore",
            details={
                "paths": pathspecs,
                "all": all,
                "staged": staged,
                "worktree": worktree,
            },
        )
        if error is not None:
            return error
        stdout, _stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {
                    "success": True,
                    "paths": pathspecs,
                    "all": all,
                    "staged": staged,
                    "worktree": worktree,
                    "output": stdout.strip(),
                },
            )
        )
