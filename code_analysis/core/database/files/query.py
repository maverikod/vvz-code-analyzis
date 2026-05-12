"""
File query: get_file_summary, get_files_needing_chunking, mark_file_needs_chunking.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional, cast

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE_F, WHERE_HAS_DOCSTRING_F

logger = logging.getLogger(__name__)


def get_file_summary(self, file_path: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get summary for a file.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized via get_file_id which normalizes to absolute.
    """
    file_id = self.get_file_id(file_path, project_id)
    if not file_id:
        return None
    file_info_raw = self._fetchone("SELECT * FROM files WHERE id = ?", (file_id,))
    if not isinstance(file_info_raw, dict):
        return None
    file_info = dict(file_info_raw)
    class_count_row = self._fetchone(
        "SELECT COUNT(*) as count FROM classes WHERE file_id = ?", (file_id,)
    )
    file_info["class_count"] = class_count_row["count"] if class_count_row else 0
    function_count_row = self._fetchone(
        "SELECT COUNT(*) as count FROM functions WHERE file_id = ?", (file_id,)
    )
    file_info["function_count"] = (
        function_count_row["count"] if function_count_row else 0
    )
    issue_count_row = self._fetchone(
        "SELECT COUNT(*) as count FROM issues WHERE file_id = ?", (file_id,)
    )
    file_info["issue_count"] = issue_count_row["count"] if issue_count_row else 0
    return file_info


def get_files_needing_chunking(
    self, project_id: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get files that need chunking (have docstrings but no chunks, or marked needs_chunking).

    Files are considered needing chunking if:
    - They have docstrings (has_docstring = 1) OR
    - They have classes/functions/methods with docstrings
    - AND (they have no chunks in code_chunks table OR needs_chunking = 1)
    - AND they are NOT marked as deleted (deleted = 0 or NULL)

    **Important**: Deleted files are ALWAYS excluded from this query.

    Args:
        project_id: Project ID
        limit: Maximum number of files to return

    Returns:
        List of file records that need chunking
    """
    return cast(
        List[Dict[str, Any]],
        self._fetchall(
            f"""
                SELECT DISTINCT
                    f.id,
                    f.project_id,
                    f.path,
                    f.relative_path,
                    f.has_docstring,
                    p.root_path AS project_root_path,
                    p.name AS project_name,
                    (SELECT wdp.absolute_path FROM watch_dir_paths wdp
                     WHERE wdp.watch_dir_id = COALESCE(f.watch_dir_id, p.watch_dir_id)
                     LIMIT 1) AS watch_absolute_path
                FROM files f
                JOIN projects p ON p.id = f.project_id
                WHERE f.project_id = ?
                AND {WHERE_FILES_ACTIVE_F}
                AND (
                    {WHERE_HAS_DOCSTRING_F}
                    OR EXISTS (
                        SELECT 1 FROM classes c
                        WHERE c.file_id = f.id AND c.docstring IS NOT NULL AND c.docstring != ''
                    )
                    OR EXISTS (
                        SELECT 1 FROM functions fn
                        WHERE fn.file_id = f.id AND fn.docstring IS NOT NULL AND fn.docstring != ''
                    )
                    OR EXISTS (
                        SELECT 1 FROM methods m
                        JOIN classes c ON m.class_id = c.id
                        WHERE c.file_id = f.id AND m.docstring IS NOT NULL AND m.docstring != ''
                    )
                )
                AND (f.needs_chunking = 1 OR NOT EXISTS (
                    SELECT 1 FROM code_chunks cc
                    WHERE cc.file_id = f.id
                ))
                ORDER BY f.updated_at DESC
                LIMIT ?
                """,
            (project_id, limit),
        ),
    )


def mark_file_needs_chunking(self, file_path: str, project_id: str) -> bool:
    """
    Mark a file as needing (re-)chunking by deleting its existing chunks.

    The vectorization worker discovers files to chunk via `get_files_needing_chunking()`,
    which selects files that have docstrings but have **no** rows in `code_chunks`.
    To request re-chunking after a file change, we delete existing chunks so the file
    becomes eligible for that query.

    **Important**: Files with deleted=1 are NOT marked for chunking.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        file_path: File path (will be normalized to absolute)
        project_id: Project ID

    Returns:
        True if file was found and processed, False otherwise.
    """
    from ...path_normalization import normalize_path_simple
    from .crud import get_file_by_path

    abs_path = normalize_path_simple(file_path)

    row = get_file_by_path(self, abs_path, project_id, include_deleted=True)
    if not row:
        return False

    file_id, is_deleted = row["id"], row["deleted"]

    # Do not mark deleted files for chunking
    if is_deleted:
        logger.debug(f"File {file_path} is marked as deleted, skipping chunking")
        return False

    # Delete chunks so worker will re-chunk and re-vectorize in background.
    self._execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
    self._execute(
        "UPDATE files SET updated_at = julianday('now') WHERE id = ?",
        (file_id,),
    )
    self._commit()
    return True
