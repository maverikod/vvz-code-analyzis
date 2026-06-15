"""
Detect indexed files missing on disk (register-only; no watcher purge).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from code_analysis.core.file_identity import absolute_path_for_indexed_file
from code_analysis.core.path_normalization import normalize_path_simple
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

logger = logging.getLogger(__name__)


def find_missing_indexed_files(
    database: Any,
    project_id: str,
    project_root: Path,
) -> List[Dict[str, Any]]:
    """
    Return active DB file rows whose resolved absolute path is not a regular file.

    Uses the same resolution rules as the file watcher (project-relative keys).
    """
    project_root = project_root.resolve()
    result = database.execute(
        f"""
        SELECT id, path, relative_path
        FROM files
        WHERE project_id = ? AND {WHERE_FILES_ACTIVE}
        """,
        (project_id,),
    )
    rows = result.get("data") or []
    missing: List[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            file_id = row.get("id")
            path = row.get("path")
            rel = row.get("relative_path")
        else:
            file_id, path = row.id, row.path
            rel = getattr(row, "relative_path", None)
        row_map = {"path": path, "relative_path": rel}
        try:
            abs_key = normalize_path_simple(
                absolute_path_for_indexed_file(project_root, row_map)
            )
        except (OSError, ValueError) as exc:
            logger.debug("skip missing-file check for row id=%s: %s", file_id, exc)
            continue
        try:
            still_file = Path(abs_key).is_file()
        except OSError:
            still_file = False
        if not still_file:
            missing.append(
                {
                    "file_id": file_id,
                    "path": path,
                    "relative_path": rel,
                    "resolved_path": abs_key,
                }
            )
    return missing
