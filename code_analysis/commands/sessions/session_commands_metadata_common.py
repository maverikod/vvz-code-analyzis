"""
Shared metadata fragments for session_management MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

EXAMPLE_SESSION_ID = "11111111-1111-4111-8111-111111111111"
EXAMPLE_PROJECT_ID = "550e8400-e29b-41d4-a716-446655440000"
EXAMPLE_FILE_ID = "660e8400-e29b-41d4-a716-446655440001"
EXAMPLE_ROLE_ID = "770e8400-e29b-41d4-a716-446655440002"


def session_id_parameter(*, required: bool = True) -> Dict[str, Any]:
    """Metadata entry for session_id."""
    return {
        "description": (
            "UUID4 of the client session. Obtain via session_create. "
            "Required on most commands; updates last_active_at when the session "
            "is touched before execution."
        ),
        "type": "string",
        "required": required,
        "examples": [EXAMPLE_SESSION_ID],
    }


def project_id_parameter() -> Dict[str, Any]:
    """Metadata entry for project_id."""
    return {
        "description": (
            "Project UUID. Use list_projects to discover valid project_id values."
        ),
        "type": "string",
        "required": True,
        "examples": [EXAMPLE_PROJECT_ID],
    }


def file_id_parameter() -> Dict[str, Any]:
    """Metadata entry for file_id."""
    return {
        "description": (
            "File record UUID from the files table for the given project. "
            "Resolve via list_project_files or indexing APIs — not a host path."
        ),
        "type": "string",
        "required": True,
        "examples": [EXAMPLE_FILE_ID],
    }


def session_not_found_error() -> Dict[str, Any]:
    """SESSION_NOT_FOUND error_cases entry."""
    return {
        "description": "session_id is absent from client_sessions.",
        "message": "Session '<uuid>' not found.",
        "solution": "Call session_create or session_list (when permitted) and retry.",
    }


def command_forbidden_error() -> Dict[str, Any]:
    """COMMAND_FORBIDDEN error_cases entry."""
    return {
        "description": (
            "SecurityPolicy (config security.policy) denies this command for "
            "the session's roles on this server instance."
        ),
        "message": "Command '...' is forbidden for session '...' under policy '...'.",
        "solution": (
            "Adjust role_permissions, assign roles at session_create, or set "
            "security.policy to disabled for development."
        ),
    }


def standard_success_return(
    *,
    description: str,
    data_fields: Dict[str, str],
    example: Dict[str, Any],
) -> Dict[str, Any]:
    """Standard return_value block for session commands."""
    return {
        "success": {
            "description": description,
            "data": {"success": "Always True on success.", **data_fields},
            "example": {"success": True, **example},
        },
        "error": {
            "description": "Command failed before or during execution.",
            "code": "Stable error code from error_cases.",
            "message": "Human-readable message.",
        },
    }
