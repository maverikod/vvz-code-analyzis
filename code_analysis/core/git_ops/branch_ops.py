"""Local git branch operations: switch the working tree to a branch, create a
branch, and delete a branch. Acts only on the resolved project repository and
never contacts a remote.
"""

from code_analysis.core.git_ops.common import ensure_local_repo, run_git


def git_switch_branch(root_dir: str, branch: str) -> dict:
    """Switch the working tree to an existing branch.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        branch: The opaque name of the branch to switch to.

    Returns:
        On success: {"success": True, "branch": str} naming the now-current
        branch.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_REF_NOT_FOUND", "GIT_COMMAND_FAILED".
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    returncode, _stdout, stderr = run_git(root_dir, ["switch", branch])
    if returncode != 0:
        lowered = stderr.lower()
        if (
            "did not match" in lowered
            or "invalid reference" in lowered
            or "not a commit" in lowered
        ):
            return {
                "success": False,
                "code": "GIT_REF_NOT_FOUND",
                "message": stderr.strip() or f"Branch '{branch}' was not found.",
            }
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git switch failed.",
        }
    return {"success": True, "branch": branch}


def git_create_branch(
    root_dir: str, branch: str, start_point: str | None = None
) -> dict:
    """Create a new branch, optionally starting at an opaque revision.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        branch: The name of the branch to create.
        start_point: An opaque ref/revision to start the branch at, or None
            to start at the current HEAD.

    Returns:
        On success: {"success": True, "branch": str} naming the created
        branch.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_REF_ALREADY_EXISTS", "GIT_REF_NOT_FOUND", "GIT_COMMAND_FAILED".
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    args = ["branch", branch]
    if start_point is not None:
        args.append(start_point)
    returncode, _stdout, stderr = run_git(root_dir, args)
    if returncode != 0:
        lowered = stderr.lower()
        if "already exists" in lowered:
            return {
                "success": False,
                "code": "GIT_REF_ALREADY_EXISTS",
                "message": stderr.strip() or f"Branch '{branch}' already exists.",
            }
        if "not a valid" in lowered or "unknown revision" in lowered:
            return {
                "success": False,
                "code": "GIT_REF_NOT_FOUND",
                "message": stderr.strip()
                or f"Start point '{start_point}' was not found.",
            }
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git branch create failed.",
        }
    return {"success": True, "branch": branch}


def git_delete_branch(root_dir: str, branch: str, force: bool = False) -> dict:
    """Delete a branch.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        branch: The name of the branch to delete.
        force: When False, uses the safe delete (git branch -d), which
            refuses to delete a branch not fully merged. When True, uses
            the forced delete (git branch -D).

    Returns:
        On success: {"success": True, "branch": str} naming the deleted
        branch.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_REF_NOT_FOUND", "GIT_BRANCH_NOT_MERGED", "GIT_COMMAND_FAILED".
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    flag = "-D" if force else "-d"
    returncode, _stdout, stderr = run_git(root_dir, ["branch", flag, branch])
    if returncode != 0:
        lowered = stderr.lower()
        if "not found" in lowered or "not a valid" in lowered:
            return {
                "success": False,
                "code": "GIT_REF_NOT_FOUND",
                "message": stderr.strip() or f"Branch '{branch}' was not found.",
            }
        if "not fully merged" in lowered:
            return {
                "success": False,
                "code": "GIT_BRANCH_NOT_MERGED",
                "message": stderr.strip() or f"Branch '{branch}' is not fully merged.",
            }
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git branch delete failed.",
        }
    return {"success": True, "branch": branch}
