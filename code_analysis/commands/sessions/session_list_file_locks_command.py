"""
session_list_file_locks MCP command: list file locks held by a session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_list_file_locks_command_metadata import (
    get_session_list_file_locks_metadata,
)
from code_analysis.core.client_sessions import (
    SessionNotFoundError,
    list_session_file_locks,
    touch_or_error,
)
from code_analysis.core.security_policy_guard import (
    CommandForbiddenError,
    enforce_security_policy,
)


class SessionListFileLocksCommand(BaseMCPCommand):
    """MCP command: list file locks held by a session."""

    name = "session_list_file_locks"
    version = "1.0.0"
    descr = "List all file locks held by a session."
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
        return "session_list_file_locks"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "UUID4 of the session to inspect.",
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
        """Execute session_list_file_locks.

        Execution order: SessionTouchRule -> SecurityPolicy check -> list locks.

        Args:
            session_id: UUID4 of the session to inspect.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with session_id, locks list, and count.
            ErrorResult SESSION_NOT_FOUND if session is absent.
            ErrorResult COMMAND_FORBIDDEN if SecurityPolicy denies the command.
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
                code="SESSION_NOT_FOUND", message=f"Session {session_id!r} not found."
            )
        try:
            enforce_security_policy(
                database=database,
                session_id=session_id,
                command_name="session_list_file_locks",
                server_uuid=server_uuid,
                policy_mode=policy_mode,
            )
        except CommandForbiddenError as e:
            return ErrorResult(code="COMMAND_FORBIDDEN", message=str(e))

        locks = list_session_file_locks(database, session_id=session_id)
        return SuccessResult(
            data={"session_id": session_id, "locks": locks, "count": len(locks)}
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended command metadata for help and AI tooling."""
        return get_session_list_file_locks_metadata(cls)
