# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_branch_current MCP command: current branch and upstream status."""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.git_ops.read_availability import (
    availability_success_result,
    check_read_availability,
    run_git_read,
)
from code_analysis.core.exceptions import ValidationError


class GitBranchCurrentCommand(BaseMCPCommand):
    """MCP command returning the current branch and sync status."""

    name = "git_branch_current"
    version = "1.0.0"
    descr = "Return the current git branch, upstream, ahead/behind, and detached state."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_current"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
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
        """Return extended AI/docs metadata for git_branch_current."""
        return {
            "name": "git_branch_current",
            "description": (
                "Return the current branch, upstream, ahead/behind counts, "
                "and detached state for a registered project's git repository. Read-only."
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
        """Execute the git_branch_current command."""
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
            root,
            [
                "status",
                "--porcelain=v1",
                "--branch",
            ],
        )
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        branch_line = next(
            (line[3:].strip() for line in out.splitlines() if line.startswith("## ")),
            "",
        )
        payload = _parse_branch_status(branch_line)
        payload.update({"success": True, "available": True})
        return SuccessResult(data=cast(Dict[str, Any], payload))


def _parse_branch_status(branch_line: str) -> Dict[str, Any]:
    """Parse the branch line emitted by git status --porcelain --branch."""
    if not branch_line:
        return {
            "branch": None,
            "upstream": None,
            "ahead": 0,
            "behind": 0,
            "detached": False,
        }

    head, bracket = _split_status_bracket(branch_line)
    upstream: Optional[str] = None
    ahead = 0
    behind = 0
    if "..." in head:
        branch, upstream = head.split("...", 1)
    else:
        branch = head
    if bracket:
        for item in [part.strip() for part in bracket.split(",")]:
            if item.startswith("ahead "):
                ahead = int(item.removeprefix("ahead ").strip())
            elif item.startswith("behind "):
                behind = int(item.removeprefix("behind ").strip())
    detached = branch.startswith("HEAD ") or branch.startswith("HEAD detached")
    return {
        "branch": None if detached else branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "detached": detached,
        "raw": branch_line,
    }


def _split_status_bracket(branch_line: str) -> tuple[str, Optional[str]]:
    """Split status branch text into head and optional bracket content."""
    if "[" not in branch_line or not branch_line.endswith("]"):
        return branch_line, None
    head, tail = branch_line.rsplit("[", 1)
    return head.strip(), tail[:-1]
