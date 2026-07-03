"""Local git commit-from-staged operation: creates a commit from the currently
staged state with a caller-supplied non-empty message. Authorship comes from
the repository's own git configuration; never pushes to a remote.
"""

from code_analysis.core.git_ops.common import ensure_local_repo, run_git


def git_commit(root_dir: str, message: str) -> dict:
    """Create a commit from the currently staged state.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        message: The commit message. Must be non-empty after surrounding
            whitespace is stripped; author identity is taken from the
            repository's own git configuration (no -c user.name/user.email
            overrides are passed).

    Returns:
        On success: {"success": True, "commit_hash": str, "branch": str}
        where commit_hash is the new commit's full hash and branch is the
        current branch name after the commit.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_COMMIT_MESSAGE_INVALID", "GIT_NOTHING_TO_COMMIT",
        "GIT_COMMAND_FAILED".
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    if not message or not message.strip():
        return {
            "success": False,
            "code": "GIT_COMMIT_MESSAGE_INVALID",
            "message": "Commit message must be non-empty after stripping whitespace.",
        }

    returncode, stdout, stderr = run_git(root_dir, ["commit", "-m", message])
    if returncode != 0:
        combined = (stdout + stderr).lower()
        if "nothing to commit" in combined:
            return {
                "success": False,
                "code": "GIT_NOTHING_TO_COMMIT",
                "message": "Nothing is staged to commit.",
            }
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git commit failed.",
        }

    _rc_hash, hash_stdout, _hash_stderr = run_git(root_dir, ["rev-parse", "HEAD"])
    _rc_branch, branch_stdout, _branch_stderr = run_git(
        root_dir, ["rev-parse", "--abbrev-ref", "HEAD"]
    )
    return {
        "success": True,
        "commit_hash": hash_stdout.strip(),
        "branch": branch_stdout.strip(),
    }
