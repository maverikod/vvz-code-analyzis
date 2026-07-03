# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_show MCP command (C-009): single-commit inspection.

Reports the header fields, full message, and stat summary of a single
named commit. Read-only; never mutates the working tree, index, or
refs. When the resolved project root is not a usable git repository,
returns the uniform read-availability outcome instead of a
malformed-call error (spec {u1v2} {w3x4}).
"""

from __future__ import annotations

from typing import Any, Dict, List, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.git_ops.read_availability import (
    availability_success_result,
    check_read_availability,
    run_git_read,
)
from code_analysis.core.exceptions import ValidationError


class GitShowCommand(BaseMCPCommand):
    """MCP command reporting single-commit detail (C-009)."""

    name = "git_show"

    version = "1.0.0"

    descr = "Report header fields, message, and stat summary of a single named commit in a project's git repository."

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
        return "git_show"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id and rev.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "rev": {"type": "string"},
            },
            "required": ["project_id", "rev"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_show.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "git_show",
            "description": (
                "Report the hash, author, date, message, and stat summary "
                "of a single named commit in a registered project's git "
                "repository. Read-only."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "rev": {"type": "string", "required": True},
            },
            "examples": [{"command": {"project_id": "<uuid>", "rev": "HEAD"}}],
        }

    async def execute(
        self,
        project_id: str,
        rev: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_show command.

        Args:
            project_id: Registered project identifier whose repository
                root is resolved and inspected.
            rev: Required opaque revision/ref identifying the commit to
                inspect. Not path-confined. Rejected if it starts with "-".
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the commit detail, SuccessResult carrying
            the uniform read-availability outcome when the repository is
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

        if rev.startswith("-"):
            return ErrorResult(
                message="rev must not start with '-'",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "rev"},
            )

        argv: List[str] = [
            "show",
            "--stat",
            "--pretty=format:%H%x1f%an%x1f%ae%x1f%aI%x1f%B%x1e",
            rev,
        ]
        rc, out, err = run_git_read(root, argv)
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        head, _, remainder = out.partition("\x1e")
        fields = head.split("\x1f")
        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "hash": fields[0] if len(fields) > 0 else "",
            "author_name": fields[1] if len(fields) > 1 else "",
            "author_email": fields[2] if len(fields) > 2 else "",
            "date": fields[3] if len(fields) > 3 else "",
            "message": fields[4] if len(fields) > 4 else "",
            "stat": remainder,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
