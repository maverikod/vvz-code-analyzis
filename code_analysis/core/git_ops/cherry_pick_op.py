"""Local git cherry-pick operation: applies a single named commit onto the
current branch. Acts only on the resolved project repository and never
contacts a remote. A conflicting cherry-pick is aborted before returning so
the working tree is never left partially mutated.
"""

from code_analysis.core.git_ops.common import ensure_local_repo, run_git


def git_cherry_pick(root_dir: str, commit_ref: str) -> dict:
    """Apply a single commit onto the current branch.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        commit_ref: The opaque commit identifier to cherry-pick.

    Returns:
        On success: {"success": True, "commit_hash": str, "branch": str}
        where commit_hash is the hash of the newly created commit and
        branch is the current branch name.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_REF_NOT_FOUND", "GIT_CONFLICT", "GIT_COMMAND_FAILED". On
        GIT_CONFLICT, `git cherry-pick --abort` has already been run so the
        working tree is left exactly as it was before the cherry-pick
        attempt.
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    returncode, stdout, stderr = run_git(root_dir, ["cherry-pick", commit_ref])
    if returncode != 0:
        combined_out = stdout + stderr
        if "CONFLICT" in combined_out or "could not apply" in combined_out.lower():
            run_git(root_dir, ["cherry-pick", "--abort"])
            return {
                "success": False,
                "code": "GIT_CONFLICT",
                "message": "Cherry-pick produced a conflict; the cherry-pick was aborted.",
            }
        lowered = combined_out.lower()
        if (
            "bad revision" in lowered
            or "bad object" in lowered
            or "unknown revision" in lowered
        ):
            return {
                "success": False,
                "code": "GIT_REF_NOT_FOUND",
                "message": stderr.strip() or f"Commit '{commit_ref}' was not found.",
            }
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git cherry-pick failed.",
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
