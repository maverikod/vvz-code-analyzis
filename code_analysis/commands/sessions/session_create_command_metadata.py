"""
Metadata for session_create MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.sessions.session_commands_metadata_common import (
    EXAMPLE_ROLE_ID,
    EXAMPLE_SESSION_ID,
    standard_success_return,
)


def get_session_create_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for session_create."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Creates a new persisted client session and returns a server-generated "
            "session_id (UUID4). Client sessions identify AI/editor workflows across "
            "commands: file locks in session_file_locks are attributed to session_id, "
            "not OS PID.\n\n"
            "Operation flow:\n"
            "1. Insert row into client_sessions with comment.\n"
            "2. Optionally assign role_ids in session_roles.\n"
            "3. Return session_id, comment, created_at, last_active_at.\n\n"
            "No session_id parameter (session does not exist yet). No SessionTouchRule "
            "and no SecurityPolicy check on create.\n\n"
            "Typical workflow: session_create → pass session_id to session_open_file, "
            "edit commands, session_close_file, then session_delete when finished."
        ),
        "parameters": {
            "comment": {
                "description": (
                    "Human-readable label for the session (model name, task id, "
                    "editor window, etc.). May be an empty string."
                ),
                "type": "string",
                "required": True,
                "examples": ["cursor-agent-task-42", "manual-review"],
            },
            "role_ids": {
                "description": (
                    "Optional list of role UUID4 strings to assign at creation. "
                    "Roles control SecurityPolicy when security.policy is allowlist "
                    "or denylist."
                ),
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "examples": [[EXAMPLE_ROLE_ID]],
            },
        },
        "return_value": standard_success_return(
            description="Session row created.",
            data_fields={
                "session_id": "New UUID4 primary key — use on all subsequent session commands.",
                "comment": "Echo of the request comment.",
                "created_at": "Julian day timestamp at insert.",
                "last_active_at": "Initially equal to created_at; updated on touch.",
            },
            example={
                "session_id": EXAMPLE_SESSION_ID,
                "comment": "cursor-agent-task-42",
                "created_at": 2460100.5,
                "last_active_at": 2460100.5,
            },
        ),
        "usage_examples": [
            {
                "description": "Create a session with a label",
                "command": {"comment": "cursor-agent-task-42"},
                "explanation": "Returns session_id for later session_open_file and policy-aware commands.",
            },
            {
                "description": "Create session with roles",
                "command": {
                    "comment": "restricted-agent",
                    "role_ids": [EXAMPLE_ROLE_ID],
                },
                "explanation": "Assigns roles before any SecurityPolicy-checked command runs.",
            },
        ],
        "error_cases": {
            "DATABASE_ERROR": {
                "description": "Insert or role assignment failed (transaction rolled back).",
                "solution": "Check server logs and database connectivity; retry session_create.",
            },
        },
        "best_practices": [
            "Create one session per agent run or editor context; reuse session_id until done.",
            "Store returned session_id client-side; it is required for lock and policy-aware commands.",
            "Assign role_ids at creation when using security.policy allowlist or denylist.",
            "Call session_delete (or force=true) when abandoning a session to release DB rows.",
        ],
    }
