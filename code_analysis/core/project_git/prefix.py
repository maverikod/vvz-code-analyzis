"""
Reserved command-name prefix for the project-scoped git capability block.

Every command in the project-scoped git block is named under the reserved
prefix "git_", disjoint from the command names of the pre-existing
edit-session git facility, so that no command name or routing collision
can arise between the two facilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import FrozenSet

RESERVED_GIT_COMMAND_PREFIX: str = "git_"

EDIT_SESSION_GIT_COMMAND_NAMES: FrozenSet[str] = frozenset(
    {
        "session_git_log",
        "session_git_diff",
        "session_git_revert",
        "session_git_show",
        "session_git_status",
    }
)


def make_prefixed_command_name(base_name: str) -> str:
    """Build a project-scoped git command name under the reserved prefix.

    Args:
        base_name: The unprefixed command base name, for example
            "status". Must be a non-empty string that does not already
            start with the reserved prefix "git_".

    Returns:
        base_name prefixed with the reserved prefix "git_".

    Raises:
        ValueError: If base_name is empty, or if base_name already starts
            with the reserved prefix "git_".
    """
    if not base_name:
        raise ValueError("base_name must be a non-empty string")
    if base_name.startswith(RESERVED_GIT_COMMAND_PREFIX):
        raise ValueError(
            "base_name {0!r} already carries the reserved prefix {1!r}".format(
                base_name, RESERVED_GIT_COMMAND_PREFIX
            )
        )
    return "{0}{1}".format(RESERVED_GIT_COMMAND_PREFIX, base_name)


def is_reserved_git_command_name(command_name: str) -> bool:
    """Report whether command_name carries the reserved git command prefix.

    Args:
        command_name: The full command name to check.

    Returns:
        True if command_name starts with the reserved prefix "git_",
        False otherwise.
    """
    return command_name.startswith(RESERVED_GIT_COMMAND_PREFIX)


def is_disjoint_from_edit_session_git(command_name: str) -> bool:
    """Report whether command_name is disjoint from edit-session git command names.

    Args:
        command_name: The full command name to check.

    Returns:
        True if command_name is not a member of
        EDIT_SESSION_GIT_COMMAND_NAMES, False if it collides with one of
        the pre-existing edit-session git command names.
    """
    return command_name not in EDIT_SESSION_GIT_COMMAND_NAMES
