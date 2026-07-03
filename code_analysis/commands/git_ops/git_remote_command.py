# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""git_remote MCP command (C-009): configured remote enumeration.

Reports the configured remotes (name, url, kind) of a registered
project's git repository. Read-only; never mutates the working tree,
index, or refs. When the resolved project root is not a usable git
repository, returns the uniform read-availability outcome instead of a
malformed-call error (spec {u1v2} {w3x4}).
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.git_ops.read_availability import (
    availability_success_result,
    check_read_availability,
    run_git_read,
)
from code_analysis.core.exceptions import ValidationError


class GitRemoteCommand(BaseMCPCommand):
    """MCP command reporting configured git remotes (C-009)."""

    name = "git_remote"

    version = "1.0.0"

    descr = (
        "Report the configured remotes (name, url, kind) of a project's git repository."
    )

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
        return "git_remote"

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
        """Return extended AI/docs metadata for git_remote.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "git_remote",
            "description": (
                "Report the configured remotes (name, url, kind) of a "
                "registered project's git repository. Read-only."
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
        """Execute the git_remote command.

        Args:
            project_id: Registered project identifier whose repository
                root is resolved and inspected.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the deduplicated remote list, SuccessResult
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

        rc, out, err = run_git_read(root, ["remote", "--verbose"])
        if rc != 0:
            return ErrorResult(
                message=err.strip() or "git command failed",
                code=cast(Any, "GIT_COMMAND_FAILED"),
                details={"returncode": rc},
            )

        seen: Set[Tuple[str, str]] = set()
        remotes: List[Dict[str, str]] = []
        for line in out.splitlines():
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            name = parts[0]
            rest = parts[1].strip()
            if rest.endswith(")") and "(" in rest:
                url_part, _, kind_part = rest.rpartition("(")
                url = url_part.strip()
                kind = kind_part.rstrip(")").strip()
            else:
                url = rest
                kind = ""
            key = (name, url)
            if key in seen:
                continue
            seen.add(key)
            remotes.append({"name": name, "url": url, "kind": kind})

        payload: Dict[str, Any] = {
            "success": True,
            "available": True,
            "remotes": remotes,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
