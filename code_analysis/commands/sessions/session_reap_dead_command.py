"""
session_reap_dead MCP command: release locks held by sessions that are no longer alive.

The background reaper (``core/session_lock_reaper.py``) does this on a cadence.
This command is the same sweep on demand, which matters twice: an operator who
has just found a stuck lock should not have to wait out the TTL, and the live
acceptance pipeline needs a way to exercise the whole release path inside one
test run instead of an hour.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_reap_dead_command_metadata import (
    get_session_reap_dead_metadata,
)
from code_analysis.core.client_sessions import SessionNotFoundError, touch_or_error
from code_analysis.core.constants import (
    CLIENT_SESSION_MANUAL_TTL_SECONDS_MIN,
    CLIENT_SESSION_TTL_SECONDS_MAX,
)
from code_analysis.core.security_policy_guard import (
    CommandForbiddenError,
    enforce_security_policy,
)
from code_analysis.core.session_lock_reaper import (
    load_session_reaper_policy,
    sweep_dead_sessions,
)


class SessionReapDeadCommand(BaseMCPCommand):
    """MCP command: release everything held by sessions idle past the TTL."""

    name = "session_reap_dead"
    version = "1.0.0"
    descr = "Release file locks and leases held by client sessions idle past the TTL."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name."""
        return "session_reap_dead"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": (
                        "Optional caller session UUID4. When provided it is "
                        "touched and policy-checked, and it is never reaped by "
                        "its own call."
                    ),
                },
                "ttl_seconds": {
                    "type": "integer",
                    "minimum": CLIENT_SESSION_MANUAL_TTL_SECONDS_MIN,
                    "maximum": CLIENT_SESSION_TTL_SECONDS_MAX,
                    "description": (
                        "Idle threshold to apply for this sweep. Defaults to the "
                        "configured code_analysis.client_session.ttl_seconds."
                    ),
                },
                "only_session_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Restrict the sweep to these sessions. The idle test "
                        "still applies to each: naming a session asks for it to "
                        "be reaped IF it is dead, it never forces the release of "
                        "a live one."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "description": (
                        "Report which sessions WOULD be reaped without releasing "
                        "anything. Default false."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        session_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        only_session_ids: Optional[List[str]] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute session_reap_dead: sweep sessions idle past the TTL.

        Args:
            session_id: Optional caller session UUID4; touched and policy-checked
                when provided, and refreshed so the caller cannot reap itself.
            ttl_seconds: Optional idle threshold override for this sweep.
            only_session_ids: Optional list restricting the sweep to those
                sessions; each is still subject to the idle test.
            dry_run: When True, report candidates and release nothing.
            **kwargs: Adapter context (ignored).

        Returns:
            SuccessResult with the sweep report, or ErrorResult
            SESSION_NOT_FOUND / COMMAND_FORBIDDEN / VALIDATION_ERROR.
        """
        _ = kwargs
        database = self._open_database_from_config()
        raw_config = self._get_raw_config()
        server_uuid: str = raw_config.get("registration", {}).get("instance_uuid", "")
        policy_mode: str = (raw_config.get("security") or {}).get("policy", "disabled")

        if session_id:
            # Touching first is not bookkeeping: it is what keeps a caller from
            # sweeping away its own session when it passes a tiny ttl_seconds.
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
                    command_name="session_reap_dead",
                    server_uuid=server_uuid,
                    policy_mode=policy_mode,
                )
            except CommandForbiddenError as exc:
                return ErrorResult(code="COMMAND_FORBIDDEN", message=str(exc))

        policy = load_session_reaper_policy(raw_config)
        effective_ttl = (
            int(ttl_seconds) if ttl_seconds is not None else policy.ttl_seconds
        )
        if (
            effective_ttl < CLIENT_SESSION_MANUAL_TTL_SECONDS_MIN
            or effective_ttl > CLIENT_SESSION_TTL_SECONDS_MAX
        ):
            return ErrorResult(
                code="VALIDATION_ERROR",
                message=(
                    "ttl_seconds must be between "
                    f"{CLIENT_SESSION_MANUAL_TTL_SECONDS_MIN} and "
                    f"{CLIENT_SESSION_TTL_SECONDS_MAX}, got {effective_ttl}"
                ),
                details={"field": "ttl_seconds"},
            )

        scope: Optional[List[str]] = None
        if only_session_ids is not None:
            if not isinstance(only_session_ids, list) or any(
                not isinstance(item, str) for item in only_session_ids
            ):
                return ErrorResult(
                    code="VALIDATION_ERROR",
                    message="only_session_ids must be a list of strings",
                    details={"field": "only_session_ids"},
                )
            scope = [item.strip() for item in only_session_ids if item.strip()]

        if dry_run:
            from code_analysis.core.client_sessions import (
                count_session_file_locks,
                list_client_sessions,
            )

            candidates = [
                {
                    "session_id": str(row.get("session_id")),
                    "comment": row.get("comment"),
                    "open_lock_count": count_session_file_locks(
                        database, str(row.get("session_id"))
                    ),
                }
                for row in list_client_sessions(
                    database, stale_threshold_seconds=effective_ttl
                )
                if scope is None or str(row.get("session_id")) in scope
            ]
            return SuccessResult(
                data={
                    "dry_run": True,
                    "ttl_seconds": effective_ttl,
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                }
            )

        result = sweep_dead_sessions(
            database, ttl_seconds=effective_ttl, only_session_ids=scope
        )
        return SuccessResult(data={"dry_run": False, **result.as_dict()})

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return extended command metadata for help and AI tooling."""
        return get_session_reap_dead_metadata(cls)
