"""
Suite: git — git config/remote/branch-tracking and GitHub API lifecycle.

Exercises: git_show, git_branch_compare, git_identity_set, git_config_get,
git_remote_add, git_remote_set_url, git_remote_set_push_url,
git_remote_rename, git_remote_remove, git_branch_set_upstream,
git_branch_track_remote; plus GitHub API commands (verify-only).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_git import run_git_lifecycle
from realsrv_test.core.lifecycle_github import run_github_lifecycle

SUITE_NAME = "git"
LIFECYCLE_RUNNERS = (run_git_lifecycle, run_github_lifecycle)
