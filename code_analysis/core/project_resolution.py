"""
Project resolution utilities: root normalization and project_id safety gate.

This module is a foundation for multi-project indexing refactor:
- All project roots are treated as resolved absolute paths.
- Mutating commands are gated by a mandatory `project_id` loaded from `<root>/projectid`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .exceptions import InvalidProjectIdFormatError, ProjectIdError


def normalize_root_dir(root_dir: str | Path) -> Path:
    """
    Normalize a project root directory to a resolved absolute `Path`.

    Args:
        root_dir: Root directory path (string or Path).

    Returns:
        Resolved absolute `Path`.

    Raises:
        FileNotFoundError: If the path does not exist.
        NotADirectoryError: If the path is not a directory.
    """

    root_path = Path(root_dir).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(str(root_path))
    if not root_path.is_dir():
        raise NotADirectoryError(str(root_path))
    return root_path


def normalize_abs_path(path: str | Path) -> str:
    """
    Normalize an arbitrary filesystem path into a resolved absolute string path.

    Args:
        path: Path (string or Path).

    Returns:
        Absolute resolved path as string.
    """

    return str(Path(path).expanduser().resolve())


@dataclass
class ProjectInfo:
    """Information about project from projectid file."""

    project_id: str  # UUID4 identifier
    description: str  # Human-readable description


def load_project_id(root_dir: str | Path) -> str:
    """
    Load `project_id` from `<root_dir>/projectid` file and validate its format.

    Expected JSON format:
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "description": "Human readable description of project"
    }

    The refactor plan enforces `project_id` as a mandatory safety gate for
    mutating operations. This function is the single source of truth for that ID.

    Args:
        root_dir: Project root directory (contains `projectid` file).

    Returns:
        Project id as a string (UUID4).

    Raises:
        ProjectIdError: If file is missing or empty.
        InvalidProjectIdFormatError: If JSON format is invalid or missing required fields.
    """
    project_info = load_project_info(root_dir)
    return project_info.project_id


def load_project_info(root_dir: str | Path) -> ProjectInfo:
    """
    Load full project information from `<root_dir>/projectid` file.

    Expected JSON format:
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "description": "Human readable description of project"
    }

    Args:
        root_dir: Project root directory (contains `projectid` file).

    Returns:
        ProjectInfo with project_id and description.

    Raises:
        ProjectIdError: If file is missing or empty.
        InvalidProjectIdFormatError: If JSON format is invalid or missing required fields.
    """
    root_path = normalize_root_dir(root_dir)
    pid_path = root_path / "projectid"
    if not pid_path.exists():
        raise ProjectIdError(
            message=f"Missing projectid file: {pid_path}",
            projectid_path=str(pid_path),
        )

    raw = pid_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ProjectIdError(
            message=f"Empty projectid file: {pid_path}",
            projectid_path=str(pid_path),
        )

    # Parse as JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InvalidProjectIdFormatError(
            message=f"Invalid projectid format: not valid JSON - {str(e)}",
            projectid_path=str(pid_path),
        ) from e

    if not isinstance(data, dict):
        raise InvalidProjectIdFormatError(
            message=f"Invalid projectid format: expected JSON object, got {type(data).__name__}",
            projectid_path=str(pid_path),
        )

    if "id" not in data:
        raise InvalidProjectIdFormatError(
            message="Invalid projectid format: missing required 'id' field",
            projectid_path=str(pid_path),
        )

    project_id = data["id"]
    description = data.get("description", "")

    # Validate UUID4 format
    try:
        u = uuid.UUID(project_id)
    except Exception as e:
        raise InvalidProjectIdFormatError(
            message=f"Invalid projectid format: 'id' field is not a valid UUID - {project_id}",
            projectid_path=str(pid_path),
        ) from e

    if u.version != 4:
        raise InvalidProjectIdFormatError(
            message=f"Invalid projectid format: 'id' field must be UUID v4, got version {u.version}",
            projectid_path=str(pid_path),
        )

    return ProjectInfo(project_id=project_id, description=description)


def require_matching_project_id(root_dir: str | Path, project_id: str | None) -> str:
    """
    Enforce safety gate: provided `project_id` must match `<root_dir>/projectid`.

    Args:
        root_dir: Project root directory.
        project_id: Project ID provided by the caller.

    Returns:
        Validated project_id (string).

    Raises:
        ProjectIdError: If project_id is missing or does not match.
    """

    expected = load_project_id(root_dir)
    if not project_id:
        raise ProjectIdError(
            "project_id is required for this operation and must match root_dir/projectid"
        )
    if project_id != expected:
        raise ProjectIdError(
            "project_id mismatch: provided value does not match root_dir/projectid",
        )
    return project_id


def find_project_root_for_file(
    file_path: str | Path, watch_dirs: list[str | Path]
) -> Optional[Tuple[Path, str]]:
    """
    Find project root and project_id for a file.

    Uses project discovery to find the nearest project root containing
    the file by walking up the directory tree and looking for projectid files.

    Args:
        file_path: Path to file
        watch_dirs: List of watched directories (absolute paths)

    Returns:
        Tuple of (project_root_path, project_id) or None if not found

    Raises:
        NestedProjectError: If nested projects detected
    """
    from .project_discovery import find_project_root

    watch_dirs_resolved = [Path(wd).resolve() for wd in watch_dirs]
    project_root = find_project_root(Path(file_path), watch_dirs_resolved)
    if project_root is None:
        return None
    return (project_root.root_path, project_root.project_id)
