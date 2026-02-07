"""
Worker status file: current operation and current file for monitoring.

Workers write a small JSON file (e.g. next to PID file or log) so get_worker_status
can include current_operation and current_file in the response.

When writing or logging fails (e.g. disk full), this module must not raise: otherwise
the exception can propagate and stop the worker loop. See docs/INDEXING_WORKER_DISK_FULL_ANALYSIS.md.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

STATUS_OPERATION_IDLE = "idle"
STATUS_OPERATION_POLLING = "polling"
STATUS_OPERATION_VECTORIZING = "vectorizing"
STATUS_OPERATION_CHUNKING = "chunking"
STATUS_OPERATION_INDEXING = "indexing"
STATUS_OPERATION_SCANNING = "scanning"
STATUS_OPERATION_PROCESSING = "processing"


def write_worker_status(
    status_file_path: Optional[Path],
    current_operation: str,
    current_file: Optional[str] = None,
    progress_percent: Optional[Union[int, float]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write current operation, file and progress percent to status file for monitoring.

    Args:
        status_file_path: Path to .status.json file (e.g. logs/vectorization_worker.status.json).
        current_operation: Operation name (e.g. "idle", "vectorizing", "indexing").
        current_file: Optional path to file being processed.
        progress_percent: Optional progress 0-100 (current cycle or batch).
        extra: Optional extra keys to store in status JSON.
    """
    if not status_file_path:
        return
    try:
        path = Path(status_file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "current_operation": current_operation,
            "current_file": current_file,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if progress_percent is not None:
            data["progress_percent"] = max(0, min(100, round(float(progress_percent), 1)))
        if extra:
            data.update(extra)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        # Log must not raise (e.g. disk full); report error but do not propagate
        try:
            logger.debug("Failed to write worker status file %s: %s", status_file_path, e)
        except Exception:
            pass


def read_worker_status(status_file_path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """
    Read worker status from file (current_operation, current_file, progress_percent, updated_at).

    Args:
        status_file_path: Path to .status.json file.

    Returns:
        Dict with current_operation, current_file, progress_percent, updated_at or None if missing/invalid.
    """
    if not status_file_path:
        return None
    path = Path(status_file_path)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = {
            "current_operation": data.get("current_operation", "unknown"),
            "current_file": data.get("current_file"),
            "updated_at": data.get("updated_at"),
        }
        if "progress_percent" in data:
            out["progress_percent"] = data["progress_percent"]
        return out
    except Exception as e:
        # Log must not raise (e.g. disk full); report error but do not propagate
        try:
            logger.debug("Failed to read worker status file %s: %s", status_file_path, e)
        except Exception:
            pass
        return None
