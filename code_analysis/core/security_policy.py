"""
SecurityPolicy evaluator: determines whether a session may execute a command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

POLICY_DISABLED = "disabled"
POLICY_ALLOWLIST = "allowlist"
POLICY_DENYLIST = "denylist"


def is_command_permitted(
    database: Any,
    session_id: str,
    command_name: str,
    server_uuid: str,
    policy_mode: str,
) -> bool:
    """
    Evaluate whether a session may execute a command on a server.

    Uses Role (C-007) and RolePermission (C-008) data from the session service
    (C-004) to determine access under the given SecurityPolicy mode (C-009).

    Policy semantics:
    - disabled: always returns True. No DB queries performed.
    - allowlist: returns True only if the session has at least one role whose
      permissions include (command_name, server_uuid). Returns False otherwise.
    - denylist: returns False only if the session has at least one role whose
      permissions explicitly deny (command_name, server_uuid). Returns True otherwise.

    Args:
        database: DB connection with .execute() method.
        session_id: UUID4 string of the active session.
        command_name: MCP command name being requested.
        server_uuid: UUID4 string of the proxy server.
        policy_mode: One of 'disabled', 'allowlist', 'denylist'.

    Returns:
        True if the command is permitted, False if denied.
    """
    if policy_mode == POLICY_DISABLED:
        return True

    from code_analysis.core.client_sessions import (
        get_permissions_for_roles,
        get_roles_for_session,
    )

    roles = get_roles_for_session(database, session_id)
    role_ids: list[str] = [str(r["role_id"]) for r in roles]

    if policy_mode == POLICY_ALLOWLIST:
        if not role_ids:
            return False
        permitted = get_permissions_for_roles(database, role_ids, server_uuid)
        return command_name in permitted

    if policy_mode == POLICY_DENYLIST:
        if not role_ids:
            return True
        denied = get_permissions_for_roles(database, role_ids, server_uuid)
        return command_name not in denied

    # Unknown policy mode: fail safe (deny)
    return False
