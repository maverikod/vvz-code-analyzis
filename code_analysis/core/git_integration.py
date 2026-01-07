"""
Git integration for automatic commits.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def is_git_repository(root_dir: Path) -> bool:
    """
    Check if directory is a git repository.

    Args:
        root_dir: Root directory to check

    Returns:
        True if directory is a git repository, False otherwise
    """
    git_dir = root_dir / ".git"
    return git_dir.exists() and git_dir.is_dir()


def is_git_available() -> bool:
    """
    Check if git command is available in system.

    Returns:
        True if git is available, False otherwise
    """
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def create_git_commit(
    root_dir: Path,
    file_path: Path,
    commit_message: str,
) -> Tuple[bool, Optional[str]]:
    """
    Create git commit for file changes.

    Args:
        root_dir: Git repository root directory
        file_path: Path to file that was changed (relative to root_dir)
        commit_message: Commit message

    Returns:
        Tuple of (success, error_message)
    """
    if not is_git_available():
        return (False, "Git is not available in system")

    if not is_git_repository(root_dir):
        return (False, "Directory is not a git repository")

    try:
        # Get relative path from root_dir
        try:
            relative_path = str(file_path.relative_to(root_dir))
        except ValueError:
            # If not relative, use absolute path
            relative_path = str(file_path)

        # Stage file
        result = subprocess.run(
            ["git", "add", relative_path],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (False, f"Failed to stage file: {result.stderr}")

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=root_dir,
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            # No changes to commit
            logger.info(f"No changes to commit for {relative_path}")
            return (True, None)

        # Create commit
        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (False, f"Failed to create commit: {result.stderr}")

        logger.info(f"Git commit created: {commit_message}")
        return (True, None)
    except subprocess.TimeoutExpired:
        return (False, "Git command timed out")
    except Exception as e:
        logger.error(f"Error creating git commit: {e}")
        return (False, str(e))

