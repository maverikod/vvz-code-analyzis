"""
Watch directory accessibility checks for background workers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def describe_watch_dir_access(path: Path) -> Optional[str]:
    """
    Return a short issue description, or ``None`` if the path is usable.

    A usable watch directory must exist, be a directory, and be readable/searchable
    by the worker process (``R_OK`` + ``X_OK``).
    """
    try:
        resolved = path.expanduser().resolve()
    except OSError as exc:
        return f"cannot resolve path ({exc})"

    if not resolved.exists():
        return "directory does not exist"
    if not resolved.is_dir():
        return "path is not a directory"
    if not os.access(resolved, os.R_OK):
        return "directory is not readable (permission denied)"
    if not os.access(resolved, os.X_OK):
        return "directory is not searchable (execute permission denied)"
    return None
