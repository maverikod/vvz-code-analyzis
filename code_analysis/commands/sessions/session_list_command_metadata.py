"""
Metadata for session_list MCP command.

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


def get_session_list_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_list."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Lists all client sessions from the database, each enriched with "
            "open_lock_count. Optional stale_threshold_seconds filters sessions "
            "idle longer than N seconds.\n\n"
            "Visibility (config sessions.show_session_ids):\n"
            "- false (default): session_id may be omitted; session_id is never "
            "included in output rows (privacy / operator listing).\n"
            "- true: session_id is required on input (SESSION_ID_REQUIRED if missing); "
            "touch and SecurityPolicy run; session_id appears in each row.\n\n"
            "When session_id is provided (and show_session_ids allows it): touch "
            "updates last_active_at, then SecurityPolicy is checked, then listing runs."
        ),
        "parameters": {
            "session_id": {
                **session_id_parameter(required=False),
                "description": (
                    "Optional caller session UUID4. Required when "
                    "sessions.show_session_ids is true in server config. When "
                    "provided, touch and SecurityPolicy apply before listing."
                ),
                "required": False,
            },
            "stale_threshold_seconds": {
                "description": (
                    "If set (minimum 1), return only sessions whose last_active_at "
                    "is older than this many seconds."
                ),
                "type": "integer",
                "required": False,
                "examples": [3600, 86400],
            },
        },
        "return_value": standard_success_return(
            description="Session list returned.",
            data_fields={
                "sessions": (
                    "List of session dicts: comment, created_at, last_active_at, "
                    "open_lock_count; session_id only when show_session_ids=true."
                ),
                "count": "Length of sessions list.",
                "show_session_ids": "Echo of config sessions.show_session_ids.",
            },
            example={
                "sessions": [
                    {
                        "session_id": EXAMPLE_SESSION_ID,
                        "comment": "agent-1",
                        "created_at": 2460100.0,
                        "last_active_at": 2460100.5,
                        "open_lock_count": 1,
                    }
                ],
                "count": 1,
                "show_session_ids": True,
            },
        ),
        "usage_examples": [
            {
                "description": "List all sessions (IDs hidden in config)",
                "command": {},
                "explanation": (
                    "When show_session_ids=false, returns comments and lock counts "
                    "without session_id in rows."
                ),
            },
            {
                "description": "List stale sessions",
                "command": {"stale_threshold_seconds": 3600},
                "explanation": "Returns sessions idle more than one hour.",
            },
            {
                "description": "List with caller session (show_session_ids=true)",
                "command": {"session_id": EXAMPLE_SESSION_ID},
                "explanation": "Touches caller session, applies policy, returns rows with session_id.",
            },
        ],
        "error_cases": {
            "SESSION_ID_REQUIRED": {
                "description": "sessions.show_session_ids is true but session_id omitted.",
                "solution": "Pass session_id from session_create or disable show_session_ids in config.",
            },
            "SESSION_NOT_FOUND": session_not_found_error(),
            "COMMAND_FORBIDDEN": command_forbidden_error(),
        },
        "best_practices": [
            "Use stale_threshold_seconds for cleanup dashboards, not for routine agent work.",
            "When show_session_ids=false, use session_create output client-side — list is aggregate only.",
            "Combine with casmgr or operator tools for session administration.",
        ],
    }
