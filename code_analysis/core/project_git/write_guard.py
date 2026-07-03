"""
Virtual-environment and installed-package write guard for the
project-scoped git command block.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mcp_proxy_adapter.commands.result import ErrorResult

from ...commands.project_text_file_guard import (
    reject_if_write_under_project_venv,
)


def reject_git_write_under_project_venv(
    absolute_path: Path,
    project_root: Path,
) -> Optional[ErrorResult]:
    """Apply the git block's virtual-environment write guard.

    This is the project-scoped git block's application point of the
    virtual-environment and installed-package write guard. It is applied to
    every working-tree write the git block performs, including staging,
    restore, commit-on-write, or any other write into the working tree; the
    git block never bypasses it.

    Args:
        absolute_path: Absolute path targeted by the git block write.
        project_root: Root path of the project containing the write target.

    Returns:
        Optional error result from the shared project virtual-environment
        guard when the write is forbidden, otherwise None.
    """
    return reject_if_write_under_project_venv(absolute_path, project_root)
