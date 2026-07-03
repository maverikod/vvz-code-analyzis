"""Local git working-tree restore operation: discards uncommitted working-tree
changes on the given project-relative paths, restoring them to the last
committed (or staged) content. Acts only on the resolved project repository
and never contacts a remote.
"""

from code_analysis.core.git_ops.common import (
    confine_relative_path,
    ensure_local_repo,
    run_git,
)


def git_restore_paths(root_dir: str, paths: list[str]) -> dict:
    """Restore the working-tree content of the given project-relative paths.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        paths: Project-relative paths to restore.

    Returns:
        On success: {"success": True, "restored_paths": list[str]} where
        restored_paths are the input paths that were restored.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_PATH_OUTSIDE_PROJECT", "GIT_COMMAND_FAILED".
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    confined_paths = []
    for rel_path in paths:
        absolute_path, path_failure = confine_relative_path(root_dir, rel_path)
        if path_failure is not None:
            return path_failure
        assert absolute_path is not None
        confined_paths.append(absolute_path)

    returncode, _stdout, stderr = run_git(root_dir, ["restore", "--"] + confined_paths)
    if returncode != 0:
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git restore failed.",
        }
    return {"success": True, "restored_paths": paths}
