"""
Project resolution utilities: root normalization and project_id safety gate.

This module is a foundation for multi-project indexing refactor:
- All project roots are treated as resolved absolute paths.
- Mutating commands are gated by a mandatory `project_id` loaded from `<root>/projectid`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path


class ProjectIdError(ValueError):
    """Raised when project_id cannot be loaded or validated."""


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


def load_project_id(root_dir: str | Path) -> str:
    """
    Load `project_id` from `<root_dir>/projectid` file and validate its format.

    The refactor plan enforces `project_id` as a mandatory safety gate for
    mutating operations. This function is the single source of truth for that ID.

    Args:
        root_dir: Project root directory (contains `projectid` file).

    Returns:
        Project id as a string (UUID4).

    Raises:
        ProjectIdError: If file is missing, empty, or not a valid UUID4.
    """

    root_path = normalize_root_dir(root_dir)
    pid_path = root_path / "projectid"
    if not pid_path.exists():
        raise ProjectIdError(f"Missing projectid file: {pid_path}")

    raw = pid_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ProjectIdError(f"Empty projectid file: {pid_path}")

    try:
        u = uuid.UUID(raw)
    except Exception as e:
        raise ProjectIdError(f"Invalid projectid format (expected UUID): {raw}") from e

    if u.version != 4:
        raise ProjectIdError(f"Invalid projectid UUID version (expected v4): {raw}")

    return raw


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
