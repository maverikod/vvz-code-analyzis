"""
Hardcoded read-only command whitelist and validation for batch invocation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional

# Immutable whitelist of command names allowed in read-only batch execution.
# Only entity-returning analysis commands; no mutating commands.
# No dynamic extension from user input or config (blackstop).
READ_ONLY_BATCH_WHITELIST: frozenset[str] = frozenset(
    {
        "get_class_hierarchy",
        "list_code_entities",
        "get_code_entity_info",
        "find_dependencies",
        "find_usages",
        "get_entity_dependencies",
        "get_entity_dependents",
        "export_graph",
    }
)

ERROR_CODE_NOT_WHITELISTED = "BATCH_COMMAND_NOT_WHITELISTED"


def validate_command(command_name: str) -> tuple[bool, Optional[dict]]:
    """
    Validate a command name against the read-only batch whitelist.

    Args:
        command_name: The command name to check (e.g. from batch request).

    Returns:
        (True, None) if the command is whitelisted.
        (False, error_payload) if the command is not whitelisted. error_payload
        is a dict with "error", "error_code", "command", "message" for
        deterministic rejection of non-whitelisted or mutating commands.
    """
    if not command_name or not isinstance(command_name, str):
        payload = _make_error_payload(
            str(command_name),
            "Command name must be a non-empty string.",
        )
        return False, payload
    name = command_name.strip()
    if not name:
        payload = _make_error_payload(command_name, "Command name must be non-empty.")
        return False, payload
    if name in READ_ONLY_BATCH_WHITELIST:
        return True, None
    payload = _make_error_payload(
        name,
        "Command is not in the read-only batch whitelist.",
    )
    return False, payload


def _make_error_payload(command: str, message: str) -> dict:
    """Build explicit error payload for non-whitelisted command."""
    return {
        "error": message,
        "error_code": ERROR_CODE_NOT_WHITELISTED,
        "command": command,
        "message": message,
    }
