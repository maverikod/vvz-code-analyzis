"""
Service state paths resolver (DB, FAISS, locks, queue).

The refactor plan moves all persistent state out of watched source roots and into
an explicit service state directory configured in `config.json`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

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
        trash_dir: Directory for trashed items (recycle bin). Holds both:
            (1) project folders: trash_dir/ProjectName_timestamp;
            (2) file-level trash per project: trash_dir/{project_id}/...
    """

    config_dir: Path
    log_dir: Path
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


def resolve_service_log_dir(
    *,
    config_data: Mapping[str, Any],
    config_path: Path,
) -> Path:
    """
    Resolve ``server.log_dir`` (absolute or relative to the config file directory).

    Worker logs, database query journals, and the database driver subprocess log
    must use this path — not ``<config_dir>/logs``, which is not writable under
    ``/etc/casmgr`` in production.
    """
    config_dir = Path(config_path).resolve().parent
    server = config_data.get("server") or {}
    if not isinstance(server, Mapping):
        server = {}
    log_dir_str = server.get("log_dir", "./logs")
    if not isinstance(log_dir_str, str) or not log_dir_str.strip():
        log_dir_str = "./logs"
    return _resolve_path(config_dir, log_dir_str)


def load_raw_config(config_path: Path) -> dict[str, Any]:
    """
    Load and validate JSON config from disk.

    Updates global config runtime state on every read.

    Args:
        config_path: Path to JSON config.

    Returns:
        Parsed dict (even when semantically invalid; see ``is_config_valid()``).

    Raises:
        ConfigJSONDecodeError: On JSON syntax errors.
    """
    from code_analysis.core.config_state import revalidate_config_at_path

    data, _valid = revalidate_config_at_path(Path(config_path))
    return data


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

    Note:
        trash_dir holds both project-level trash (ProjectName_timestamp)
        and file-level trash per project (trash_dir/{project_id}/...).
        Use get_file_trash_dir(paths.trash_dir, project_id) for file trash.
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

    log_dir = resolve_service_log_dir(config_data=config_data, config_path=config_path)

    return StoragePaths(
        config_dir=config_dir,
        log_dir=log_dir,
        db_path=db_path,
        faiss_dir=faiss_dir,
        locks_dir=locks_dir,
        queue_dir=queue_dir,
        backup_dir=backup_dir,
        trash_dir=trash_dir,
    )


def resolve_search_sessions_root(
    *,
    config_data: Mapping[str, Any],
    config_path: Path,
) -> Path:
    """
    Resolve on-disk root for paginated search session directories.

    Defaults to ``{db_path.parent}/search_sessions`` so production state under
    ``/var/casmgr/data`` stays writable when ``config.json`` lives in ``/etc/casmgr``.
    """
    storage = resolve_storage_paths(config_data=config_data, config_path=config_path)
    search_cfg = config_data.get("search_session") or {}
    if isinstance(search_cfg, Mapping):
        raw = search_cfg.get("sessions_dir")
        if isinstance(raw, str) and raw.strip():
            return _resolve_path(storage.config_dir, raw)
    return (storage.db_path.parent / "search_sessions").resolve()


def ensure_storage_dirs(paths: StoragePaths) -> None:
    """
    Ensure that storage directories exist.

    Args:
        paths: StoragePaths.
    """

    paths.log_dir.mkdir(parents=True, exist_ok=True)
    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    paths.faiss_dir.mkdir(parents=True, exist_ok=True)
    paths.locks_dir.mkdir(parents=True, exist_ok=True)
    paths.backup_dir.mkdir(parents=True, exist_ok=True)
    paths.trash_dir.mkdir(parents=True, exist_ok=True)
    if paths.queue_dir is not None:
        paths.queue_dir.mkdir(parents=True, exist_ok=True)


def get_faiss_index_path(faiss_dir: Path, project_id: str) -> Path:
    """
    Get FAISS index file path for a project.

    One index per project: path format is `{faiss_dir}/{project_id}.bin`.

    Args:
        faiss_dir: Base directory for FAISS index files (from StoragePaths).
        project_id: Project identifier (UUID4 string).

    Returns:
        Absolute Path to the FAISS index file for this project.
    """
    return faiss_dir / f"{project_id}.bin"


def get_file_trash_dir(trash_dir: Path, project_id: str) -> Path:
    """
    Get file-level trash directory for a project.

    Trashed files of a project live under trash_dir/{project_id}/...
    (FILE_TRASH_SPEC step 1).

    Args:
        trash_dir: Base trash directory (from StoragePaths.trash_dir).
        project_id: Project identifier (UUID4 string).

    Returns:
        Path to trash subfolder for this project's deleted files.
    """
    return trash_dir / project_id


_FORBIDDEN_BATCH_OUTPUT_PREFIXES = (
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/sys",
    "/proc",
    "/root",
    "/boot",
    "/lib",
    "/lib64",
    "/dev",
)


def _is_forbidden_batch_output_path(path: Path) -> bool:
    path_str = str(path.resolve())
    if path_str == "/":
        return True
    for prefix in _FORBIDDEN_BATCH_OUTPUT_PREFIXES:
        if path_str == prefix or path_str.startswith(prefix + "/"):
            return True
    return False


def resolve_batch_output_dir(*, config_path: Path, dir_str: str) -> Path:
    """
    Resolve batch output directory (absolute or relative to config file directory).

    Relative values must not be resolved against process cwd (daemon WorkingDirectory
    may be /usr/lib/casmgr-server).
    """
    from code_analysis.core.constants import DEFAULT_BATCH_OUTPUT_DIR

    value = (
        dir_str.strip()
        if isinstance(dir_str, str) and dir_str.strip()
        else DEFAULT_BATCH_OUTPUT_DIR
    )
    return _resolve_path(Path(config_path).resolve().parent, value)


def apply_resolved_batch_output_dir(
    server_config_dict: dict[str, Any],
    config_path: Path,
) -> dict[str, Any]:
    """Return a copy with ``batch_output_dir`` resolved for ``ServerConfig`` validation."""
    from code_analysis.core.constants import DEFAULT_BATCH_OUTPUT_DIR

    out = dict(server_config_dict)
    raw = out.get("batch_output_dir", DEFAULT_BATCH_OUTPUT_DIR)
    if not isinstance(raw, str):
        raw = DEFAULT_BATCH_OUTPUT_DIR
    resolved = resolve_batch_output_dir(config_path=config_path, dir_str=raw)
    if _is_forbidden_batch_output_path(resolved):
        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )
        resolved = storage.db_path.parent / "batch_output"
    out["batch_output_dir"] = str(resolved.resolve())
    return out
