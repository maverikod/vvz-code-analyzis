"""
Suite: remotebranch — remote-branch inspection against a real server.

Closes TODO 487773a8: there was no way to ask what a remote has right now
(git_branch_list only reads the fetch cache), and no way to prune stale tracking
refs without also fetching.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_remote_branch import (
    run_remote_branch_list,
    run_remote_branch_prune,
    run_remote_branch_write_cycle,
)

SUITE_NAME = "remotebranch"
LIFECYCLE_RUNNERS = (
    run_remote_branch_list,
    run_remote_branch_write_cycle,
    run_remote_branch_prune,
)
