"""
Register git block and github block MCP command classes.

Wires the project-scoped git command block (code_analysis.commands.git_ops
and the git remote commands) and the GitHub command block
(code_analysis.commands.github_read_ops_commands,
github_write_ops_commands, github_pr_merge_command) into the server's
command registry, so both capability blocks framed by G-006/T-004 are
actually invocable and not merely defined.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def register_commands_git_github(reg: Any) -> None:
    """Register the git block and github block MCP command classes.

    Args:
        reg: MCP command registry instance.

    Returns:
        None
    """
    try:
        from .commands.git_ops.git_status_command import GitStatusCommand
        from .commands.git_ops.git_log_command import GitLogCommand
        from .commands.git_ops.git_diff_command import GitDiffCommand
        from .commands.git_ops.git_branch_command import GitBranchCommand
        from .commands.git_ops.git_branch_compare_command import GitBranchCompareCommand
        from .commands.git_ops.git_branch_current_command import (
            GitBranchCurrentCommand,
        )
        from .commands.git_ops.git_branch_list_command import GitBranchListCommand
        from .commands.git_ops.git_branch_sync_status_command import (
            GitBranchSyncStatusCommand,
        )
        from .commands.git_ops.git_show_command import GitShowCommand
        from .commands.git_ops.git_remote_command import GitRemoteCommand
        from .commands.git_ops.git_blame_command import GitBlameCommand

        reg.register(GitStatusCommand, "custom")
        reg.register(GitLogCommand, "custom")
        reg.register(GitDiffCommand, "custom")
        reg.register(GitBranchCommand, "custom")
        reg.register(GitBranchCompareCommand, "custom")
        reg.register(GitBranchCurrentCommand, "custom")
        reg.register(GitBranchListCommand, "custom")
        reg.register(GitBranchSyncStatusCommand, "custom")
        reg.register(GitShowCommand, "custom")
        reg.register(GitRemoteCommand, "custom")
        reg.register(GitBlameCommand, "custom")
        logger.info(
            "✅ Registered git read commands: git_status, git_log, git_diff, "
            "git_branch, git_branch_compare, git_branch_current, "
            "git_branch_list, git_branch_sync_status, git_show, git_remote, "
            "git_blame"
        )
    except ImportError as e:
        logger.warning("Failed to import git read commands: %s", e)

    try:
        from .commands.git_branch_checkout_command import GitBranchCheckoutCommand
        from .commands.git_branch_create_command import GitBranchCreateCommand
        from .commands.git_branch_delete_command import GitBranchDeleteCommand
        from .commands.git_branch_delete_remote_command import (
            GitBranchDeleteRemoteCommand,
        )
        from .commands.git_branch_fetch_pull_commands import (
            GitBranchFetchCommand,
            GitBranchPullCommand,
        )
        from .commands.git_branch_push_command import GitBranchPushCommand
        from .commands.git_branch_track_remote_command import (
            GitBranchTrackRemoteCommand,
        )
        from .commands.git_branch_upstream_commands import (
            GitBranchSetUpstreamCommand,
            GitBranchUnsetUpstreamCommand,
        )
        from .commands.git_fetch_command import GitFetchCommand
        from .commands.git_pull_command import GitPullCommand
        from .commands.git_push_command import GitPushCommand
        from .commands.git_worktree_commands import (
            GitAddCommand,
            GitCommitCommand,
            GitConfigGetCommand,
            GitConfigListCommand,
            GitIdentityGetCommand,
            GitIdentitySetCommand,
            GitRestoreCommand,
            GitStashApplyCommand,
            GitStashDropCommand,
            GitStashListCommand,
            GitStashPushCommand,
        )

        reg.register(GitAddCommand, "custom")
        reg.register(GitBranchCheckoutCommand, "custom")
        reg.register(GitBranchCreateCommand, "custom")
        reg.register(GitBranchDeleteCommand, "custom")
        reg.register(GitBranchDeleteRemoteCommand, "custom")
        reg.register(GitBranchFetchCommand, "custom")
        reg.register(GitBranchPullCommand, "custom")
        reg.register(GitBranchPushCommand, "custom")
        reg.register(GitBranchTrackRemoteCommand, "custom")
        reg.register(GitBranchSetUpstreamCommand, "custom")
        reg.register(GitBranchUnsetUpstreamCommand, "custom")
        reg.register(GitFetchCommand, "custom")
        reg.register(GitPullCommand, "custom")
        reg.register(GitPushCommand, "custom")
        reg.register(GitCommitCommand, "custom")
        reg.register(GitConfigGetCommand, "custom")
        reg.register(GitConfigListCommand, "custom")
        reg.register(GitIdentityGetCommand, "custom")
        reg.register(GitIdentitySetCommand, "custom")
        reg.register(GitRestoreCommand, "custom")
        reg.register(GitStashApplyCommand, "custom")
        reg.register(GitStashDropCommand, "custom")
        reg.register(GitStashListCommand, "custom")
        reg.register(GitStashPushCommand, "custom")
        logger.info(
            "✅ Registered git write commands: git_add, git_branch_checkout, "
            "git_branch_create, git_branch_delete, git_branch_delete_remote, "
            "git_branch_fetch, git_branch_pull, git_branch_push, "
            "git_branch_track_remote, git_branch_set_upstream, "
            "git_branch_unset_upstream, git_fetch, git_pull, git_push, "
            "git_commit, git_config_get, git_config_list, "
            "git_identity_get, git_identity_set, git_restore, "
            "git_stash_apply, git_stash_drop, git_stash_list, git_stash_push"
        )
    except ImportError as e:
        logger.warning("Failed to import git remote commands: %s", e)

    try:
        from .commands.github_read_ops_commands import (
            GithubRepoGetCommand,
            GithubRepoListCommand,
            GithubPrListCommand,
            GithubPrGetCommand,
            GithubIssueListCommand,
        )

        reg.register(GithubRepoGetCommand, "custom")
        reg.register(GithubRepoListCommand, "custom")
        reg.register(GithubPrListCommand, "custom")
        reg.register(GithubPrGetCommand, "custom")
        reg.register(GithubIssueListCommand, "custom")
        logger.info(
            "✅ Registered github read commands: github_repo_get, "
            "github_repo_list, github_pr_list, github_pr_get, "
            "github_issue_list"
        )
    except ImportError as e:
        logger.warning("Failed to import github read commands: %s", e)

    try:
        from .commands.github_write_ops_commands import (
            GithubPrCreateCommand,
            GithubIssueCreateCommand,
            GithubIssueCommentCommand,
            GithubReleaseCreateCommand,
        )

        reg.register(GithubPrCreateCommand, "custom")
        reg.register(GithubIssueCreateCommand, "custom")
        reg.register(GithubIssueCommentCommand, "custom")
        reg.register(GithubReleaseCreateCommand, "custom")
        logger.info(
            "✅ Registered github write commands: github_pr_create, "
            "github_issue_create, github_issue_comment, "
            "github_release_create"
        )
    except ImportError as e:
        logger.warning("Failed to import github write commands: %s", e)

    try:
        from .commands.github_pr_merge_command import GithubPrMergeCommand

        reg.register(GithubPrMergeCommand, "custom")
        logger.info("✅ Registered github merge command: github_pr_merge")
    except ImportError as e:
        logger.warning("Failed to import github merge command: %s", e)
