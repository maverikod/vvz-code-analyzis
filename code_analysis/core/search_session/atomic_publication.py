"""
Atomic publication helpers for search session blocks and index files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _staging_path(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".tmp")


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write bytes via a same-directory temporary file and atomic replace."""
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = _staging_path(target)
    with open(staging, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    atomic_publish_rename(staging, target)


def atomic_write_json(target: Path, obj: Any) -> None:
    """Write JSON via a same-directory temporary file and atomic replace."""
    payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_write_bytes(target, payload)


def atomic_publish_rename(staging_path: Path, final_path: Path) -> None:
    """Atomically publish staged content at ``final_path``."""
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging_path, final_path)
__all__ = [
    "atomic_publish_rename",
    "atomic_write_bytes",
    "atomic_write_json",
]
