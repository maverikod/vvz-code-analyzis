# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_branch_compare MCP command: compare two refs."""

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


class GitBranchCompareCommand(BaseMCPCommand):
    """MCP command comparing two branches or refs."""

    name = "git_branch_compare"
    version = "1.0.0"
    descr = "Compare two branches or refs: ahead/behind, commits, and changed files."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_compare"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "base": {"type": "string"},
                "head": {"type": "string"},
                "max_commits": {"type": "integer", "minimum": 0, "default": 20},
            },
            "required": ["project_id", "base", "head"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata."""
        return {
            "name": "git_branch_compare",
            "description": (
                "Compare two branches or refs and report ahead/behind counts, "
                "head-only commits, and changed files. Read-only."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "base": {"type": "string", "required": True},
                "head": {"type": "string", "required": True},
                "max_commits": {"type": "integer", "required": False},
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "base": "main",
                        "head": "feature/new",
                    }
                }
            ],
        }

    async def execute(
        self,
        project_id: str,
        base: str,
        head: str,
        max_commits: int = 20,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_compare command."""
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

        # Single plumbing call for both ahead/behind counts and their commit
        # lists, so the counts and the returned lists can never disagree
        # (bug d05492ef: two separate calls could observe the refs at
        # different moments, or the count call and the list call could
        # disagree in scope, producing e.g. behind:5 with an empty list).
        # `git log --left-right --oneline base...head` walks the full,
        # untruncated symmetric difference in one subprocess invocation:
        # "<" lines are base-only commits (behind), ">" lines are
        # head-only commits (ahead). Counts are the exact lengths of those
        # lists; only the returned lists are capped to max_commits.
        rc, log_out, err = run_git_read(
            root, ["log", "--left-right", "--oneline", f"{base}...{head}"]
        )
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )
        behind_commits, ahead_commits = _parse_left_right_commits(log_out)
        behind = len(behind_commits)
        ahead = len(ahead_commits)
        cap = max(0, max_commits)
        rc, files_out, err = run_git_read(
            root, ["diff", "--name-status", f"{base}...{head}"]
        )
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )
        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "base": base,
            "head": head,
            "ahead": ahead,
            "behind": behind,
            "commits": ahead_commits[:cap],
            "behind_commits": behind_commits[:cap],
            "files": _parse_name_status(files_out),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


def _parse_left_right_commits(
    output: str,
) -> tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Parse `git log --left-right --oneline base...head` output.

    Args:
        output: Raw stdout from the left-right oneline log invocation.

    Returns:
        A tuple (behind_commits, ahead_commits): commits reachable only
        from base ("<" marker, behind) and commits reachable only from
        head (">" marker, ahead), each as {"commit", "message"} dicts in
        the order git emitted them. The two lists are derived from the
        same single subprocess call as the ahead/behind counts, so their
        lengths always equal those counts exactly.
    """
    behind: List[Dict[str, str]] = []
    ahead: List[Dict[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        marker, _, rest = line.partition(" ")
        commit, _, message = rest.partition(" ")
        entry = {"commit": commit, "message": message}
        if marker == "<":
            behind.append(entry)
        elif marker == ">":
            ahead.append(entry)
    return behind, ahead


def _parse_name_status(output: str) -> List[Dict[str, str]]:
    """Parse git diff --name-status output."""
    files: List[Dict[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        status, _, path = line.partition("\t")
        files.append({"status": status, "path": path})
    return files
