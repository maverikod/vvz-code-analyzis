"""
Metadata for session_open_file MCP command.

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
    file_id_parameter,
    project_id_parameter,
    session_id_parameter,
    session_not_found_error,
    standard_success_return,
)


def get_session_open_file_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_open_file."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Acquires a persisted file lock for (session_id, project_id, file_id) "
            "in session_file_locks. Idempotent: if the lock already exists, acquired "
            "is false and no error is returned.\n\n"
            "Execution order:\n"
            "1. SessionTouchRule — update last_active_at or SESSION_NOT_FOUND.\n"
            "2. SecurityPolicy check.\n"
            "3. Insert into session_file_locks when absent (idempotent).\n\n"
            "Locks are logical DB records (not OS flock). They attribute which session "
            "has a file open for coordination and session_delete guards."
        ),
        "parameters": {
            "session_id": session_id_parameter(),
            "project_id": project_id_parameter(),
            "file_id": file_id_parameter(),
        },
        "return_value": standard_success_return(
            description="Lock acquisition attempted.",
            data_fields={
                "acquired": "True if a new lock row was inserted; false if already held.",
                "session_id": "Echo of request session_id.",
                "project_id": "Echo of request project_id.",
                "file_id": "Echo of request file_id.",
            },
            example={
                "acquired": True,
                "session_id": EXAMPLE_SESSION_ID,
                "project_id": EXAMPLE_PROJECT_ID,
                "file_id": EXAMPLE_FILE_ID,
            },
        ),
        "usage_examples": [
            {
                "description": "Open a file for editing under a session",
                "command": {
                    "session_id": EXAMPLE_SESSION_ID,
                    "project_id": EXAMPLE_PROJECT_ID,
                    "file_id": EXAMPLE_FILE_ID,
                },
                "explanation": (
                    "Acquires a logical DB lock for coordination and session_delete guards. "
                    "Independent of universal_file_open edit sessions."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "COMMAND_FORBIDDEN": command_forbidden_error(),
        },
        "best_practices": [
            "Resolve project_id via list_projects and file_id via list_project_files.",
            "Pair every session_open_file with session_close_file when done.",
            "Check acquired=false to detect duplicate open in the same session.",
            "Verify locks with session_list_file_locks before session_delete.",
        ],
    }
