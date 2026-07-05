"""
Ownership invariant enforcement for project-scoped git and write operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
from typing import Optional, Tuple

OWNERSHIP_VIOLATION_OUTCOME = "GIT_PRIVILEGED_USER_REFUSED"

_ROOT_OVERRIDE_ENV_VAR = "CASMGR_ALLOW_ROOT"
_TRUTHY_VALUES = {"1", "true", "yes"}


def _root_override_enabled() -> bool:
    """Return True when CASMGR_ALLOW_ROOT is set to a truthy value.

    Truthy values are "1", "true", or "yes" (case-insensitive, surrounding
    whitespace ignored). Any other value, or the variable being unset, is
    treated as not enabled.
    """
    return os.environ.get(_ROOT_OVERRIDE_ENV_VAR, "").strip().lower() in _TRUTHY_VALUES


def check_unprivileged_execution_context() -> Tuple[bool, Optional[str]]:
    """
    Verify that the current process is running as the unprivileged server user,
    or that root execution has been explicitly allowed via CASMGR_ALLOW_ROOT.

    Reads the effective user id of the running process via os.geteuid(). When
    it is 0 (the privileged root user), this normally refuses. However, when
    the environment variable CASMGR_ALLOW_ROOT is set to a truthy value ("1",
    "true", or "yes", case-insensitive) — as in the all-in-one container
    deployment where the daemon intentionally runs as root while PostgreSQL
    runs unprivileged — root execution is allowed instead of refused. Intended
    to be called before every git operation and every write operation
    executes, so that files and repository objects created or updated by the
    operation retain the unprivileged server user's ownership whenever the
    override is not in effect. This function never changes ownership of any
    file (no chown is performed anywhere); it only reports whether the
    current execution context is acceptable.

    Returns:
        A tuple (allowed, outcome). Returns (True, None) when the effective
        user id is not 0, or when it is 0 and CASMGR_ALLOW_ROOT is truthy.
        Returns (False, "GIT_PRIVILEGED_USER_REFUSED") when the effective
        user id is 0 and CASMGR_ALLOW_ROOT is not set to a truthy value; the
        caller must then refuse to perform the git or write operation.
    """
    effective_user_id = os.geteuid()
    if effective_user_id == 0 and not _root_override_enabled():
        return (False, OWNERSHIP_VIOLATION_OUTCOME)
    return (True, None)
