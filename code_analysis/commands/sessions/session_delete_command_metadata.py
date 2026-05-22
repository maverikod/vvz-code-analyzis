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

_FORCE_SCHEMA_DESCRIPTION = (
    "Destructive override for session teardown. "
    "Default is false: omit this parameter or pass false for the safe path. "
    "When false, deletion succeeds only if the session has zero rows in "
    "session_file_locks and zero rows in subordinate_sessions where this "
    "session is parent_session_id; otherwise SESSION_HAS_LOCKS or "
    "SESSION_HAS_SUBORDINATES is returned and no data is changed. "
    "When true, deletes subordinate server link rows for this session, "
    "releases all session_file_locks for this session, then deletes the "
    "client_sessions row for session_id."
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
            "Terminates one client session row in client_sessions. Session touch "
            "is NOT applied (the session is ending).\n\n"
            "**Parameter force defaults to false.** If the client omits force, "
            "behavior is identical to force=false.\n\n"
            "Execution order:\n"
            "1. SESSION_NOT_FOUND if session_id is absent from client_sessions.\n"
            "2. SecurityPolicy check for command session_delete on this server "
            "instance (skipped when policy is disabled).\n"
            "3. When force=false (default):\n"
            "   a. If session_file_locks has any row for session_id → "
            "SESSION_HAS_LOCKS (no mutation).\n"
            "   b. Else if subordinate_sessions has any row with "
            "parent_session_id=session_id → SESSION_HAS_SUBORDINATES (no mutation).\n"
            "   c. Else DELETE the client_sessions row.\n"
            "4. When force=true:\n"
            "   a. DELETE all subordinate_sessions rows where parent_session_id "
            "equals session_id.\n"
            "   b. DELETE all session_file_locks rows for session_id.\n"
            "   c. DELETE the client_sessions row for session_id.\n\n"
            "Link rows in subordinate_sessions CASCADE when the parent "
            "client_sessions row is deleted. session_roles rows CASCADE on session "
            "delete.\n\n"
            "Does not delete runtime_lock_sessions or file_advisory_lock_leases; "
            "use advisory-lock commands separately if needed."
        ),
        "parameters": {
            "session_id": session_id_parameter(),
            "force": {
                "description": _FORCE_SCHEMA_DESCRIPTION,
                "type": "boolean",
                "required": False,
                "default": False,
                "notes": (
                    "JSON schema default is false. Runtime default in execute() is "
                    "also false when the parameter is omitted."
                ),
            },
        },
        "return_value": standard_success_return(
            description="Session row removed from client_sessions.",
            data_fields={
                "session_id": "UUID4 of the deleted session (echo of request).",
                "deleted": "Always true on success.",
                "released_lock_count": (
                    "Count of session_file_locks rows deleted for session_id during "
                    "this call. Always present; 0 when force=false (locks must already "
                    "be absent) or when force=true but there were no locks."
                ),
                "released_subordinate_count": (
                    "Count of subordinate_sessions link rows deleted for this session "
                    "during this call. Always present; 0 when force=false (links must "
                    "already be absent) or when force=true but there were no links."
                ),
            },
            example={
                "session_id": EXAMPLE_SESSION_ID,
                "deleted": True,
                "released_lock_count": 0,
                "released_subordinate_count": 0,
            },
        ),
        "usage_examples": [
            {
                "description": "Safe delete with default force=false (parameter omitted)",
                "command": {"session_id": EXAMPLE_SESSION_ID},
                "explanation": (
                    "Equivalent to force=false. Succeeds only when session_view would "
                    "show locked_file_count=0 and subordinate_session_count=0."
                ),
            },
            {
                "description": "Safe delete with explicit force=false",
                "command": {"session_id": EXAMPLE_SESSION_ID, "force": False},
                "explanation": "Same as omitting force; fails if locks or subordinates exist.",
            },
            {
                "description": "Force delete with open locks and subordinate sessions",
                "command": {"session_id": EXAMPLE_SESSION_ID, "force": True},
                "explanation": (
                    "Deletes subordinate_sessions link rows and session_file_locks rows "
                    "for session_id, then deletes the client_sessions row."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "SESSION_HAS_LOCKS": {
                "description": (
                    "force is false (explicit or default) and session_file_locks "
                    "contains at least one row for session_id."
                ),
                "message": (
                    "Session '<uuid>' has N open file lock(s). Use force=True to release."
                ),
                "solution": (
                    "Call session_close_file per lock, session_view or "
                    "session_list_file_locks to inspect, or retry with force=true."
                ),
            },
            "SESSION_HAS_SUBORDINATES": {
                "description": (
                    "force is false (explicit or default) and subordinate_sessions "
                    "contains at least one row with parent_session_id=session_id."
                ),
                "message": (
                    "Session '<uuid>' has N subordinate session link(s). "
                    "Use force=True to delete them."
                ),
                "solution": (
                    "Remove links with subordinate_session_delete, inspect via "
                    "session_view, or retry with force=true to delete link rows."
                ),
            },
            "COMMAND_FORBIDDEN": command_forbidden_error(),
        },
        "best_practices": [
            "Prefer omitting force (default false) after session_close_file and "
            "subordinate_session_delete cleanup.",
            "Call session_view before delete to inspect locked_files_by_project and "
            "subordinate_sessions.",
            "Use force=true only when operator-side teardown must remove link rows and "
            "file locks without manual cleanup.",
            "Do not reuse a deleted session_id — call session_create for a new session.",
        ],
    }
