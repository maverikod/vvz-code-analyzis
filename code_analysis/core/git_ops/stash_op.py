"""Local git stash operations: save (push) the current uncommitted changes
onto the stash and pop the most recent stash entry back onto the working
tree. Acts only on the resolved project repository and never contacts a
remote.
"""

from code_analysis.core.git_ops.common import ensure_local_repo, run_git


def git_stash_save(root_dir: str, message: str | None = None) -> dict:
    """Save the current uncommitted changes onto the stash.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        message: Optional stash message. When None, git's default stash
            message is used.

    Returns:
        On success: {"success": True, "stashed": bool} where stashed is
        False when there were no local changes to save (not an error) and
        True when a stash entry was created.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_COMMAND_FAILED".
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    args = ["stash", "push"]
    if message is not None:
        args.extend(["-m", message])
    returncode, stdout, stderr = run_git(root_dir, args)
    if returncode != 0:
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git stash push failed.",
        }
    stashed = "no local changes to save" not in stdout.lower()
    return {"success": True, "stashed": stashed}


def git_stash_pop(root_dir: str) -> dict:
    """Apply and drop the most recent stash entry onto the working tree.

    Args:
        root_dir: Absolute path to the resolved project repository root.

    Returns:
        On success: {"success": True} indicating the stash entry was applied
        and dropped.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_NO_STASH_ENTRY", "GIT_CONFLICT", "GIT_COMMAND_FAILED".
        On GIT_CONFLICT, the working tree is left with conflict markers for
        manual resolution, matching git's own stash-pop conflict behaviour;
        there is no stash-pop abort command.
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    returncode, stdout, stderr = run_git(root_dir, ["stash", "pop"])
    if returncode != 0:
        combined = (stdout + stderr).lower()
        if "no stash entries found" in combined:
            return {
                "success": False,
                "code": "GIT_NO_STASH_ENTRY",
                "message": "No stash entries found.",
            }
        if "conflict" in combined:
            return {
                "success": False,
                "code": "GIT_CONFLICT",
                "message": stderr.strip() or "Stash pop produced a conflict.",
            }
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git stash pop failed.",
        }
    return {"success": True}
