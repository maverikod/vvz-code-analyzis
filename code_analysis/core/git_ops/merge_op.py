"""Local git merge operation: merges a named branch into the current branch.
Acts only on the resolved project repository and never contacts a remote. A
conflicting merge is aborted before returning so the working tree is never
left partially mutated.
"""

from code_analysis.core.git_ops.common import ensure_local_repo, run_git


def git_merge_branch(root_dir: str, branch: str) -> dict:
    """Merge a named branch into the current branch.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        branch: The opaque name of the branch to merge into the current
            branch.

    Returns:
        On success: {"success": True, "commit_hash": str, "branch": str,
        "merged_branch": str} where commit_hash is the current HEAD hash
        after the merge (the merge commit, or the pre-merge HEAD when the
        merge was a fast-forward or already up to date), branch is the
        current branch name, and merged_branch is the input branch name.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_REF_NOT_FOUND", "GIT_CONFLICT", "GIT_COMMAND_FAILED". On
        GIT_CONFLICT, `git merge --abort` has already been run so the
        working tree is left exactly as it was before the merge attempt.
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    returncode, stdout, stderr = run_git(root_dir, ["merge", "--no-edit", branch])
    if returncode != 0:
        combined_out = stdout + stderr
        if "CONFLICT" in combined_out or "Automatic merge failed" in combined_out:
            run_git(root_dir, ["merge", "--abort"])
            return {
                "success": False,
                "code": "GIT_CONFLICT",
                "message": "Merge produced a conflict; the merge was aborted.",
            }
        lowered = combined_out.lower()
        if "not something we can merge" in lowered or "unknown revision" in lowered:
            return {
                "success": False,
                "code": "GIT_REF_NOT_FOUND",
                "message": stderr.strip() or f"Branch '{branch}' was not found.",
            }
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git merge failed.",
        }

    _rc_hash, hash_stdout, _hash_stderr = run_git(root_dir, ["rev-parse", "HEAD"])
    _rc_branch, branch_stdout, _branch_stderr = run_git(
        root_dir, ["rev-parse", "--abbrev-ref", "HEAD"]
    )
    return {
        "success": True,
        "commit_hash": hash_stdout.strip(),
        "branch": branch_stdout.strip(),
        "merged_branch": branch,
    }
