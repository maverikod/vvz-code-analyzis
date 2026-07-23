"""
Helpers for restore_database MCP command: config parsing and file iteration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
from pathlib import Path
from typing import Any, Iterable


def extract_restore_dirs_from_config(cfg: dict[str, Any]) -> list[str]:
    """
    Extract directories list for restore from config.

    Args:
        cfg: Parsed config dict.

    Returns:
        List of directory paths (as strings). May be empty.
    """
    code_analysis_val = cfg.get("code_analysis")
    code_cfg: dict[str, Any] = (
        code_analysis_val if isinstance(code_analysis_val, dict) else {}
    )
    dirs = code_cfg.get("dirs")
    if isinstance(dirs, list) and all(isinstance(x, str) for x in dirs):
        non_empty_dirs = [x for x in dirs if x]
        if non_empty_dirs:
            return non_empty_dirs

    worker_val = code_cfg.get("worker")
    worker_cfg: dict[str, Any] = worker_val if isinstance(worker_val, dict) else {}
    watch_dirs = worker_cfg.get("watch_dirs")
    if isinstance(watch_dirs, list) and all(isinstance(x, str) for x in watch_dirs):
        non_empty_watch_dirs = [x for x in watch_dirs if x]
        if non_empty_watch_dirs:
            return non_empty_watch_dirs

    return []


def extract_restore_dirs_from_watch_dirs_table(database: Any) -> list[str]:
    """
    Fallback restore directories sourced from the ``watch_dirs`` table.

    Used when the config file has no directories configured (both
    ``code_analysis.dirs`` and ``code_analysis.worker.watch_dirs`` empty or
    missing) — restore falls back to every currently registered watch
    directory's absolute path instead of failing with ``NO_DIRS``.

    Args:
        database: Open database/driver connection (duck-typed, see
            ``code_analysis.core.database.watch_dirs_query.list_watch_dir_path_pairs``).

    Returns:
        Deduplicated list of absolute watch-directory paths (insertion order
        preserved). May be empty when no watch dirs are registered.
    """
    from ..core.database.watch_dirs_query import list_watch_dir_path_pairs

    seen: set[str] = set()
    out: list[str] = []
    for _watch_dir_id, absolute_path in list_watch_dir_path_pairs(database):
        if absolute_path and absolute_path not in seen:
            seen.add(absolute_path)
            out.append(absolute_path)
    return out


def iter_python_files(root_path: Path) -> Iterable[Path]:
    """
    Iterate python files under root_path.

    Args:
        root_path: Root directory to scan.

    Yields:
        Paths to .py files.
    """
    from ..core.constants import DATA_DIR_NAME, DEFAULT_IGNORE_PATTERNS, LOGS_DIR_NAME

    ignore_dirs = DEFAULT_IGNORE_PATTERNS | {DATA_DIR_NAME, LOGS_DIR_NAME}
    for walk_root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignore_dirs]
        for fn in files:
            if fn.endswith(".py"):
                yield Path(walk_root) / fn
