# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_log MCP command (C-009): commit history.

Reports commit history for a registered project's git repository,
optionally scoped to a revision range start and/or a tracked file.
Read-only; never mutates the working tree, index, or refs. When the
resolved project root is not a usable git repository, returns the
uniform read-availability outcome instead of a malformed-call error
(spec {u1v2} {w3x4}).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.git_ops.read_availability import (
    availability_success_result,
    check_read_availability,
    run_git_read,
)
from code_analysis.core.exceptions import ValidationError
from code_analysis.core.project_git.path_confinement import (
    confine_project_git_path,
)


class GitLogCommand(BaseMCPCommand):
    """MCP command reporting git commit history (C-009)."""

    name = "git_log"

    version = "1.0.0"

    descr = "Report commit history of a project's git repository, optionally scoped to a revision or file."

    category = "git"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name.

        Returns:
            MCP command name string.
        """
        return "git_log"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, rev, max_count, file_path.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "rev": {"type": "string"},
                "max_count": {"type": "integer", "minimum": 1, "default": 50},
                "file_path": {"type": "string"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_log.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "git_log",
            "description": (
                "Report commit history (hash, author, date, subject) of a "
                "registered project's git repository, optionally scoped to "
                "a starting revision and/or a tracked file path. Read-only."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "rev": {"type": "string", "required": False},
                "max_count": {"type": "integer", "required": False, "default": 50},
                "file_path": {"type": "string", "required": False},
            },
            "examples": [{"command": {"project_id": "<uuid>", "max_count": 20}}],
        }

    async def execute(
        self,
        project_id: str,
        rev: Optional[str] = None,
        max_count: int = 50,
        file_path: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_log command.

        Args:
            project_id: Registered project identifier whose repository
                root is resolved and inspected.
            rev: Optional opaque revision/ref to start history from.
                Not path-confined. Rejected if it starts with "-".
            max_count: Maximum number of commits to return. Defaults to 50.
            file_path: Optional project-relative path to scope history to
                one file. Confined to the project root when provided.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the commit list, SuccessResult carrying the
            uniform read-availability outcome when the repository is
            unusable, or ErrorResult on validation or git command failure.
        """
        _ = kwargs
        try:
            root = self._resolve_project_root(project_id)
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": e.field} if getattr(e, "field", None) else None,
            )

        outcome = check_read_availability(root)
        if outcome is not None:
            return availability_success_result(outcome)

        if rev is not None and rev.startswith("-"):
            return ErrorResult(
                message="rev must not start with '-'",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "rev"},
            )

        if file_path is not None:
            _confined_path, confinement_error = confine_project_git_path(
                root, file_path
            )
            if confinement_error is not None:
                return confinement_error

        argv: List[str] = [
            "log",
            "--pretty=format:%H%x1f%an%x1f%ae%x1f%aI%x1f%s",
            "-n",
            str(max_count),
        ]
        if rev:
            argv.append(rev)
        if file_path:
            argv.extend(["--", file_path])

        rc, out, err = run_git_read(root, argv)
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        commits: List[Dict[str, str]] = []
        for line in out.splitlines():
            if not line:
                continue
            fields = line.split("\x1f")
            commits.append(
                {
                    "hash": fields[0],
                    "author_name": fields[1],
                    "author_email": fields[2],
                    "date": fields[3],
                    "subject": fields[4],
                }
            )

        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "commits": commits,
            "count": len(commits),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
