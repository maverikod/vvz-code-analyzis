"""
Metadata for session_close_file MCP command.

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


def get_session_close_file_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_close_file."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Releases a file lock for (session_id, project_id, file_id). Idempotent: "
            "if no lock exists, was_locked is false and the call still succeeds.\n\n"
            "Execution order:\n"
            "1. SessionTouchRule.\n"
            "2. SecurityPolicy check.\n"
            "3. DELETE matching row from session_file_locks.\n\n"
            "Does not modify file content on disk — only the lock record."
        ),
        "parameters": {
            "session_id": session_id_parameter(),
            "project_id": project_id_parameter(),
            "file_id": file_id_parameter(),
        },
        "return_value": standard_success_return(
            description="Lock release attempted.",
            data_fields={
                "released": "True if a lock row was deleted.",
                "was_locked": "True if a lock existed before this call.",
                "session_id": "Echo of request session_id.",
                "project_id": "Echo of request project_id.",
                "file_id": "Echo of request file_id.",
            },
            example={
                "released": True,
                "was_locked": True,
                "session_id": EXAMPLE_SESSION_ID,
                "project_id": EXAMPLE_PROJECT_ID,
                "file_id": EXAMPLE_FILE_ID,
            },
        ),
        "usage_examples": [
            {
                "description": "Release lock after editing",
                "command": {
                    "session_id": EXAMPLE_SESSION_ID,
                    "project_id": EXAMPLE_PROJECT_ID,
                    "file_id": EXAMPLE_FILE_ID,
                },
                "explanation": "Allows session_delete without force when this was the last lock.",
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "COMMAND_FORBIDDEN": command_forbidden_error(),
        },
        "best_practices": [
            "Always close files opened with session_open_file before session_delete.",
            "was_locked=false means the triple was not locked — safe to ignore or log.",
            "Confirm with session_list_file_locks that count dropped.",
        ],
    }
