"""
session_delete MCP command: delete a client session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_delete_command_metadata import (
    _FORCE_SCHEMA_DESCRIPTION,
    get_session_delete_metadata,
)
from code_analysis.core.client_sessions import (
    SessionHasAdvisoryLocksError,
    SessionHasLocksError,
    SessionHasSubordinatesError,
    SessionNotFoundError,
    delete_client_session,
)
from code_analysis.core.security_policy_guard import (
    CommandForbiddenError,
    enforce_security_policy,
)


class SessionDeleteCommand(BaseMCPCommand):
    """MCP command: delete a client session."""

    name = "session_delete"
    version = "1.0.0"
    descr = (
        "Delete a client session; force=false (default) requires no locks or "
        "subordinates; force=true removes them recursively."
    )
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "session_delete"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "UUID4 of the session to delete.",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": _FORCE_SCHEMA_DESCRIPTION,
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        session_id: str,
        force: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute session_delete.

        No SessionTouchRule (session is being terminated).
        Execution order: SESSION_NOT_FOUND guard -> SecurityPolicy check -> delete.

        Args:
            session_id: UUID4 of the session to delete.
            force: Default false when omitted. See get_schema() force description.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with session_id, deleted, released_lock_count,
            released_subordinate_count.
            ErrorResult SESSION_NOT_FOUND if session absent.
            ErrorResult SESSION_HAS_LOCKS if open locks exist and force=False.
            ErrorResult SESSION_HAS_SUBORDINATES if subordinate links exist and
            force=False.
            ErrorResult COMMAND_FORBIDDEN if SecurityPolicy denies the command.
        """
        _ = kwargs
        database = self._open_database_from_config()
        raw_config = self._get_raw_config()
        server_uuid: str = raw_config.get("registration", {}).get("instance_uuid", "")
        policy_mode: str = (raw_config.get("security") or {}).get("policy", "disabled")

        from code_analysis.core.client_sessions import get_client_session

        if get_client_session(database, session_id) is None:
            return ErrorResult(
                code="SESSION_NOT_FOUND",
                message=f"Session {session_id!r} not found.",
            )

        try:
            enforce_security_policy(
                database=database,
                session_id=session_id,
                command_name="session_delete",
                server_uuid=server_uuid,
                policy_mode=policy_mode,
            )
        except CommandForbiddenError as e:
            return ErrorResult(code="COMMAND_FORBIDDEN", message=str(e))

        try:
            result = delete_client_session(database, session_id=session_id, force=force)
        except SessionNotFoundError:
            return ErrorResult(
                code="SESSION_NOT_FOUND",
                message=f"Session {session_id!r} not found.",
            )
        except SessionHasLocksError as e:
            return ErrorResult(code="SESSION_HAS_LOCKS", message=str(e))
        except SessionHasSubordinatesError as e:
            return ErrorResult(code="SESSION_HAS_SUBORDINATES", message=str(e))
        except SessionHasAdvisoryLocksError as e:
            return ErrorResult(code="SESSION_HAS_ADVISORY_LOCKS", message=str(e))
        return SuccessResult(data=result)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended command metadata for help and AI tooling."""
        return get_session_delete_metadata(cls)
