"""
Metadata for session_delete MCP command.

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


def get_session_delete_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_delete."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Deletes a client session from client_sessions. Session touch is NOT "
            "applied (the session is terminating).\n\n"
            "Execution order:\n"
            "1. SESSION_NOT_FOUND if session_id missing.\n"
            "2. SecurityPolicy check (when session exists).\n"
            "3. If open file locks exist and force=false → SESSION_HAS_LOCKS.\n"
            "4. If force=true → delete all session_file_locks for this session, "
            "then delete the session row.\n"
            "5. If no locks → delete session row.\n\n"
            "Destructive: removes the session record. Use force=true to release "
            "locks without calling session_close_file for each file."
        ),
        "parameters": {
            "session_id": session_id_parameter(),
            "force": {
                "description": (
                    "When false (default), deletion fails if the session holds any "
                    "file locks. When true, all locks are released first, then the "
                    "session is deleted."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
        },
        "return_value": standard_success_return(
            description="Session deleted.",
            data_fields={
                "session_id": "UUID4 that was deleted.",
                "deleted": "Always true on success.",
                "released_lock_count": (
                    "Number of session_file_locks rows removed when force=true; "
                    "0 when there were no locks or force was not needed."
                ),
            },
            example={
                "session_id": EXAMPLE_SESSION_ID,
                "deleted": True,
                "released_lock_count": 2,
            },
        ),
        "usage_examples": [
            {
                "description": "Delete session after all files closed",
                "command": {"session_id": EXAMPLE_SESSION_ID},
                "explanation": "Succeeds when open_lock_count is zero.",
            },
            {
                "description": "Force-delete session with open locks",
                "command": {"session_id": EXAMPLE_SESSION_ID, "force": True},
                "explanation": "Releases all file locks then removes the session.",
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "SESSION_HAS_LOCKS": {
                "description": "Session has open file locks and force=false.",
                "message": "Session ... has N open file lock(s). Use force=True to release.",
                "solution": (
                    "Call session_close_file for each lock, session_list_file_locks "
                    "to inspect, or retry with force=true."
                ),
            },
            "COMMAND_FORBIDDEN": command_forbidden_error(),
        },
        "best_practices": [
            "Release locks with session_close_file before delete when possible.",
            "Use force=true only when abandoning a stuck session operator-side.",
            "Verify with session_list that the session is gone (when IDs are visible).",
            "Do not reuse a deleted session_id — create a new session_create.",
        ],
    }
