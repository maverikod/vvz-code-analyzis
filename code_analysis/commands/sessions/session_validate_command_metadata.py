"""
Metadata for session_validate MCP command.

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


def get_session_validate_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_validate."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Read-only check that ``session_id`` exists in ``client_sessions``. "
            "External editors call this before lock/transfer commands. The analysis "
            "server owns the session table and watched project files; the editor does "
            "not store session rows locally.\n\n"
            "When ``touch=true``, ``last_active_at`` is updated (same as other "
            "session-aware commands). Default ``touch=false`` performs no writes."
        ),
        "parameters": {
            "session_id": session_id_parameter(),
            "touch": {
                "description": "Update last_active_at when true. Default false.",
                "type": "boolean",
                "required": False,
                "default": False,
            },
        },
        "return_value": standard_success_return(
            description="Session exists.",
            data_fields={
                "valid": "Always true on success.",
                "session_id": "Echo of the request.",
                "comment": "Session label from client_sessions.",
                "created_at": "Julian day timestamp at creation.",
                "last_active_at": "Julian day timestamp of last touch (if touch=true).",
            },
            example={
                "valid": True,
                "session_id": EXAMPLE_SESSION_ID,
                "comment": "editor-window-1",
                "created_at": 2460000.0,
                "last_active_at": 2460001.0,
            },
        ),
        "usage_examples": [
            {
                "description": "Validate before file lock",
                "command": {"session_id": EXAMPLE_SESSION_ID},
                "explanation": "Fails fast with SESSION_NOT_FOUND if the editor lost the id.",
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "COMMAND_FORBIDDEN": command_forbidden_error(),
        },
        "best_practices": [
            "Call session_create on this server, then reuse session_id for locks and transfer.",
            "Use touch=true only when the call should count as session activity.",
        ],
    }
