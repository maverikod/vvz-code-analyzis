"""
Service state paths resolver (DB, FAISS, locks, queue).

The refactor plan moves all persistent state out of watched source roots and into
an explicit service state directory configured in `config.json`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class StoragePaths:
    """
    Resolved absolute paths for service state.

    Attributes:
        config_dir: Directory containing the loaded config file.
        db_path: SQLite database path.
        faiss_dir: Directory for FAISS index files.
        locks_dir: Directory for lock files (no locks in watched directories).
        queue_dir: Optional directory for persisted queue state.
        backup_dir: Directory for database backups.
        trash_dir: Directory for trashed (deleted) projects (recycle bin).
    """

    config_dir: Path
    db_path: Path
    faiss_dir: Path
    locks_dir: Path
    queue_dir: Optional[Path]
    backup_dir: Path  # Directory for database backups
    trash_dir: Path  # Directory for trashed (deleted) projects (recycle bin)


def _resolve_path(config_dir: Path, value: str) -> Path:
    """
    Resolve a config path value (absolute or relative to config_dir).

    Args:
        config_dir: Config directory.
        value: Path string.

    Returns:
        Resolved absolute Path.
    """

    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (config_dir / p).resolve()
    return p.resolve()


def load_raw_config(config_path: Path) -> dict[str, Any]:
    """
    Load raw JSON config from disk.

    Args:
        config_path: Path to JSON config.

    Returns:
        Parsed dict.
    """

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_storage_paths(
    *,
    config_data: Mapping[str, Any],
    config_path: Path,
) -> StoragePaths:
    """
    Resolve service state paths from config.

    Expected target config shape (plan Step 0):
        code_analysis.storage.db_path
        code_analysis.storage.faiss_dir
        code_analysis.storage.locks_dir
        code_analysis.storage.queue_dir (optional)

    Backward compatibility:
        - code_analysis.db_path
        - code_analysis.faiss_index_path (file path) -> faiss_dir = parent

    Args:
        config_data: Raw config dict.
        config_path: Path to config.json (used to resolve relative paths).

    Returns:
        StoragePaths with absolute resolved Paths.
    """

    config_dir = Path(config_path).resolve().parent
    code_analysis_cfg = config_data.get("code_analysis") or {}
    if not isinstance(code_analysis_cfg, Mapping):
        code_analysis_cfg = {}

    storage_cfg = code_analysis_cfg.get("storage") or {}
    if not isinstance(storage_cfg, Mapping):
        storage_cfg = {}

    db_path_val = storage_cfg.get("db_path") or code_analysis_cfg.get("db_path")
    if not isinstance(db_path_val, str) or not db_path_val.strip():
        db_path_val = "data/code_analysis.db"
    db_path = _resolve_path(config_dir, db_path_val)

    faiss_dir_val = storage_cfg.get("faiss_dir")
    if isinstance(faiss_dir_val, str) and faiss_dir_val.strip():
        faiss_dir = _resolve_path(config_dir, faiss_dir_val)
    else:
        legacy_faiss = code_analysis_cfg.get("faiss_index_path")
        if isinstance(legacy_faiss, str) and legacy_faiss.strip():
            faiss_dir = _resolve_path(config_dir, legacy_faiss).parent
        else:
            faiss_dir = _resolve_path(config_dir, "data/faiss")

    locks_dir_val = storage_cfg.get("locks_dir")
    if isinstance(locks_dir_val, str) and locks_dir_val.strip():
        locks_dir = _resolve_path(config_dir, locks_dir_val)
    else:
        locks_dir = _resolve_path(config_dir, "data/locks")

    queue_dir_val = storage_cfg.get("queue_dir")
    queue_dir: Optional[Path] = None
    if isinstance(queue_dir_val, str) and queue_dir_val.strip():
        queue_dir = _resolve_path(config_dir, queue_dir_val)

    # Resolve backup directory
    backup_dir_val = storage_cfg.get("backup_dir")
    if isinstance(backup_dir_val, str) and backup_dir_val.strip():
        backup_dir = _resolve_path(config_dir, backup_dir_val)
    else:
        # Default: {project_root}/backups
        if db_path.parent.name == "data":
            project_root = db_path.parent.parent
        else:
            project_root = config_dir
        backup_dir = project_root / "backups"

    # Resolve trash directory (project recycle bin)
    trash_dir_val = storage_cfg.get("trash_dir")
    if isinstance(trash_dir_val, str) and trash_dir_val.strip():
        trash_dir = _resolve_path(config_dir, trash_dir_val)
    else:
        trash_dir = _resolve_path(config_dir, "data/trash")

    return StoragePaths(
        config_dir=config_dir,
        db_path=db_path,
        faiss_dir=faiss_dir,
        locks_dir=locks_dir,
        queue_dir=queue_dir,
        backup_dir=backup_dir,
        trash_dir=trash_dir,
    )


def ensure_storage_dirs(paths: StoragePaths) -> None:
    """
    Ensure that storage directories exist.

    Args:
        paths: StoragePaths.
    """

    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    paths.faiss_dir.mkdir(parents=True, exist_ok=True)
    paths.locks_dir.mkdir(parents=True, exist_ok=True)
    paths.backup_dir.mkdir(parents=True, exist_ok=True)
    paths.trash_dir.mkdir(parents=True, exist_ok=True)
    if paths.queue_dir is not None:
        paths.queue_dir.mkdir(parents=True, exist_ok=True)


def get_faiss_index_path(faiss_dir: Path, project_id: str, dataset_id: str) -> Path:
    """
    Get FAISS index file path for a specific dataset.

    Implements dataset-scoped FAISS indexing (Step 2 of refactor plan).
    Each dataset gets its own FAISS index file to avoid cross-root collisions
    and maintain high search relevance.

    Path format: `{faiss_dir}/{project_id}/{dataset_id}.bin`

    Args:
        faiss_dir: Base directory for FAISS index files (from StoragePaths).
        project_id: Project identifier (UUID4 string).
        dataset_id: Dataset identifier (UUID4 string).

    Returns:
        Absolute Path to the FAISS index file for this dataset.

    Example:
        >>> faiss_dir = Path("/var/lib/code_analysis/faiss")
        >>> project_id = "123e4567-e89b-12d3-a456-426614174000"
        >>> dataset_id = "987fcdeb-51a2-43f7-8b9c-123456789abc"
        >>> get_faiss_index_path(faiss_dir, project_id, dataset_id)
        Path('/var/lib/code_analysis/faiss/123e4567-e89b-12d3-a456-426614174000/987fcdeb-51a2-43f7-8b9c-123456789abc.bin')
    """
    index_file = faiss_dir / project_id / f"{dataset_id}.bin"
    # Ensure parent directory exists
    index_file.parent.mkdir(parents=True, exist_ok=True)
    return index_file


# Test change понеділок, 5 січня 2026 12:57:11 +0200
# Second test change понеділок, 5 січня 2026 12:59:26 +0200
# Third change 1767610869
# Final test change 1767611059
# Auto-detection test 1767611193
# Change detection test 1767611302
