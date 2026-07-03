# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_diff MCP command (C-009): working-tree and revision differences.

Reports the diff between two revisions, or between a revision and the
working tree/index, optionally scoped to a tracked file. Read-only;
never mutates the working tree, index, or refs. When the resolved
project root is not a usable git repository, returns the uniform
read-availability outcome instead of a malformed-call error (spec
{u1v2} {w3x4}).
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


class GitDiffCommand(BaseMCPCommand):
    """MCP command reporting git diff output (C-009)."""

    name = "git_diff"

    version = "1.0.0"

    descr = "Report the diff between revisions, or a revision and the working tree, of a project's git repository."

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
        return "git_diff"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, rev_from, rev_to, file_path.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "rev_from": {"type": "string"},
                "rev_to": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_diff.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "git_diff",
            "description": (
                "Report the raw unified diff between two revisions, or "
                "between a revision and the working tree/index, of a "
                "registered project's git repository, optionally scoped "
                "to one tracked file. Read-only."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "rev_from": {"type": "string", "required": False},
                "rev_to": {"type": "string", "required": False},
                "file_path": {"type": "string", "required": False},
            },
            "examples": [{"command": {"project_id": "<uuid>", "rev_from": "HEAD~1"}}],
        }

    async def execute(
        self,
        project_id: str,
        rev_from: Optional[str] = None,
        rev_to: Optional[str] = None,
        file_path: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_diff command.

        Args:
            project_id: Registered project identifier whose repository
                root is resolved and inspected.
            rev_from: Optional opaque revision/ref, the diff start point.
                Not path-confined. Rejected if it starts with "-".
            rev_to: Optional opaque revision/ref, the diff end point.
                Not path-confined. Rejected if it starts with "-".
            file_path: Optional project-relative path to scope the diff
                to one file. Confined to the project root when provided.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the raw diff text, SuccessResult carrying
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

        for value, field_name in ((rev_from, "rev_from"), (rev_to, "rev_to")):
            if value is not None and value.startswith("-"):
                return ErrorResult(
                    message=f"{field_name} must not start with '-'",
                    code=cast(Any, "VALIDATION_ERROR"),
                    details={"field": field_name},
                )

        if file_path is not None:
            _confined_path, confinement_error = confine_project_git_path(
                root, file_path
            )
            if confinement_error is not None:
                return confinement_error

        argv: List[str] = ["diff"]
        if rev_from:
            argv.append(rev_from)
        if rev_to:
            argv.append(rev_to)
        if file_path:
            argv.extend(["--", file_path])

        rc, out, err = run_git_read(root, argv)
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "diff": out,
            "is_empty": out.strip() == "",
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
