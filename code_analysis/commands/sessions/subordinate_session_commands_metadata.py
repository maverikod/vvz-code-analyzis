"""
Shared metadata for subordinate session MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.sessions.session_commands_metadata_common import (
    EXAMPLE_SESSION_ID,
    session_not_found_error,
    standard_success_return,
)

EXAMPLE_SERVER_UUID = "880e8400-e29b-41d4-a716-446655440003"

_COMPOSITE_KEY_FIELDS = {
    "parent_session_id": (
        "Leading client session UUID4. The same id is used on subordinate servers."
    ),
    "server_uuid": "Subordinate server instance UUID4 (registration.instance_uuid).",
    "comment": "Human-readable label for this server link.",
}


def composite_key_parameters(
    *, include_comment: bool = False, server_uuid_required: bool = True
) -> Dict[str, Any]:
    """Metadata parameters for composite primary key fields."""
    params: Dict[str, Any] = {
        "parent_session_id": {
            "description": _COMPOSITE_KEY_FIELDS["parent_session_id"],
            "type": "string",
            "required": True,
            "examples": [EXAMPLE_SESSION_ID],
        },
        "server_uuid": {
            "description": _COMPOSITE_KEY_FIELDS["server_uuid"],
            "type": "string",
            "required": server_uuid_required,
            "examples": [EXAMPLE_SERVER_UUID],
        },
    }
    if include_comment:
        params["comment"] = {
            "description": _COMPOSITE_KEY_FIELDS["comment"],
            "type": "string",
            "required": True,
            "examples": ["worker-on-server-b"],
        }
    return params


def composite_key_schema(*, include_comment: bool = False) -> Dict[str, Any]:
    """JSON-schema properties for composite key (+ optional comment)."""
    props: Dict[str, Any] = {
        "parent_session_id": {
            "type": "string",
            "description": _COMPOSITE_KEY_FIELDS["parent_session_id"],
        },
        "server_uuid": {
            "type": "string",
            "description": _COMPOSITE_KEY_FIELDS["server_uuid"],
        },
    }
    required = ["parent_session_id", "server_uuid"]
    if include_comment:
        props["comment"] = {
            "type": "string",
            "description": _COMPOSITE_KEY_FIELDS["comment"],
        }
        required.append("comment")
    return {"properties": props, "required": required}


def subordinate_session_not_found_error() -> Dict[str, Any]:
    """SUBORDINATE_SESSION_NOT_FOUND error_cases entry."""
    return {
        "description": "No row matches (parent_session_id, server_uuid).",
        "message": "Subordinate session link not found for parent/server.",
        "solution": "Call subordinate_session_list or verify UUIDs and retry.",
    }


def subordinate_session_already_exists_error() -> Dict[str, Any]:
    """SUBORDINATE_SESSION_ALREADY_EXISTS error_cases entry."""
    return {
        "description": "Composite primary key already present.",
        "message": "Subordinate session link already exists.",
        "solution": "Use subordinate_session_update or delete the existing link first.",
    }


def invalid_params_error() -> Dict[str, Any]:
    """INVALID_PARAMS error_cases entry."""
    return {
        "description": "UUID validation failed.",
        "message": "Invalid subordinate session parameters.",
        "solution": "Pass valid UUID4 values for parent_session_id and server_uuid.",
    }


def row_return_value(*, description: str) -> Dict[str, Any]:
    """Standard success return for row payloads."""
    return standard_success_return(
        description=description,
        data_fields={
            "parent_session_id": "Leading session UUID4 (used on the subordinate server).",
            "server_uuid": "Subordinate server instance UUID4.",
            "comment": "Link comment string.",
        },
        example={
            "parent_session_id": EXAMPLE_SESSION_ID,
            "server_uuid": EXAMPLE_SERVER_UUID,
            "comment": "worker-on-server-b",
        },
    )


def get_subordinate_session_create_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Metadata for subordinate_session_create."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Registers a leading client session on a subordinate server instance.\n\n"
            "The leading session must exist in client_sessions. Subordinate servers "
            "use parent_session_id as session_id — no second client session row is "
            "stored.\n\n"
            "The composite key (parent_session_id, server_uuid) must be unique.\n\n"
            "When server_uuid is omitted, the current server "
            "registration.instance_uuid is used."
        ),
        "parameters": composite_key_parameters(
            include_comment=True, server_uuid_required=False
        ),
        "return_value": row_return_value(description="Link created."),
        "usage_examples": [
            {
                "description": "Register leading session on this server",
                "command": {
                    "parent_session_id": EXAMPLE_SESSION_ID,
                    "comment": "planner worker",
                },
                "explanation": "server_uuid defaults to this server's instance UUID.",
            }
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": session_not_found_error(),
            "SUBORDINATE_SESSION_ALREADY_EXISTS": (
                subordinate_session_already_exists_error()
            ),
            "INVALID_PARAMS": {
                **invalid_params_error(),
                "description": (
                    "UUID validation failed or server_uuid is required when "
                    "registration.instance_uuid is unset."
                ),
            },
        },
        "best_practices": [
            "Create the leading session with session_create before linking.",
            "Use subordinate_session_list to audit links per parent or server.",
        ],
    }


def get_subordinate_session_get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Metadata for subordinate_session_get."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": "Fetch one subordinate server link by composite key.",
        "parameters": composite_key_parameters(),
        "return_value": row_return_value(description="Link row returned."),
        "usage_examples": [
            {
                "description": "Read one link",
                "command": {
                    "parent_session_id": EXAMPLE_SESSION_ID,
                    "server_uuid": EXAMPLE_SERVER_UUID,
                },
                "explanation": "Returns comment and identifiers.",
            }
        ],
        "error_cases": {
            "SUBORDINATE_SESSION_NOT_FOUND": subordinate_session_not_found_error(),
            "INVALID_PARAMS": invalid_params_error(),
        },
        "best_practices": [
            "Prefer subordinate_session_list when searching by parent only."
        ],
    }


def get_subordinate_session_update_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Metadata for subordinate_session_update."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": "Update the comment field on an existing link.",
        "parameters": composite_key_parameters(include_comment=True),
        "return_value": row_return_value(description="Updated link row."),
        "usage_examples": [
            {
                "description": "Rename link comment",
                "command": {
                    "parent_session_id": EXAMPLE_SESSION_ID,
                    "server_uuid": EXAMPLE_SERVER_UUID,
                    "comment": "renamed worker",
                },
                "explanation": "Only comment is mutable.",
            }
        ],
        "error_cases": {
            "SUBORDINATE_SESSION_NOT_FOUND": subordinate_session_not_found_error(),
            "INVALID_PARAMS": invalid_params_error(),
        },
        "best_practices": [
            "Identifiers are immutable; delete and recreate to change keys."
        ],
    }


def get_subordinate_session_delete_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Metadata for subordinate_session_delete."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Delete one subordinate server link. Does not delete the leading "
            "client_sessions row."
        ),
        "parameters": composite_key_parameters(),
        "return_value": standard_success_return(
            description="Link deleted.",
            data_fields={
                "parent_session_id": "Leading session UUID4.",
                "server_uuid": "Server instance UUID4.",
                "deleted": "Always true on success.",
            },
            example={
                "parent_session_id": EXAMPLE_SESSION_ID,
                "server_uuid": EXAMPLE_SERVER_UUID,
                "deleted": True,
            },
        ),
        "usage_examples": [
            {
                "description": "Remove link",
                "command": {
                    "parent_session_id": EXAMPLE_SESSION_ID,
                    "server_uuid": EXAMPLE_SERVER_UUID,
                },
                "explanation": "Leading session remains until session_delete.",
            }
        ],
        "error_cases": {
            "SUBORDINATE_SESSION_NOT_FOUND": subordinate_session_not_found_error(),
            "INVALID_PARAMS": invalid_params_error(),
        },
        "best_practices": [
            "Deleting a link does not close file locks on the leading session.",
        ],
    }


def get_subordinate_session_list_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Metadata for subordinate_session_list."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "List subordinate server links with optional filters on parent or "
            "server UUID."
        ),
        "parameters": {
            "parent_session_id": {
                "description": "Optional filter: leading session UUID4.",
                "type": "string",
                "required": False,
                "examples": [EXAMPLE_SESSION_ID],
            },
            "server_uuid": {
                "description": "Optional filter: server instance UUID4.",
                "type": "string",
                "required": False,
                "examples": [EXAMPLE_SERVER_UUID],
            },
        },
        "return_value": standard_success_return(
            description="Matching links.",
            data_fields={
                "links": "List of link rows.",
                "count": "Number of rows returned.",
            },
            example={
                "links": [
                    {
                        "parent_session_id": EXAMPLE_SESSION_ID,
                        "server_uuid": EXAMPLE_SERVER_UUID,
                        "comment": "worker",
                    }
                ],
                "count": 1,
            },
        ),
        "usage_examples": [
            {
                "description": "All links for a parent on any server",
                "command": {"parent_session_id": EXAMPLE_SESSION_ID},
                "explanation": "Omit other filters to widen the query.",
            }
        ],
        "error_cases": {"INVALID_PARAMS": invalid_params_error()},
        "best_practices": [
            "Combine parent_session_id and server_uuid to scope multi-server setups.",
        ],
    }
