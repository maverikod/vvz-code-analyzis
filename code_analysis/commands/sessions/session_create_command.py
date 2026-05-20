"""
session_create MCP command: create a new client session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_create_command_metadata import (
    get_session_create_metadata,
)
from code_analysis.core.client_sessions import create_client_session


class SessionCreateCommand(BaseMCPCommand):
    """MCP command: create a new client session."""

    name = "session_create"
    version = "1.0.0"
    descr = "Create a new client session and return its session_id."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name.

        Returns:
            MCP command name string.
        """
        return "session_create"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "properties": {
                "comment": {
                    "type": "string",
                    "description": "Human-readable label for this session.",
                },
                "role_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of role UUID4 strings to assign at creation.",
                },
            },
            "required": ["comment"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        comment: str,
        role_ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute session_create.

        Creates a new ClientSession record with the given comment and optional
        role assignments. No SessionTouchRule applies (session does not exist yet).
        No SecurityPolicy check (creation is always permitted).

        Args:
            comment: Human-readable label for the session.
            role_ids: Optional list of role UUID4 strings to assign at creation.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with session_id, comment, created_at, last_active_at.
        """
        _ = kwargs
        database = self._open_database_from_config()
        row = create_client_session(database, comment=comment, role_ids=role_ids)
        return SuccessResult(data=row)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended command metadata for help and AI tooling."""
        return get_session_create_metadata(cls)
