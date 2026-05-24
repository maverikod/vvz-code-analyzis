"""
Rotate all logs (main process and workers) with optional gzip packing.

Uses a process-wide lock and status so that periodic background rotation
and manual rotate_all_logs command do not run concurrently.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import gzip
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Process-wide lock and status to prevent races between background thread and manual command.
_rotation_lock = threading.Lock()
_rotation_status: str = "idle"  # "idle" | "rotating"

# Labels used for filtering; must match schema enum in MCP command.
LOG_LABEL_MCP_SERVER = "mcp_server"
LOG_LABEL_CODE_ANALYSIS = "code_analysis"
LOG_LABEL_VECTORIZATION = "vectorization"
LOG_LABEL_FILE_WATCHER = "file_watcher"
LOG_LABEL_INDEXING = "indexing_worker"


def get_rotation_status() -> str:
    """Return current rotation status (idle or rotating)."""
    return _rotation_status


def collect_log_paths(
    config_data: Dict[str, Any],
    config_dir: Path,
    log_filter: Optional[List[str]] = None,
) -> List[Tuple[Path, str]]:
    """
    Collect log file paths from config (main and workers), optionally filtered.

    Resolves paths relative to config file directory. Deduplicates.
    If log_filter is None or empty, returns all logs; otherwise only logs whose
    label is in log_filter (case-insensitive) or whose path contains any filter
    string are included.

    Args:
        config_data: Full config dict (e.g. from config.json).
        config_dir: Directory containing config file (for resolving relative paths).
        log_filter: Optional list of labels or path substrings; if None or empty, all logs.

    Returns:
        List of (absolute Path, label) for each log file.
    """
    items: List[Tuple[Path, str]] = []
    seen: set[str] = set()
    filter_lower = [
        s.strip().lower() for s in (log_filter or []) if s and isinstance(s, str)
    ]
    include_all = not filter_lower

    def matches(path: Path, label: str) -> bool:
        if include_all:
            return True
        if any(label.lower() == f for f in filter_lower):
            return True
        path_str = str(path)
        if any(f in path_str for f in filter_lower):
            return True
        return False

    def add(p: Optional[str], label: str) -> None:
        if not p or not isinstance(p, str) or not p.strip():
            return
        path = Path(p.strip()).expanduser()
        if not path.is_absolute():
            path = (config_dir / path).resolve()
        key = str(path)
        if key not in seen and matches(path, label):
            seen.add(key)
            items.append((path, label))

    server = config_data.get("server") or {}
    log_dir_str = server.get("log_dir")
    if log_dir_str:
        log_dir = Path(log_dir_str).expanduser()
        if not log_dir.is_absolute():
            log_dir = (config_dir / log_dir).resolve()
        add(str(log_dir / "mcp_server.log"), LOG_LABEL_MCP_SERVER)
        add(str(log_dir / "code_analysis.log"), LOG_LABEL_CODE_ANALYSIS)

    code_analysis = config_data.get("code_analysis") or {}
    add(code_analysis.get("log"), LOG_LABEL_CODE_ANALYSIS)

    worker = code_analysis.get("worker") or {}
    add(worker.get("log_path"), LOG_LABEL_VECTORIZATION)

    file_watcher = code_analysis.get("file_watcher") or {}
    add(file_watcher.get("log_path"), LOG_LABEL_FILE_WATCHER)

    indexing_worker = code_analysis.get("indexing_worker") or {}
    add(indexing_worker.get("log_path"), LOG_LABEL_INDEXING)

    return items


def _rotation_path(log_path: Path, n: int) -> Path:
    """Path for rotated file: log -> log.1, log.1 -> log.2, etc."""
    return Path(str(log_path) + "." + str(n))


def _rotate_and_pack_one(
    log_path: Path,
    backup_count: int,
    pack_rotated: bool,
) -> Dict[str, Any]:
    """
    Rotate one log file (current -> .1, .1 -> .2, ...) and optionally gzip rotated files.

    Args:
        log_path: Path to log file.
        backup_count: Number of backup files to keep (1..99).
        pack_rotated: If True, gzip rotated files (.1, .2, ...) to .1.gz, .2.gz, ...

    Returns:
        Dict with log_path, rotated_paths, packed_paths, error (if any).
    """
    result: Dict[str, Any] = {
        "log_path": str(log_path),
        "rotated_paths": [],
        "packed_paths": [],
        "error": None,
    }
    if not log_path.exists():
        result["skipped"] = True
        result["message"] = "File does not exist; nothing to rotate"
        return result

    try:
        # Rotate existing backups: .(N-1) -> .N, ... .1 -> .2
        for i in range(backup_count - 1, 0, -1):
            src = _rotation_path(log_path, i)
            if src.exists():
                dst = _rotation_path(log_path, i + 1)
                if dst.exists():
                    dst.unlink()
                src.rename(dst)
                result["rotated_paths"].append(str(dst))

        # Current log -> .1
        dst1 = _rotation_path(log_path, 1)
        if dst1.exists():
            dst1.unlink()
        log_path.rename(dst1)
        result["rotated_paths"].insert(0, str(dst1))

        # Create new empty log file
        log_path.touch()

        # Pack rotated files if requested
        if pack_rotated:
            for i in range(1, backup_count + 1):
                p = _rotation_path(log_path, i)
                if not p.exists():
                    continue
                gz_path = Path(str(p) + ".gz")
                if gz_path.exists():
                    gz_path.unlink()
                with open(p, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        f_out.writelines(f_in)
                p.unlink()
                result["packed_paths"].append(str(gz_path))

        result["message"] = (
            f"Rotated to {dst1}; backups: {len(result['rotated_paths'])}"
            + (f"; packed: {len(result['packed_paths'])}" if pack_rotated else "")
        )
    except OSError as e:
        logger.exception("Log rotation failed for %s: %s", log_path, e)
        result["error"] = str(e)
    return result


def run_rotation_all_logs(
    config_data: Dict[str, Any],
    config_dir: Path,
    backup_count: int = 5,
    pack_rotated: bool = True,
    log_filter: Optional[List[str]] = None,
    timeout_seconds: Optional[float] = 30.0,
) -> Dict[str, Any]:
    """
    Rotate logs (main + workers) and optionally pack with gzip.

    Acquires the process-wide lock so that only one rotation runs at a time
    (background thread or manual command). Sets status to "rotating" for the
    duration.

    Args:
        config_data: Full config dict.
        config_dir: Config file directory for resolving relative paths.
        backup_count: Number of backup files per log (1..99).
        pack_rotated: If True, gzip rotated files.
        log_filter: Optional list of labels or path substrings; if None or empty, rotate all logs.
        timeout_seconds: Max time to wait for lock (None = wait forever).

    Returns:
        Dict with status ("ok" | "error" | "lock_timeout"), rotation_status,
        files (list of per-file results with label), and optional error message.
    """
    global _rotation_status
    acquired = _rotation_lock.acquire(
        timeout=timeout_seconds if timeout_seconds else -1
    )
    if not acquired:
        return {
            "status": "lock_timeout",
            "rotation_status": _rotation_status,
            "message": "Another rotation is in progress or lock timed out",
            "files": [],
        }
    try:
        _rotation_status = "rotating"
        files_result: List[Dict[str, Any]] = []
        log_items = collect_log_paths(config_data, config_dir, log_filter=log_filter)
        for path, label in log_items:
            one = _rotate_and_pack_one(
                path, backup_count=backup_count, pack_rotated=pack_rotated
            )
            one["label"] = label
            files_result.append(one)
        has_error = any(f.get("error") for f in files_result)
        return {
            "status": "error" if has_error else "ok",
            "rotation_status": "idle",
            "files": files_result,
            "message": (
                f"Rotated {len(files_result)} log(s); "
                f"{sum(1 for f in files_result if f.get('error'))} error(s)"
            ),
        }
    finally:
        _rotation_status = "idle"
        _rotation_lock.release()
