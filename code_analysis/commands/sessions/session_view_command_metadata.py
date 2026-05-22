"""
Metadata for session_view MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.sessions.session_commands_metadata_common import (
    EXAMPLE_PROJECT_ID,
    EXAMPLE_SESSION_ID,
    command_forbidden_error,
    session_id_parameter,
    session_not_found_error,
    standard_success_return,
)
from code_analysis.commands.sessions.subordinate_session_commands_metadata import (
    EXAMPLE_SERVER_UUID,
)


def get_session_view_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_view."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Returns an aggregated view of one client session:\n\n"
            "1. **locked_files_by_project** — file locks held by the session, "
            "grouped by project. Each project entry includes project_id, "
            "project_presentation (human-readable label from name/comment), "
            "and files with file_id, file_path (project-relative when indexed), "
            "locked_at.\n\n"
            "2. **subordinate_sessions** — links where this session is the parent. "
            "Each entry includes server_uuid, session_presentation (parent session "
            "comment when the session row exists), server_presentation "
            "(title/description/version when server_uuid matches this server's "
            "registration.instance_uuid), and link_comment from the "
            "subordinate_sessions row.\n\n"
            "Execution order: SessionTouchRule -> SecurityPolicy -> view build."
        ),
        "parameters": {
            "session_id": session_id_parameter(),
        },
        "return_value": standard_success_return(
            description="Session view payload.",
            data_fields={
                "session_id": "Requested session UUID4.",
                "locked_files_by_project": "List of per-project lock groups.",
                "locked_file_count": "Total lock rows for this session.",
                "subordinate_sessions": "Subordinate session links for this parent.",
                "subordinate_session_count": "Number of subordinate links.",
            },
            example={
                "session_id": EXAMPLE_SESSION_ID,
                "locked_file_count": 1,
                "locked_files_by_project": [
                    {
                        "project_id": EXAMPLE_PROJECT_ID,
                        "project_presentation": "vast_srv — test project",
                        "files": [
                            {
                                "file_id": "660e8400-e29b-41d4-a716-446655440001",
                                "file_path": "src/main.py",
                                "locked_at": 2460100.5,
                            }
                        ],
                    }
                ],
                "subordinate_session_count": 1,
                "subordinate_sessions": [
                    {
                        "server_uuid": EXAMPLE_SERVER_UUID,
                        "session_presentation": "worker session",
                        "server_presentation": {
                            "title": "Code Analysis Server",
                            "description": "…",
                            "version": "1.0.4",
                        },
                        "link_comment": "planner worker",
                    }
                ],
            },
        ),
        "usage_examples": [
            {
                "description": "Inspect locks and subordinates for a session",
                "command": {"session_id": EXAMPLE_SESSION_ID},
                "explanation": (
                    "Use before session_delete to see open files and child sessions."
                ),
            }
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "COMMAND_FORBIDDEN": command_forbidden_error(),
        },
        "best_practices": [
            "Call session_close_file for each open file before session_delete.",
            "server_presentation is populated only for the local server instance UUID.",
        ],
    }
