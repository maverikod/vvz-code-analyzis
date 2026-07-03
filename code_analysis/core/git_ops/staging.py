"""Local git staging operations: stage (git add) and unstage (git restore
--staged) project-relative paths in the resolved project repository. Never
contacts a remote.
"""

from code_analysis.core.git_ops.common import (
    confine_relative_path,
    ensure_local_repo,
    run_git,
)


def git_add(root_dir: str, paths: list[str]) -> dict:
    """Stage the given project-relative paths.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        paths: Project-relative paths to stage.

    Returns:
        On success: {"success": True, "staged_paths": list[str]} where
        staged_paths are the input paths that were staged.
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

    returncode, _stdout, stderr = run_git(root_dir, ["add", "--"] + confined_paths)
    if returncode != 0:
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git add failed.",
        }
    return {"success": True, "staged_paths": paths}


def git_unstage(root_dir: str, paths: list[str]) -> dict:
    """Unstage the given project-relative paths (git restore --staged).

    Args:
        root_dir: Absolute path to the resolved project repository root.
        paths: Project-relative paths to unstage.

    Returns:
        On success: {"success": True, "unstaged_paths": list[str]} where
        unstaged_paths are the input paths that were unstaged.
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

    returncode, _stdout, stderr = run_git(
        root_dir, ["restore", "--staged", "--"] + confined_paths
    )
    if returncode != 0:
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git restore --staged failed.",
        }
    return {"success": True, "unstaged_paths": paths}
