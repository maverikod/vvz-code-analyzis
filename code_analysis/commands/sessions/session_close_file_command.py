"""
session_close_file MCP command: release a file lock for a session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_close_file_command_metadata import (
    get_session_close_file_metadata,
)
from code_analysis.core.client_sessions import (
    SessionNotFoundError,
    close_session_file,
    touch_or_error,
)
from code_analysis.core.security_policy_guard import (
    CommandForbiddenError,
    enforce_security_policy,
)


class SessionCloseFileCommand(BaseMCPCommand):
    """MCP command: release a file lock for a session."""

    name = "session_close_file"
    version = "1.0.0"
    descr = "Release a file lock for a session (idempotent)."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "session_close_file"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "UUID4 of the active session.",
                },
                "project_id": {
                    "type": "string",
                    "description": "UUID of the registered project.",
                },
                "file_id": {
                    "type": "string",
                    "description": "UUID of the file record.",
                },
            },
            "required": ["session_id", "project_id", "file_id"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        session_id: str,
        project_id: str,
        file_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Release a file lock: touch, policy check, then close_session_file.

        Args:
            session_id: UUID4 of the active session.
            project_id: UUID of the registered project.
            file_id: UUID of the file record.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with released, was_locked, session_id, project_id, file_id;
            ErrorResult SESSION_NOT_FOUND or COMMAND_FORBIDDEN on failure.
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
                command_name="session_close_file",
                server_uuid=server_uuid,
                policy_mode=policy_mode,
            )
        except CommandForbiddenError as e:
            return ErrorResult(code="COMMAND_FORBIDDEN", message=str(e))

        result = close_session_file(
            database, session_id=session_id, project_id=project_id, file_id=file_id
        )
        return SuccessResult(data=result)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended command metadata for help and AI tooling."""
        return get_session_close_file_metadata(cls)
