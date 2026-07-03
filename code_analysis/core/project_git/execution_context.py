"""
Ownership invariant enforcement for project-scoped git and write operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
from typing import Optional, Tuple

OWNERSHIP_VIOLATION_OUTCOME = "GIT_PRIVILEGED_USER_REFUSED"


def check_unprivileged_execution_context() -> Tuple[bool, Optional[str]]:
    """
    Verify that the current process is running as the unprivileged server user.

    Reads the effective user id of the running process via os.geteuid() and
    refuses when it is 0 (the privileged root user). Intended to be called
    before every git operation and every write operation executes, so that
    files and repository objects created or updated by the operation retain
    the unprivileged server user's ownership. This function never changes
    ownership of any file (no chown is performed anywhere); it only reports
    whether the current execution context is already unprivileged.

    Returns:
        A tuple (allowed, outcome). When the effective user id is not 0,
        returns (True, None) and the caller may proceed with the git or
        write operation. When the effective user id is 0, returns
        (False, "GIT_PRIVILEGED_USER_REFUSED") and the caller must refuse
        to perform the git or write operation.
    """
    effective_user_id = os.geteuid()
    if effective_user_id == 0:
        return (False, OWNERSHIP_VIOLATION_OUTCOME)
    return (True, None)
