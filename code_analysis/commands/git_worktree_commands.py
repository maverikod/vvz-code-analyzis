"""Compatibility exports for git working-tree MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.commands.git_config_commands import (
    GitConfigGetCommand,
    GitConfigListCommand,
    GitIdentityGetCommand,
    GitIdentitySetCommand,
)
from code_analysis.commands.git_history_commands import (
    GitCherryPickCommand,
    GitCleanCommand,
    GitMergeCommand,
    GitRebaseCommand,
    GitResetCommand,
    GitRevertCommand,
    GitTagCommand,
)
from code_analysis.commands.git_stage_commands import (
    GitAddCommand,
    GitCommitCommand,
    GitRestoreCommand,
)
from code_analysis.commands.git_stash_commands import (
    GitStashApplyCommand,
    GitStashDropCommand,
    GitStashListCommand,
    GitStashPushCommand,
)

__all__ = [
    "GitAddCommand",
    "GitCommitCommand",
    "GitConfigGetCommand",
    "GitConfigListCommand",
    "GitCherryPickCommand",
    "GitCleanCommand",
    "GitIdentityGetCommand",
    "GitIdentitySetCommand",
    "GitMergeCommand",
    "GitRebaseCommand",
    "GitResetCommand",
    "GitRestoreCommand",
    "GitRevertCommand",
    "GitStashApplyCommand",
    "GitStashDropCommand",
    "GitStashListCommand",
    "GitStashPushCommand",
    "GitTagCommand",
]
