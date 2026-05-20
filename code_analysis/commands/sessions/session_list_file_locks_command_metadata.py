"""
Metadata for session_list_file_locks MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.sessions.session_commands_metadata_common import (
    EXAMPLE_FILE_ID,
    EXAMPLE_PROJECT_ID,
    EXAMPLE_SESSION_ID,
    command_forbidden_error,
    session_id_parameter,
    session_not_found_error,
    standard_success_return,
)


def get_session_list_file_locks_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_list_file_locks."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Returns all file locks held by the given session from session_file_locks.\n\n"
            "Execution order:\n"
            "1. SessionTouchRule.\n"
            "2. SecurityPolicy check.\n"
            "3. SELECT locks ordered by locked_at.\n\n"
            "Read-only with respect to locks (no acquire/release). Use before "
            "session_delete to ensure open_lock_count is zero."
        ),
        "parameters": {
            "session_id": session_id_parameter(),
        },
        "return_value": standard_success_return(
            description="Lock list returned.",
            data_fields={
                "session_id": "Echo of request session_id.",
                "locks": ("List of {project_id, file_id, locked_at} for this session."),
                "count": "Number of lock rows.",
            },
            example={
                "session_id": EXAMPLE_SESSION_ID,
                "locks": [
                    {
                        "project_id": EXAMPLE_PROJECT_ID,
                        "file_id": EXAMPLE_FILE_ID,
                        "locked_at": 2460100.5,
                    }
                ],
                "count": 1,
            },
        ),
        "usage_examples": [
            {
                "description": "Inspect locks before deleting session",
                "command": {"session_id": EXAMPLE_SESSION_ID},
                "explanation": (
                    "If count > 0, call session_close_file for each triple or use "
                    "session_delete with force=true."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "COMMAND_FORBIDDEN": command_forbidden_error(),
        },
        "best_practices": [
            "Run after errors on session_delete (SESSION_HAS_LOCKS).",
            "Map file_id back to paths via list_project_files when planning closes.",
            "Does not list locks owned by other sessions — use operator DB tools for global view.",
        ],
    }
