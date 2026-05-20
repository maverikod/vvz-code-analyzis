"""
session_list MCP command: list all client sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_list_command_metadata import (
    get_session_list_metadata,
)
from code_analysis.core.client_sessions import (
    SessionNotFoundError,
    count_session_file_locks,
    list_client_sessions,
    touch_or_error,
)
from code_analysis.core.security_policy_guard import (
    CommandForbiddenError,
    enforce_security_policy,
)


class SessionListCommand(BaseMCPCommand):
    """MCP command: list all client sessions."""

    name = "session_list"
    version = "1.0.0"
    descr = "List all client sessions with optional stale filter."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "session_list"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": (
                        "Required when show_session_ids=true in config. "
                        "Optional when show_session_ids=false. "
                        "Touch and SecurityPolicy check applied when provided."
                    ),
                },
                "stale_threshold_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "If set, return only sessions idle longer than N seconds.",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        session_id: Optional[str] = None,
        stale_threshold_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute session_list.

        Lists all ClientSessions enriched with open_lock_count. Respects
        SessionListVisibilityPolicy (C-006) and SecurityPolicy (C-009).

        Execution order when session_id provided:
          1. SessionTouchRule (touch_or_error) -> SESSION_NOT_FOUND on failure.
          2. SecurityPolicy check -> COMMAND_FORBIDDEN on failure.
          3. List logic.
        When session_id not provided and show_session_ids=false:
          no touch, no policy check.

        Args:
            session_id: Optional session UUID4. Required when show_session_ids=True.
            stale_threshold_seconds: Optional inactivity filter in seconds.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with sessions list and count.
            ErrorResult SESSION_ID_REQUIRED, SESSION_NOT_FOUND, or
            COMMAND_FORBIDDEN on failure.
        """
        _ = kwargs
        raw_config = self._get_raw_config()
        sessions_cfg = raw_config.get("sessions") or {}
        show_ids: bool = bool(sessions_cfg.get("show_session_ids", False))
        server_uuid: str = raw_config.get("registration", {}).get("instance_uuid", "")
        policy_mode: str = (raw_config.get("security") or {}).get("policy", "disabled")

        database = self._open_database_from_config()

        if show_ids and not session_id:
            return ErrorResult(
                code="SESSION_ID_REQUIRED",
                message="sessions.show_session_ids is true: session_id is required.",
            )
        if session_id:
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
                    command_name="session_list",
                    server_uuid=server_uuid,
                    policy_mode=policy_mode,
                )
            except CommandForbiddenError as e:
                return ErrorResult(code="COMMAND_FORBIDDEN", message=str(e))

        rows: List[Dict[str, Any]] = list_client_sessions(
            database, stale_threshold_seconds=stale_threshold_seconds
        )
        for row in rows:
            row["open_lock_count"] = count_session_file_locks(
                database, row["session_id"]
            )
            if not show_ids:
                row.pop("session_id", None)

        return SuccessResult(
            data={"sessions": rows, "count": len(rows), "show_session_ids": show_ids}
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended command metadata for help and AI tooling."""
        return get_session_list_metadata(cls)
