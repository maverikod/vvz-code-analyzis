"""
session_validate MCP command: confirm a client session exists.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_validate_command_metadata import (
    get_session_validate_metadata,
)
from code_analysis.core.client_sessions import (
    SessionNotFoundError,
    validate_client_session,
)
from code_analysis.core.security_policy_guard import (
    CommandForbiddenError,
    enforce_security_policy,
)


class SessionValidateCommand(BaseMCPCommand):
    """MCP command: verify session_id is registered in client_sessions."""

    name = "session_validate"
    version = "1.0.0"
    descr = "Confirm that a client session exists (optional activity touch)."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "session_validate"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "UUID4 of the client session to validate.",
                },
                "touch": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, update last_active_at after confirming the session exists."
                    ),
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        session_id: str,
        touch: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute session_validate."""
        _ = kwargs
        database = self._open_database_from_config()
        raw_config = self._get_raw_config()
        server_uuid: str = raw_config.get("registration", {}).get("instance_uuid", "")
        policy_mode: str = (raw_config.get("security") or {}).get("policy", "disabled")

        try:
            row = validate_client_session(
                database, session_id, touch=bool(touch)
            )
        except SessionNotFoundError:
            return ErrorResult(
                code="SESSION_NOT_FOUND",
                message=f"Session {session_id!r} not found.",
            )

        try:
            enforce_security_policy(
                database=database,
                session_id=session_id,
                command_name="session_validate",
                server_uuid=server_uuid,
                policy_mode=policy_mode,
            )
        except CommandForbiddenError as e:
            return ErrorResult(code="COMMAND_FORBIDDEN", message=str(e))

        return SuccessResult(data=row)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended command metadata for help and AI tooling."""
        return get_session_validate_metadata(cls)
