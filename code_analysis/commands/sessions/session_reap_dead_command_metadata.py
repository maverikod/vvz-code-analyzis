"""
Metadata for session_reap_dead MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.sessions.session_commands_metadata_common import (
    EXAMPLE_SESSION_ID,
    command_forbidden_error,
    session_id_parameter,
    session_not_found_error,
    standard_success_return,
)


def get_session_reap_dead_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_reap_dead."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Releases everything still held by client sessions that have been "
            "idle longer than the TTL: file locks, subordinate session links, "
            "advisory leases and their on-disk .lock sidecars. The session row "
            "itself is deleted, so a client returning to a reaped id gets a "
            "clean SESSION_NOT_FOUND instead of an invisible stuck lock.\n\n"
            "Liveness is measured from client_sessions.last_active_at, which "
            "every session-scoped command refreshes. A session between commands "
            "is not idle; only one whose client stopped calling is.\n\n"
            "The same sweep runs in the background on the configured cadence "
            "(code_analysis.client_session.poll_interval) and once at server "
            "startup, which is what recovers locks orphaned by a restart. This "
            "command exists for the operator who has already found a stuck lock "
            "and does not want to wait out the TTL.\n\n"
            "Each session is released independently: one row that fails does "
            "not abort the sweep, and its error is reported in 'failed'."
        ),
        "parameters": {
            "session_id": {
                **session_id_parameter(required=False),
                "description": (
                    "Optional caller session UUID4. When provided it is touched "
                    "and policy-checked first, which also guarantees the caller "
                    "cannot reap its own session with a small ttl_seconds."
                ),
                "required": False,
            },
            "ttl_seconds": {
                "description": (
                    "Idle threshold for this sweep only, between 1 and 604800. "
                    "Defaults to code_analysis.client_session.ttl_seconds. The "
                    "floor is lower than the configured one on purpose: config "
                    "drives an unattended loop, this is a deliberate act. A very "
                    "small value will reap sessions that are merely between "
                    "commands, so pair it with only_session_ids."
                ),
                "type": "integer",
                "required": False,
                "examples": [60, 3600],
            },
            "only_session_ids": {
                "description": (
                    "Restrict the sweep to these sessions. Each is still subject "
                    "to the idle test, so naming a session asks for it to be "
                    "reaped IF it is dead and never forces a live one open."
                ),
                "type": "array",
                "required": False,
                "examples": [[EXAMPLE_SESSION_ID]],
            },
            "dry_run": {
                "description": (
                    "Report which sessions would be reaped, and how many locks "
                    "each holds, without releasing anything."
                ),
                "type": "boolean",
                "required": False,
                "examples": [True, False],
            },
        },
        "return_value": standard_success_return(
            description="Sweep completed.",
            data_fields={
                "dry_run": "Echo of the dry_run flag.",
                "ttl_seconds": "Idle threshold actually applied.",
                "reaped_session_count": "Number of sessions released.",
                "released_lock_total": "File locks released across all of them.",
                "reaped": (
                    "Per-session detail: session_id, idle_seconds, "
                    "released_lock_count, released_subordinate_count, "
                    "released_advisory_lease_count."
                ),
                "failed": "Sessions that could not be released, with the error.",
                "candidate_count": "Dry run only: number of matching sessions.",
                "candidates": "Dry run only: session_id, comment, open_lock_count.",
            },
            example={
                "dry_run": False,
                "ttl_seconds": 3600,
                "reaped_session_count": 1,
                "released_lock_total": 2,
                "reaped": [
                    {
                        "session_id": EXAMPLE_SESSION_ID,
                        "idle_seconds": 7325.4,
                        "released_lock_count": 2,
                        "released_subordinate_count": 0,
                        "released_advisory_lease_count": 2,
                    }
                ],
                "failed": [],
            },
        ),
        "usage_examples": [
            {
                "description": "See what would be released, change nothing",
                "command": {"dry_run": True},
                "explanation": (
                    "Safe first step: lists idle sessions and their open lock "
                    "counts using the configured TTL."
                ),
            },
            {
                "description": "Release locks held by sessions idle over an hour",
                "command": {"ttl_seconds": 3600},
                "explanation": "Runs the sweep immediately at the given threshold.",
            },
            {
                "description": "Operator sweep from an authenticated session",
                "command": {"session_id": EXAMPLE_SESSION_ID, "ttl_seconds": 600},
                "explanation": (
                    "The caller's own session is touched first, so it is never "
                    "a candidate for its own sweep."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "COMMAND_FORBIDDEN": command_forbidden_error(),
            "VALIDATION_ERROR": {
                "description": (
                    "ttl_seconds outside 1..604800, or only_session_ids that is "
                    "not a list of strings."
                ),
                "solution": (
                    "Pass a threshold inside the range, or omit it to use the "
                    "configured TTL. To stop reaping entirely, set "
                    "code_analysis.client_session.reap_dead_sessions to false."
                ),
            },
        },
        "best_practices": [
            "Run with dry_run=true first: the report names every session and its lock count.",
            "Prefer fixing a client that leaks sessions over lowering the TTL; a short TTL can reap a live but idle editor.",
            "The background reaper already covers restarts — reach for this command when you need the locks back now.",
        ],
    }
