"""Local git tag creation operation: creates a lightweight or annotated tag
in the resolved project repository. Acts only on the resolved project
repository and never contacts a remote.
"""

from code_analysis.core.git_ops.common import ensure_local_repo, run_git


def git_create_tag(
    root_dir: str, tag_name: str, target: str | None = None, message: str | None = None
) -> dict:
    """Create a tag, optionally annotated and optionally at a specific target.

    Args:
        root_dir: Absolute path to the resolved project repository root.
        tag_name: The name of the tag to create.
        target: An opaque ref/revision the tag points at, or None to tag
            the current HEAD.
        message: When provided, creates an annotated tag with this message.
            When None, creates a lightweight tag.

    Returns:
        On success: {"success": True, "tag_name": str, "commit_hash": str}
        where commit_hash is the hash the tag resolves to.
        On failure: {"success": False, "code": str, "message": str} with
        code one of "GIT_NOT_AVAILABLE", "GIT_NOT_A_REPO",
        "GIT_REF_ALREADY_EXISTS", "GIT_REF_NOT_FOUND", "GIT_COMMAND_FAILED".
    """
    repo_failure = ensure_local_repo(root_dir)
    if repo_failure is not None:
        return repo_failure

    args = ["tag"]
    if message is not None:
        args.extend(["-a", tag_name, "-m", message])
    else:
        args.append(tag_name)
    if target is not None:
        args.append(target)

    returncode, _stdout, stderr = run_git(root_dir, args)
    if returncode != 0:
        lowered = stderr.lower()
        if "already exists" in lowered:
            return {
                "success": False,
                "code": "GIT_REF_ALREADY_EXISTS",
                "message": stderr.strip() or f"Tag '{tag_name}' already exists.",
            }
        if "not a valid" in lowered or "unknown revision" in lowered:
            return {
                "success": False,
                "code": "GIT_REF_NOT_FOUND",
                "message": stderr.strip() or f"Target '{target}' was not found.",
            }
        return {
            "success": False,
            "code": "GIT_COMMAND_FAILED",
            "message": stderr.strip() or "git tag failed.",
        }

    _rc, hash_stdout, _stderr = run_git(root_dir, ["rev-list", "-n", "1", tag_name])
    return {
        "success": True,
        "tag_name": tag_name,
        "commit_hash": hash_stdout.strip(),
    }
