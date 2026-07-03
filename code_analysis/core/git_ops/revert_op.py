"""Local git revert operation as a new inverse commit.

Revert creates a new commit whose content is the inverse of a named target
commit. It never rewrites or removes existing history, which makes it safe to
apply on branches whose history must be preserved. The recorded authorship of
the new commit comes from the resolved repository's own git configuration, not
from any override passed by this module. This operation never contacts a remote.
"""

from code_analysis.core.git_ops.common import run_git, ensure_local_repo


def revert_commit(root_dir: str, target_commit: str) -> dict:
    """Revert target_commit by creating a new inverse commit.

    Uses `git revert --no-edit`, never rewriting existing history. On success,
    returns a dict with key "success": True plus the new commit hash, the
    reverted target, and the current branch name. On failure, returns a dict
    with key "success": False plus a "code" and a "message". It never contacts
    a remote. Authorship of the new commit comes from the repository's own git
    configuration because no `-c user.name` or `-c user.email` override is ever
    passed to git.
    """
    repo_failure: dict | None = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    returncode, stdout, stderr = run_git(
        root_dir, ["revert", "--no-edit", target_commit]
    )
    if returncode != 0:
        run_git(root_dir, ["revert", "--abort"])
        message = stderr.strip() or stdout.strip() or "git revert failed"
        return {
            "success": False,
            "code": "GIT_REVERT_CONFLICT",
            "message": message,
        }

    hash_returncode, hash_stdout, hash_stderr = run_git(root_dir, ["rev-parse", "HEAD"])
    if hash_returncode != 0:
        return {
            "success": False,
            "code": "GIT_REVERT_STATE_UNREADABLE",
            "message": hash_stderr.strip() or "git rev-parse HEAD failed",
        }
    new_commit_hash = hash_stdout.strip()

    branch_returncode, branch_stdout, branch_stderr = run_git(
        root_dir, ["rev-parse", "--abbrev-ref", "HEAD"]
    )
    if branch_returncode != 0:
        return {
            "success": False,
            "code": "GIT_REVERT_STATE_UNREADABLE",
            "message": branch_stderr.strip()
            or "git rev-parse --abbrev-ref HEAD failed",
        }
    current_branch = branch_stdout.strip()

    return {
        "success": True,
        "new_commit_hash": new_commit_hash,
        "reverted_target": target_commit,
        "current_branch": current_branch,
    }
