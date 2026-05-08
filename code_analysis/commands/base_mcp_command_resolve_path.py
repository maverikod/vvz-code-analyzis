"""
Resolve file path from project_id and relative path for BaseMCPCommand.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Optional

from ..core.database_client.client import DatabaseClient
from ..core.exceptions import ValidationError


def resolve_under_project_root(
    project_root: Path,
    relative_file_path: str,
    *,
    require_exists: bool = True,
    must_be_file: Optional[bool] = None,
) -> Path:
    """Resolve ``relative_file_path`` under ``project_root`` with traversal checks.

    Used by filesystem-first commands (list companions: read, grep, copy, move).
    Does not open the code index database.

    Args:
        project_root: Registered project root directory.
        relative_file_path: Path relative to project root (POSIX ``/``).
        require_exists: When True, the target path must exist on disk.
        must_be_file: When True, require a regular file; when False, require a directory;
            when None, accept any existing path.

    Returns:
        Resolved absolute path under ``project_root``.

    Raises:
        ValidationError: On empty/absolute/traversal paths, escape, or kind mismatch.
    """
    raw = (relative_file_path or "").strip()
    if not raw:
        raise ValidationError(
            "file_path must be a non-empty relative path",
            field="file_path",
            details={},
        )
    rel = Path(raw)
    if rel.is_absolute():
        raise ValidationError(
            "Absolute file_path is not allowed; use a project-relative path.",
            field="file_path",
            details={"file_path": relative_file_path},
        )
    if any(part == ".." for part in rel.parts):
        raise ValidationError(
            "Path traversal (..) is not allowed in file_path.",
            field="file_path",
            details={"file_path": relative_file_path},
        )
    root = project_root.resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise ValidationError(
            "Resolved path escapes project root.",
            field="file_path",
            details={
                "file_path": relative_file_path,
                "resolved": str(candidate),
                "root": str(root),
            },
        ) from e
    if require_exists and not candidate.exists():
        raise ValidationError(
            f"Path does not exist: {candidate}",
            field="file_path",
            details={
                "relative_file_path": relative_file_path,
                "absolute_path": str(candidate),
            },
        )
    if require_exists and must_be_file is True and not candidate.is_file():
        raise ValidationError(
            f"Not a file: {candidate}",
            field="file_path",
            details={"absolute_path": str(candidate)},
        )
    if require_exists and must_be_file is False and not candidate.is_dir():
        raise ValidationError(
            f"Not a directory: {candidate}",
            field="file_path",
            details={"absolute_path": str(candidate)},
        )
    return candidate


def resolve_file_path_from_project(
    database: DatabaseClient,
    project_id: str,
    relative_file_path: str,
    *,
    require_exists: bool = True,
) -> Path:
    """
    Resolve absolute file path from project_id and relative path.

    Path formation: watch_dir_path / project_name / relative_file_path.

    Args:
        database: DatabaseClient instance.
        project_id: Project identifier (UUID4).
        relative_file_path: File path relative to project root.

    Args:
        require_exists: When True (default), the resolved path must exist and refer to an
            existing filesystem entry (legacy behavior for reads/patches). When False, only
            project/watch-dir resolution is validated — used for create/save-new flows.

    Returns:
        Resolved absolute Path object.

    Raises:
        ValidationError: If project not found, watch_dir not found, or path invalid.
    """
    project = database.get_project(project_id)
    if not project:
        raise ValidationError(
            f"Project with ID {project_id} not found in database",
            field="project_id",
            details={"project_id": project_id},
        )

    if not project.watch_dir_id:
        raise ValidationError(
            f"Project {project_id} is not linked to a watch directory",
            field="project_id",
            details={
                "project_id": project_id,
                "project_name": project.name,
            },
        )

    if not project.name:
        raise ValidationError(
            f"Project {project_id} does not have a name",
            field="project_id",
            details={"project_id": project_id},
        )

    watch_dir_path_result = database.execute(
        "SELECT absolute_path FROM watch_dir_paths WHERE watch_dir_id = ?",
        (project.watch_dir_id,),
    )
    if isinstance(watch_dir_path_result, list):
        watch_dir_paths = watch_dir_path_result
    else:
        watch_dir_paths = watch_dir_path_result.get("data", [])

    if not watch_dir_paths:
        raise ValidationError(
            f"Watch directory path not found for watch_dir_id {project.watch_dir_id}",
            field="project_id",
            details={
                "project_id": project_id,
                "watch_dir_id": project.watch_dir_id,
            },
        )

    watch_dir_path = watch_dir_paths[0].get("absolute_path")
    if not watch_dir_path:
        raise ValidationError(
            f"Watch directory path is NULL for watch_dir_id {project.watch_dir_id}",
            field="project_id",
            details={
                "project_id": project_id,
                "watch_dir_id": project.watch_dir_id,
            },
        )

    absolute_path = Path(watch_dir_path) / project.name / relative_file_path
    resolved_path = absolute_path.resolve()

    if require_exists and not resolved_path.exists():
        raise ValidationError(
            f"File does not exist: {resolved_path}",
            field="file_path",
            details={
                "relative_file_path": relative_file_path,
                "absolute_path": str(resolved_path),
                "watch_dir_path": watch_dir_path,
                "project_name": project.name,
            },
        )

    return resolved_path
