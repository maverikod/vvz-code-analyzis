"""
Resolve file path from project_id and relative path for BaseMCPCommand.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Optional

from ..core.database_driver_pkg.domain.projects import get_project
from ..core.exceptions import ValidationError
from ..core.project_root_path import resolve_project_root_absolute_str

# Driver-direct (stage 2): DatabaseClient class removed; ``database`` below is a
# duck-typed driver-shaped object (PostgreSQLDriver in production). Kept as an
# ``Any`` alias so the existing type annotation does not need rewriting.
DatabaseClient = Any


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
    project = get_project(database, project_id)
    if not project:
        raise ValidationError(
            f"Project with ID {project_id} not found in database",
            field="project_id",
            details={"project_id": project_id},
        )

    rows = database.select("projects", where={"id": project_id})
    row = dict(rows[0]) if rows else {}
    root_str = resolve_project_root_absolute_str(
        project_id=project_id,
        root_path_stored=str(row.get("root_path") or project.root_path or ""),
        watch_dir_id=(
            str(row["watch_dir_id"])
            if row.get("watch_dir_id") is not None
            else project.watch_dir_id
        ),
        project_name=str(row.get("name") or project.name or "").strip() or None,
        database=database,
        require_exists=True,
    ).strip()
    if not root_str or not Path(root_str).is_absolute():
        raise ValidationError(
            f"Cannot resolve absolute project root for project_id {project_id}",
            field="project_id",
            details={
                "project_id": project_id,
                "stored_root_path": row.get("root_path"),
                "watch_dir_id": row.get("watch_dir_id"),
                "name": row.get("name"),
            },
        )

    absolute_path = Path(root_str) / relative_file_path
    resolved_path = absolute_path.resolve()

    if require_exists and not resolved_path.exists():
        raise ValidationError(
            f"File does not exist: {resolved_path}",
            field="file_path",
            details={
                "relative_file_path": relative_file_path,
                "absolute_path": str(resolved_path),
                "project_root": root_str,
                "project_name": project.name,
            },
        )

    return resolved_path
