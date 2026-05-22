"""
session_view MCP command: aggregated session locks and subordinate sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_view_command_metadata import (
    get_session_view_metadata,
)
from code_analysis.core.client_sessions import SessionNotFoundError, touch_or_error
from code_analysis.core.security_policy_guard import (
    CommandForbiddenError,
    enforce_security_policy,
)
from code_analysis.core.session_view import build_session_view


class SessionViewCommand(BaseMCPCommand):
    """MCP command: view session locks by project and subordinate sessions."""

    name = "session_view"
    version = "1.0.0"
    descr = (
        "View locked files grouped by project and subordinate session links "
        "for one client session."
    )
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "session_view"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "UUID4 of the client session to inspect.",
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        session_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute session_view.

        Args:
            session_id: UUID4 of the client session.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with locked_files_by_project and subordinate_sessions.
        """
        _ = kwargs
        database = self._open_database_from_config()
        raw_config = self._get_raw_config()
        server_uuid: str = raw_config.get("registration", {}).get("instance_uuid", "")
        policy_mode: str = (raw_config.get("security") or {}).get("policy", "disabled")

        try:
            touch_or_error(database, session_id)
        except SessionNotFoundError:
            return ErrorResult(
                code="SESSION_NOT_FOUND",
                message=f"Session {session_id!r} not found.",
            )
        try:
            enforce_security_policy(
                database=database,
                session_id=session_id,
                command_name="session_view",
                server_uuid=server_uuid,
                policy_mode=policy_mode,
            )
        except CommandForbiddenError as e:
            return ErrorResult(code="COMMAND_FORBIDDEN", message=str(e))

        data = build_session_view(database, session_id, app_config=raw_config)
        return SuccessResult(data=data)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended command metadata for help and AI tooling."""
        return get_session_view_metadata(cls)
