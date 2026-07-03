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

from mcp_proxy_adapter.commands.command_registry import registry

logger = logging.getLogger(__name__)


def register_commands_git_github(reg: registry) -> None:
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
        from .commands.git_ops.git_show_command import GitShowCommand
        from .commands.git_ops.git_remote_command import GitRemoteCommand
        from .commands.git_ops.git_blame_command import GitBlameCommand

        reg.register(GitStatusCommand, "custom")
        reg.register(GitLogCommand, "custom")
        reg.register(GitDiffCommand, "custom")
        reg.register(GitBranchCommand, "custom")
        reg.register(GitShowCommand, "custom")
        reg.register(GitRemoteCommand, "custom")
        reg.register(GitBlameCommand, "custom")
        logger.info(
            "✅ Registered git read commands: git_status, git_log, git_diff, "
            "git_branch, git_show, git_remote, git_blame"
        )
    except ImportError as e:
        logger.warning("Failed to import git read commands: %s", e)

    try:
        from .commands.git_fetch_command import GitFetchCommand
        from .commands.git_pull_command import GitPullCommand
        from .commands.git_push_command import GitPushCommand

        reg.register(GitFetchCommand, "custom")
        reg.register(GitPullCommand, "custom")
        reg.register(GitPushCommand, "custom")
        logger.info("✅ Registered git remote commands: git_fetch, git_pull, git_push")
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
