"""
MCP command: search_sessions_purge — on-demand sweep of expired search sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.exceptions import ValidationError
from ..core.search_session.cleaner import sweep_expired_sessions
from .base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class SearchSessionsPurgeCommand(BaseMCPCommand):
    """
    Trigger an on-demand sweep of expired paginated search sessions.

    Runs the same safe removal logic as the periodic background cleaner
    (``core/search_session/cleaner.py``): a session directory is only
    removed when it is idle and in a terminal state (or detected dead/
    orphaned/timed-out), never while ``running`` with a live, heartbeating
    process. Exists mainly as an operator/administrative lever and as a
    deterministic hook for live verification (waiting for the real 1800s
    default retention -- or even the 60s minimum sweep cadence -- in a test
    is unnecessarily slow; this command lets a test force an immediate,
    bounded-scope sweep).
    """

    name = "search_sessions_purge"
    version = "1.0.0"
    descr = (
        "Trigger an on-demand sweep of expired search sessions. Optional "
        "max_age_seconds overrides the configured/default retention for "
        "this sweep only; never removes a live 'running' session."
    )
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "max_age_seconds": {
                    "type": ["integer", "null"],
                    "minimum": 0,
                    "description": (
                        "Override retention for this sweep only: remove idle "
                        "terminal-state sessions older than this many seconds. "
                        "Omit or pass null to use the configured/default "
                        "retention (code_analysis.search_session.ttl_seconds). "
                        "A live 'running' session with a fresh heartbeat is "
                        "never removed regardless of this value."
                    ),
                },
            },
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return validate params."""
        params = super().validate_params(params)
        max_age = params.get("max_age_seconds")
        if max_age is not None:
            try:
                max_age_int = int(max_age)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "max_age_seconds must be an integer",
                    field="max_age_seconds",
                    details={"max_age_seconds": max_age},
                ) from exc
            if max_age_int < 0:
                raise ValidationError(
                    "max_age_seconds must be >= 0",
                    field="max_age_seconds",
                    details={"max_age_seconds": max_age},
                )
            params["max_age_seconds"] = max_age_int
        return params

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:  # type: ignore[override]
        """Execute the command."""
        try:
            params = self.validate_params(
                {k: v for k, v in kwargs.items() if k != "context"}
            )
        except ValidationError as exc:
            return self._handle_error(exc, "VALIDATION_ERROR", self.name)

        sessions_root = self._get_search_sessions_root()
        config_path = self._resolve_config_path()

        # Offload the synchronous filesystem sweep to a thread, same
        # reasoning as the periodic loop: a sessions_root with many stale
        # entries (the reported bug: one measured session held ~56k files)
        # must not block the event loop for other in-flight requests.
        result = await asyncio.to_thread(
            sweep_expired_sessions,
            sessions_root=sessions_root,
            config_path=config_path,
            now=time.time(),
            ttl_override_seconds=params.get("max_age_seconds"),
        )
        if result.deleted:
            logger.info(
                "search_sessions_purge removed %d session(s), freed %d bytes: %s",
                len(result.deleted),
                result.freed_bytes,
                result.deleted,
            )

        return SuccessResult(
            data={
                "purged_count": len(result.deleted),
                "purged_session_ids": result.deleted,
                "freed_bytes": result.freed_bytes,
            }
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return command metadata."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "parameters": {
                "max_age_seconds": {
                    "description": (
                        "Optional retention override (seconds) for this "
                        "sweep only."
                    ),
                    "type": "integer",
                    "required": False,
                },
            },
            "return_value": {
                "success": {
                    "description": "Sweep outcome.",
                    "data": {
                        "purged_count": "Number of session directories removed.",
                        "purged_session_ids": "Removed session ids.",
                        "freed_bytes": "Total bytes freed by this sweep.",
                    },
                },
            },
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "max_age_seconds is not a non-negative integer."
                },
            },
            "best_practices": [
                "The periodic background sweep (see cleaner.py) already runs "
                "on a configurable cadence; use this command for immediate, "
                "on-demand or test-driven sweeps only.",
                "A running session with a live process and fresh heartbeat is "
                "never removed, even with max_age_seconds=0.",
            ],
        }
