# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_status MCP command (C-009): working-tree and index status.

Reports the current branch and the porcelain status entries for a
registered project's git repository. Read-only; never mutates the
working tree, index, or refs. When the resolved project root is not a
usable git repository, returns the uniform read-availability outcome
instead of a malformed-call error (spec {u1v2} {w3x4}).
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


class GitStatusCommand(BaseMCPCommand):
    """MCP command reporting git working-tree and index status (C-009)."""

    name = "git_status"

    version = "1.0.0"

    descr = "Report the current branch and porcelain status entries of a project's git repository."

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
        return "git_status"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_status.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "git_status",
            "description": (
                "Report the current branch and porcelain=v1 status entries "
                "of a registered project's git repository. Read-only."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
            },
            "examples": [{"command": {"project_id": "<uuid>"}}],
        }

    async def execute(
        self,
        project_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_status command.

        Args:
            project_id: Registered project identifier whose repository
                root is resolved and inspected.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with branch and status entries, SuccessResult
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

        rc, out, err = run_git_read(root, ["status", "--porcelain=v1", "--branch"])
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        branch: str = ""
        entries: List[Dict[str, str]] = []
        for line in out.splitlines():
            if line.startswith("## "):
                branch = line[3:].strip()
            elif line:
                entries.append({"status": line[:2], "path": line[3:]})

        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "branch": branch,
            "entries": entries,
            "clean": len(entries) == 0,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
