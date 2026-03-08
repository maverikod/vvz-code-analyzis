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
    code_cfg = (
        cfg.get("code_analysis") if isinstance(cfg.get("code_analysis"), dict) else {}
    )
    dirs = code_cfg.get("dirs")
    if isinstance(dirs, list) and all(isinstance(x, str) for x in dirs):
        non_empty_dirs = [x for x in dirs if x]
        if non_empty_dirs:
            return non_empty_dirs

    worker_cfg = (
        code_cfg.get("worker") if isinstance(code_cfg.get("worker"), dict) else {}
    )
    watch_dirs = worker_cfg.get("watch_dirs")
    if isinstance(watch_dirs, list) and all(isinstance(x, str) for x in watch_dirs):
        non_empty_watch_dirs = [x for x in watch_dirs if x]
        if non_empty_watch_dirs:
            return non_empty_watch_dirs

    return []


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
