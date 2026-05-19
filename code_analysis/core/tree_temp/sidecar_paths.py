"""Resolve `.trees/` mirrored storage paths for tree-temp Sidecars (C-002).

Bind one source file identity under the project to exactly one Sidecar file path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

TREES_DIRECTORY_NAME = ".trees"


class SidecarPathError(ValueError):
    """Raised when a project-relative source path cannot map to a Sidecar path."""


def resolve_trees_sidecar_path(
    project_root: Path, source_relative_to_project: Path
) -> Path:
    """Return absolute Path to the Sidecar file for `source_relative_to_project`
    under `project_root/.trees/` using mirrored relative naming with `.tree` suffix.
    """
    if source_relative_to_project.is_absolute():
        raise SidecarPathError("source path must be relative to project root")
    pure = PurePosixPath(*source_relative_to_project.parts)
    if pure == PurePosixPath(".") or str(pure) == "":
        raise SidecarPathError("source path must not be empty")
    for segment in pure.parts:
        if segment == "..":
            raise SidecarPathError(
                "source path must not contain parent directory segments"
            )
        if segment in {".", ""}:
            raise SidecarPathError("source path must not contain '.' or empty segments")
    rel_posix = pure.as_posix()
    sidecar_rel_name = f"{rel_posix}.tree"
    return (project_root / TREES_DIRECTORY_NAME / sidecar_rel_name).resolve()
