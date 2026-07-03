# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_branch_sync_status MCP command: local branch upstream summary."""

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


class GitBranchSyncStatusCommand(BaseMCPCommand):
    """MCP command reporting local branch sync status."""

    name = "git_branch_sync_status"
    version = "1.0.0"
    descr = (
        "Report upstream, ahead/behind, gone, and current status for local branches."
    )
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_sync_status"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "include_no_upstream": {"type": "boolean", "default": True},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata."""
        return {
            "name": "git_branch_sync_status",
            "description": (
                "Report upstream, ahead/behind, gone, and current status for "
                "local branches. Read-only."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "include_no_upstream": {"type": "boolean", "required": False},
            },
            "examples": [{"command": {"project_id": "<uuid>"}}],
        }

    async def execute(
        self,
        project_id: str,
        include_no_upstream: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_sync_status command."""
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
                "for-each-ref",
                "--format=%(refname:short)%09%(HEAD)%09%(upstream:short)%09%(upstream:track)",
                "refs/heads",
            ],
        )
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )
        branches = [
            parsed
            for line in out.splitlines()
            if (parsed := _parse_sync_line(line, include_no_upstream)) is not None
        ]
        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "branches": branches,
            "count": len(branches),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


def _parse_sync_line(line: str, include_no_upstream: bool) -> Optional[Dict[str, Any]]:
    """Parse one for-each-ref sync line."""
    parts = line.split("\t")
    if len(parts) < 4:
        return None
    name, head, upstream, track = parts[:4]
    if not upstream and not include_no_upstream:
        return None
    ahead, behind, gone = _parse_track(track)
    state = "no_upstream"
    if gone:
        state = "gone"
    elif upstream:
        state = "up_to_date" if ahead == 0 and behind == 0 else "diverged"
        if ahead > 0 and behind == 0:
            state = "ahead"
        elif behind > 0 and ahead == 0:
            state = "behind"
    return {
        "name": name,
        "current": head == "*",
        "upstream": upstream or None,
        "ahead": ahead,
        "behind": behind,
        "gone": gone,
        "state": state,
    }


def _parse_track(track: str) -> tuple[int, int, bool]:
    """Parse %(upstream:track) output."""
    if not track:
        return 0, 0, False
    if "gone" in track:
        return 0, 0, True
    ahead = 0
    behind = 0
    cleaned = track.strip("[]")
    for part in [item.strip() for item in cleaned.split(",")]:
        if part.startswith("ahead "):
            ahead = int(part.removeprefix("ahead ").strip())
        elif part.startswith("behind "):
            behind = int(part.removeprefix("behind ").strip())
    return ahead, behind, False
