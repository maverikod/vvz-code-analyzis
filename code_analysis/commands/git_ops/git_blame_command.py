# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_blame MCP command (C-009): per-line authorship attribution.

Reports per-line commit attribution for one tracked file. Read-only;
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


class GitBlameCommand(BaseMCPCommand):
    """MCP command reporting per-line git blame attribution (C-009)."""

    name = "git_blame"

    version = "1.0.0"

    descr = "Report per-line commit attribution for one tracked file in a project's git repository."

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
        return "git_blame"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, file_path, rev.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "file_path": {"type": "string"},
                "rev": {"type": "string"},
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_blame.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "git_blame",
            "description": (
                "Report per-line commit hash, author, and content for one "
                "tracked file in a registered project's git repository, "
                "optionally as of a given revision. Read-only."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "file_path": {"type": "string", "required": True},
                "rev": {"type": "string", "required": False},
            },
            "examples": [
                {"command": {"project_id": "<uuid>", "file_path": "README.md"}}
            ],
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        rev: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_blame command.

        Args:
            project_id: Registered project identifier whose repository
                root is resolved and inspected.
            file_path: Required project-relative path to the tracked file
                to blame. Confined to the project root.
            rev: Optional opaque revision/ref to blame as of. Not
                path-confined. Rejected if it starts with "-".
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the per-line attribution list, SuccessResult
            carrying the uniform read-availability outcome when the
            repository is unusable, or ErrorResult on validation or git
            command failure.
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

        _confined_path, confinement_error = confine_project_git_path(root, file_path)
        if confinement_error is not None:
            return confinement_error

        argv: List[str] = ["blame", "--line-porcelain"]
        if rev:
            argv.append(rev)
        argv.extend(["--", file_path])

        rc, out, err = run_git_read(root, argv)
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        lines_out: List[Dict[str, Any]] = []
        current_hash = ""
        current_author = ""
        current_line_no = 0
        for raw_line in out.splitlines():
            if raw_line.startswith("\t"):
                lines_out.append(
                    {
                        "line_no": current_line_no,
                        "hash": current_hash,
                        "author": current_author,
                        "content": raw_line[1:],
                    }
                )
                continue
            if raw_line.startswith("author "):
                current_author = raw_line[len("author ") :]
                continue
            first_token = raw_line.split(" ", 1)[0]
            if len(first_token) == 40 and all(
                c in "0123456789abcdef" for c in first_token
            ):
                header_parts = raw_line.split(" ")
                current_hash = header_parts[0]
                current_line_no = int(header_parts[2])

        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "lines": lines_out,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
