"""Git stash MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_stash_metadata import (
    get_git_stash_apply_metadata,
    get_git_stash_drop_metadata,
    get_git_stash_list_metadata,
    get_git_stash_push_metadata,
)
from code_analysis.commands.git_worktree_base import (
    GitWorktreeCommand,
    string_list,
    validation_error,
)


class GitStashListCommand(GitWorktreeCommand):
    """List git stash entries for a project."""

    name = "git_stash_list"
    version = "1.0.0"
    descr = "List stash entries in a project's git repository."
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_stash_list"

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
                }
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_stash_list."""
        return get_git_stash_list_metadata(cls)

    async def execute(
        self,
        project_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_stash_list command."""
        _ = kwargs
        result, error = self._run_local_git(
            project_id,
            ["stash", "list", "--date=iso"],
            error_code="GIT_STASH_LIST_FAILED",
            action="git stash list",
        )
        if error is not None:
            return error
        stdout, _stderr = result or ("", "")
        entries: List[Dict[str, str]] = []
        for line in stdout.splitlines():
            ref, sep, rest = line.partition(": ")
            if sep:
                entries.append({"ref": ref, "summary": rest})
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {"success": True, "entries": entries, "count": len(entries)},
            )
        )


class GitStashPushCommand(GitWorktreeCommand):
    """Push current changes onto the git stash."""

    name = "git_stash_push"
    version = "1.0.0"
    descr = "Save working-tree changes to git stash."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_stash_push"

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
                        "Optional stash message passed with -m for later "
                        "identification."
                    ),
                },
                "paths": {
                    "type": "array",
                    "description": (
                        "Optional literal project-relative git pathspecs to stash. "
                        "Passed after '--'."
                    ),
                    "items": {"type": "string"},
                },
                "include_untracked": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include untracked files in the stash.",
                },
                "keep_index": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, keep staged changes in the index after stashing."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_stash_push."""
        return get_git_stash_push_metadata(cls)

    async def execute(
        self,
        project_id: str,
        message: Optional[str] = None,
        paths: Optional[List[str]] = None,
        include_untracked: bool = False,
        keep_index: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_stash_push command."""
        _ = kwargs
        pathspecs = string_list(paths)
        args = ["stash", "push"]
        if include_untracked:
            args.append("--include-untracked")
        if keep_index:
            args.append("--keep-index")
        if message:
            args.extend(["-m", message])
        if pathspecs:
            args.extend(["--", *pathspecs])
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_STASH_PUSH_FAILED",
            action="git stash push",
            details={
                "paths": pathspecs,
                "include_untracked": include_untracked,
                "keep_index": keep_index,
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
                    "include_untracked": include_untracked,
                    "keep_index": keep_index,
                    "output": stdout.strip(),
                },
            )
        )


class GitStashApplyCommand(GitWorktreeCommand):
    """Apply a git stash entry."""

    name = "git_stash_apply"
    version = "1.0.0"
    descr = "Apply a stash entry to the current working tree."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_stash_apply"

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
                "ref": {
                    "type": "string",
                    "default": "stash@{0}",
                    "description": (
                        "Stash reference to apply. Defaults to the newest stash."
                    ),
                },
                "index": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, try to restore the staged/index state from the stash."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_stash_apply."""
        return get_git_stash_apply_metadata(cls)

    async def execute(
        self,
        project_id: str,
        ref: str = "stash@{0}",
        index: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_stash_apply command."""
        _ = kwargs
        if not ref.strip():
            return validation_error("Stash ref must not be empty", "ref")
        args = ["stash", "apply"]
        if index:
            args.append("--index")
        args.append(ref)
        result, error = self._run_local_git(
            project_id,
            args,
            error_code="GIT_STASH_APPLY_FAILED",
            action="git stash apply",
            details={"ref": ref, "index": index},
        )
        if error is not None:
            return error
        stdout, _stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {"success": True, "ref": ref, "index": index, "output": stdout.strip()},
            )
        )


class GitStashDropCommand(GitWorktreeCommand):
    """Drop a git stash entry."""

    name = "git_stash_drop"
    version = "1.0.0"
    descr = "Drop a stash entry from a project's git repository."
    use_queue = True

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_stash_drop"

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
                "ref": {
                    "type": "string",
                    "default": "stash@{0}",
                    "description": (
                        "Stash reference to drop. Defaults to the newest stash."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_stash_drop."""
        return get_git_stash_drop_metadata(cls)

    async def execute(
        self,
        project_id: str,
        ref: str = "stash@{0}",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_stash_drop command."""
        _ = kwargs
        if not ref.strip():
            return validation_error("Stash ref must not be empty", "ref")
        result, error = self._run_local_git(
            project_id,
            ["stash", "drop", ref],
            error_code="GIT_STASH_DROP_FAILED",
            action="git stash drop",
            details={"ref": ref},
        )
        if error is not None:
            return error
        stdout, _stderr = result or ("", "")
        return SuccessResult(
            data=cast(
                Dict[str, Any],
                {"success": True, "ref": ref, "output": stdout.strip()},
            )
        )
