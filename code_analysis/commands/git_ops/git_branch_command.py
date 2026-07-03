# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_branch MCP command (C-009): local branch enumeration.

Reports the list of local branches with the current branch marked.
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


class GitBranchCommand(BaseMCPCommand):
    """MCP command reporting the local branch list (C-009)."""

    name = "git_branch"

    version = "1.0.0"

    descr = "Report the local branch list of a project's git repository, with the current branch marked."

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
        return "git_branch"

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
        """Return extended AI/docs metadata for git_branch.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "git_branch",
            "description": (
                "Report the local branch list of a registered project's "
                "git repository, with the current branch marked. Read-only."
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
        """Execute the git_branch command.

        Args:
            project_id: Registered project identifier whose repository
                root is resolved and inspected.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the branch list, SuccessResult carrying the
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

        rc, out, err = run_git_read(
            root, ["branch", "--list", "--format=%(refname:short)%09%(HEAD)"]
        )
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        branches: List[Dict[str, Any]] = []
        current: Optional[str] = None
        for line in out.splitlines():
            if not line:
                continue
            parts = line.split("\t")
            name = parts[0]
            is_current = len(parts) > 1 and parts[1].strip() == "*"
            branches.append({"name": name, "current": is_current})
            if is_current:
                current = name

        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "branches": branches,
            "current": current,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
