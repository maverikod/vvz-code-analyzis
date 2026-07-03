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

        rc, counts, err = run_git_read(
            root, ["rev-list", "--left-right", "--count", f"{base}...{head}"]
        )
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )
        behind, ahead = [int(part) for part in counts.split()]
        commit_args = [
            "log",
            "--oneline",
            f"--max-count={max(0, max_commits)}",
            f"{base}..{head}",
        ]
        rc, commit_out, err = run_git_read(root, commit_args)
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )
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
            "commits": _parse_commits(commit_out),
            "files": _parse_name_status(files_out),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


def _parse_commits(output: str) -> List[Dict[str, str]]:
    """Parse git log --oneline output."""
    commits: List[Dict[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        commit, _, message = line.partition(" ")
        commits.append({"commit": commit, "message": message})
    return commits


def _parse_name_status(output: str) -> List[Dict[str, str]]:
    """Parse git diff --name-status output."""
    files: List[Dict[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        status, _, path = line.partition("\t")
        files.append({"status": status, "path": path})
    return files
