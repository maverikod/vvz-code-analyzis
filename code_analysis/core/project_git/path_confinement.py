"""
Path confinement guard for the project-scoped git command block.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult


def confine_project_git_path(
    project_root: Path,
    relative_path: str,
) -> Tuple[Optional[Path], Optional[ErrorResult]]:
    """Confine a git operation path parameter to the project root.

    This function confines a project-relative path parameter of a git operation
    to the resolved project root. Revision identifiers, including branch names,
    tag names, commit hashes, and ref expressions, must never be passed to this
    function because they are exempt from path confinement.

    Args:
        project_root: Resolved or resolvable project root used as the boundary.
        relative_path: Project-relative git operation path parameter to confine.

    Returns:
        Tuple of the confined absolute path and no error on success, or no path
        and an ErrorResult with code GIT_PATH_OUTSIDE_PROJECT on rejection.
    """
    raw = (relative_path or "").strip()
    if not raw:
        return (
            None,
            ErrorResult(
                message="Path parameter is empty; cannot be confined to the project root.",
                code="GIT_PATH_OUTSIDE_PROJECT",
                details={"relative_path": relative_path},
            ),
        )

    rel = Path(raw)
    if rel.is_absolute():
        return (
            None,
            ErrorResult(
                message=(
                    "Absolute path is not allowed for a git operation path parameter; "
                    "use a project-relative path."
                ),
                code="GIT_PATH_OUTSIDE_PROJECT",
                details={"relative_path": relative_path},
            ),
        )

    if any(part == ".." for part in rel.parts):
        return (
            None,
            ErrorResult(
                message="Path traversal ('..') is not allowed in a git operation path parameter.",
                code="GIT_PATH_OUTSIDE_PROJECT",
                details={"relative_path": relative_path},
            ),
        )

    root = project_root.resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return (
            None,
            ErrorResult(
                message="Resolved path escapes the project root.",
                code="GIT_PATH_OUTSIDE_PROJECT",
                details={
                    "relative_path": relative_path,
                    "resolved_path": str(candidate),
                    "project_root": str(root),
                },
            ),
        )

    return (candidate, None)
