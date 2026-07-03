# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_branch_list MCP command: local and remote branch enumeration."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.git_ops.read_availability import (
    availability_success_result,
    check_read_availability,
    run_git_read,
)
from code_analysis.core.exceptions import ValidationError

BranchScope = Literal["local", "remote", "all"]


class GitBranchListCommand(BaseMCPCommand):
    """MCP command reporting local and remote-tracking branches."""

    name = "git_branch_list"
    version = "1.0.0"
    descr = "List local and/or remote-tracking branches for a project's git repository."
    category = "git"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "git_branch_list"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "scope": {
                    "type": "string",
                    "enum": ["local", "remote", "all"],
                    "default": "all",
                },
                "contains": {"type": "string"},
                "merged": {"type": "string"},
                "sort": {"type": "string"},
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended AI/docs metadata for git_branch_list."""
        return {
            "name": "git_branch_list",
            "description": (
                "List local and/or remote-tracking branches for a registered "
                "project's git repository. Read-only."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "scope": {
                    "type": "string",
                    "required": False,
                    "description": "One of local, remote, or all. Default: all.",
                },
                "contains": {
                    "type": "string",
                    "required": False,
                    "description": "Only list branches containing the given commit.",
                },
                "merged": {
                    "type": "string",
                    "required": False,
                    "description": "Only list branches merged into the given commit.",
                },
                "sort": {
                    "type": "string",
                    "required": False,
                    "description": "Git branch sort key, for example -committerdate.",
                },
            },
            "examples": [
                {"command": {"project_id": "<uuid>"}},
                {"command": {"project_id": "<uuid>", "scope": "remote"}},
            ],
        }

    async def execute(
        self,
        project_id: str,
        scope: BranchScope = "all",
        contains: Optional[str] = None,
        merged: Optional[str] = None,
        sort: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the git_branch_list command."""
        _ = kwargs
        if scope not in {"local", "remote", "all"}:
            return ErrorResult(
                message="scope must be one of: local, remote, all",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"field": "scope"},
            )
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

        args = [
            "for-each-ref",
            "--format=%(refname)%09%(refname:short)%09%(HEAD)%09%(upstream:short)%09%(objectname:short)%09%(committerdate:iso-strict)",
        ]
        if contains:
            args.extend(["--contains", contains])
        if merged:
            args.extend(["--merged", merged])
        if sort:
            args.extend(["--sort", sort])
        args.extend(_ref_prefixes(scope))

        rc, out, err = run_git_read(root, args)
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        branches: List[Dict[str, Any]] = []
        current: Optional[str] = None
        for line in out.splitlines():
            branch = _parse_branch_line(line)
            if branch is None:
                continue
            branches.append(branch)
            if branch["current"]:
                current = cast(str, branch["name"])

        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "scope": scope,
            "current": current,
            "branches": branches,
            "count": len(branches),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))


def _ref_prefixes(scope: BranchScope) -> List[str]:
    """Return git ref prefixes for a branch listing scope."""
    if scope == "local":
        return ["refs/heads"]
    if scope == "remote":
        return ["refs/remotes"]
    return ["refs/heads", "refs/remotes"]


def _parse_branch_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse one tab-separated git for-each-ref line."""
    parts = line.split("\t")
    if len(parts) < 6:
        return None
    refname, short_name, head_marker, upstream, commit, committed_at = parts[:6]
    if refname == "refs/remotes/origin/HEAD" or short_name.endswith("/HEAD"):
        return None
    is_remote = refname.startswith("refs/remotes/")
    return {
        "name": short_name,
        "ref": refname,
        "scope": "remote" if is_remote else "local",
        "remote": _remote_name(short_name) if is_remote else None,
        "current": head_marker == "*",
        "upstream": upstream or None,
        "commit": commit,
        "committed_at": committed_at or None,
    }


def _remote_name(short_name: str) -> Optional[str]:
    """Return the remote name for a remote-tracking branch short name."""
    if "/" not in short_name:
        return None
    return short_name.split("/", 1)[0]
