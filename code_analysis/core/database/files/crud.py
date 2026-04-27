"""
File CRUD: get/add/delete/clear by path or id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

logger = logging.getLogger(__name__)


def get_file_by_path(
    self, path: str, project_id: str, include_deleted: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Get file record by path and project ID.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        path: File path (will be normalized to absolute)
        project_id: Project ID
        include_deleted: If True, include files marked as deleted (default: False)

    Returns:
        File record as dictionary or None if not found
    """
    from ...path_normalization import normalize_path_simple

    # Normalize path to absolute (Step 5: absolute paths everywhere)
    # Ensure consistent normalization - use resolve() to handle symlinks and relative paths
    abs_path = normalize_path_simple(path)

    # Log normalization for debugging path mismatches
    if path != abs_path:
        logger.debug(
            f"[get_file_by_path] Path normalized: {path!r} -> {abs_path!r} | "
            f"project_id={project_id} | include_deleted={include_deleted}"
        )

    if include_deleted:
        row = self._fetchone(
            "SELECT * FROM files WHERE path = ? AND project_id = ?",
            (abs_path, project_id),
        )
    else:
        row = self._fetchone(
            "SELECT * FROM files WHERE path = ? AND project_id = ? AND "
            + WHERE_FILES_ACTIVE,
            (abs_path, project_id),
        )
    if not isinstance(row, dict):
        return None
    return cast(Dict[str, Any], row)


def add_file(
    self,
    path: str,
    lines: int,
    last_modified: float,
    has_docstring: bool,
    project_id: str,
) -> int:
    """
    Add or update file record. Returns file_id.

    Files are stored with relative_path from project root.
    Files are uniquely identified by (project_id, path).

    **Important**: If the same **absolute** path is already indexed as an active file row
    in a different project (unusual; can indicate relocation or misconfiguration), that
    other row is marked deleted and its related data cleared before continuing. Matching
    ``relative_path`` alone across projects is **not** treated as a conflict, because
    ``relative_path`` is only meaningful within a project root (e.g. parallel
    ``.venv/site-packages/...`` trees under different project roots).

    Args:
        path: File path (will be normalized to absolute, then converted to relative)
        lines: Number of lines in file
        last_modified: Last modification timestamp
        has_docstring: Whether file has docstring
        project_id: Project ID (UUID4 string)

    Returns:
        File ID
    """
    from ...path_normalization import normalize_file_path
    from ...file_identity import normalize_project_file_path, relative_path_for_project
    from ...exceptions import ProjectIdMismatchError, ProjectNotFoundError

    # Get project to find project root and watch_dir_id
    project = self.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    project_root = Path(project["root_path"]).resolve()
    watch_dir_id = project.get("watch_dir_id")

    # Normalize input path to absolute (identity for DB ``path`` column)
    abs_path = normalize_project_file_path(path)
    abs_path_obj = Path(abs_path)

    # Project-relative path (POSIX); meaningful only within this project_id
    relative_path_str = relative_path_for_project(abs_path, project_root)

    # Validate project_id matches (if projectid file exists)
    try:
        normalized = normalize_file_path(abs_path_obj, project_root=project_root)
        if normalized.project_id != project_id:
            raise ProjectIdMismatchError(
                message=(
                    f"Project ID mismatch: file {abs_path} belongs to project "
                    f"{normalized.project_id} (from projectid file) but was provided "
                    f"with project_id {project_id}"
                ),
                file_project_id=normalized.project_id,
                db_project_id=project_id,
            )
    except (ProjectNotFoundError, FileNotFoundError):
        # File doesn't exist or project not found - continue anyway
        pass
    except ProjectIdMismatchError:
        # Re-raise project ID mismatch - this is a critical error
        raise

    # Cross-project check: only the same absolute path can indicate a shared/relocated
    # file row. Do not compare relative_path across project_id (not globally unique).
    existing_file = self._fetchone(
        f"""
        SELECT id, project_id FROM files 
        WHERE path = ? 
        AND project_id != ? 
        AND {WHERE_FILES_ACTIVE}
        LIMIT 1
        """,
        (abs_path, project_id),
    )

    if existing_file:
        wrong_file_id = existing_file["id"]
        wrong_project_id = existing_file["project_id"]

        logger.error(
            "Same absolute path already indexed in another project: path=%r is active "
            "under project_id=%s while add_file targets project_id=%s. "
            "Treating as relocation/conflict: marking the other project's file deleted "
            "and clearing its related data.",
            abs_path,
            wrong_project_id,
            project_id,
        )

        # Clear all related data for the file in wrong project
        try:
            self.clear_file_data(wrong_file_id)
            logger.info(
                f"Cleared all related data for file_id={wrong_file_id} in project {wrong_project_id}"
            )

            # Mark file as deleted in wrong project
            self._execute(
                """
                UPDATE files 
                SET deleted = 1, updated_at = julianday('now')
                WHERE id = ?
                """,
                (wrong_file_id,),
            )
            logger.info(
                f"Marked file_id={wrong_file_id} as deleted in project {wrong_project_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to clear data and mark file as deleted: {e}", exc_info=True
            )
            # Continue anyway - we'll still add the file to the correct project

    # Check if file already exists in the correct project (by relative_path or path)
    existing_in_correct_project = self._fetchone(
        """
        SELECT id FROM files 
        WHERE project_id = ?
        AND (relative_path = ? OR path = ?)
        """,
        (project_id, relative_path_str, abs_path),
    )

    if existing_in_correct_project:
        # Update existing file (including relative_path and watch_dir_id)
        file_id_raw = (
            existing_in_correct_project.get("id")
            if isinstance(existing_in_correct_project, dict)
            else None
        )
        if not isinstance(file_id_raw, int):
            raise ValueError(
                "Existing file record has invalid id type in add_file update path"
            )
        file_id = file_id_raw
        self._execute(
            """
            UPDATE files 
            SET watch_dir_id = ?, path = ?, relative_path = ?, lines = ?, 
                last_modified = ?, has_docstring = ?, updated_at = julianday('now')
            WHERE id = ?
            """,
            (
                watch_dir_id,
                abs_path,
                relative_path_str,
                lines,
                last_modified,
                has_docstring,
                file_id,
            ),
        )
        # Only commit if not in a transaction (transaction will commit all changes)
        if not self._in_transaction():
            self._commit()
        return file_id
    else:
        # Insert new file with relative_path and watch_dir_id
        self._execute(
            """
                INSERT INTO files
                (project_id, watch_dir_id, path, relative_path, lines, last_modified, has_docstring, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, julianday('now'))
            """,
            (
                project_id,
                watch_dir_id,
                abs_path,
                relative_path_str,
                lines,
                last_modified,
                has_docstring,
            ),
        )
        # Only commit if not in a transaction (transaction will commit all changes)
        if not self._in_transaction():
            self._commit()
        result = self._lastrowid()
        if not isinstance(result, int):
            raise ValueError("Database returned invalid lastrowid type")
        return result


def get_file_id(
    self, path: str, project_id: str, include_deleted: bool = False
) -> Optional[int]:
    """
    Get file ID by path and project.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        path: File path (will be normalized to absolute)
        project_id: Project ID
        include_deleted: If True, include files marked as deleted (default: False)

    Returns:
        File ID or None if not found
    """
    from ...path_normalization import normalize_path_simple

    # Normalize path to absolute (Step 5: absolute paths everywhere)
    abs_path = normalize_path_simple(path)

    if include_deleted:
        row = self._fetchone(
            "SELECT id FROM files WHERE path = ? AND project_id = ?",
            (abs_path, project_id),
        )
    else:
        row = self._fetchone(
            "SELECT id FROM files WHERE path = ? AND project_id = ? AND "
            + WHERE_FILES_ACTIVE,
            (abs_path, project_id),
        )
    return row["id"] if row else None


def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
    """Get file record by ID."""
    row = self._fetchone("SELECT * FROM files WHERE id = ?", (file_id,))
    if not isinstance(row, dict):
        return None
    return cast(Dict[str, Any], row)


def delete_file(self, file_id: int) -> None:
    """Delete file and all related records (cascade)."""
    self._execute("DELETE FROM files WHERE id = ?", (file_id,))
    self._commit()


def _clear_file_vectors(self, file_id: int) -> None:
    """Clear code_chunks and vector_index entries for a file only.

    Entity ids (classes, functions, methods) are read before any deletions
    so that vector_index rows for class/function/method can be removed.
    Does not commit; caller is responsible for commit.
    """
    class_ids = [
        row["id"]
        for row in self._fetchall(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
    ]
    function_ids = [
        row["id"]
        for row in self._fetchall(
            "SELECT id FROM functions WHERE file_id = ?", (file_id,)
        )
    ]
    method_ids = [
        row["id"]
        for row in self._fetchall(
            "SELECT m.id FROM methods m JOIN classes c ON m.class_id = c.id "
            "WHERE c.file_id = ?",
            (file_id,),
        )
    ]
    entity_ids = class_ids + function_ids + method_ids
    self._execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
    self._execute(
        "DELETE FROM vector_index WHERE entity_type = 'file' AND entity_id = ?",
        (file_id,),
    )
    if entity_ids:
        placeholders = ",".join("?" * len(entity_ids))
        self._execute(
            "DELETE FROM vector_index WHERE entity_type IN "
            "('class', 'function', 'method') AND entity_id IN (" + placeholders + ")",
            tuple(entity_ids),
        )


def clear_file_data(self, file_id: int) -> None:
    """
    Clear all data for a file.

    Removes all related data including:
    - code chunks and vector index (via _clear_file_vectors, entity ids fetched first)
    - entity_cross_ref, code_content_fts, methods, classes, functions, imports,
      issues, usages, code_content, ast_trees, cst_trees (via one execute_batch).

    Vector cleanup uses _clear_file_vectors so entity ids are read before any deletions.
    """
    self._clear_file_vectors(file_id)

    class_rows = self._fetchall("SELECT id FROM classes WHERE file_id = ?", (file_id,))
    class_ids = [row["id"] for row in class_rows]

    method_ids: List[int] = []
    if class_ids:
        ph = ",".join("?" * len(class_ids))
        method_rows = self._fetchall(
            f"SELECT id FROM methods WHERE class_id IN ({ph})",
            tuple(class_ids),
        )
        method_ids = [r["id"] for r in method_rows]

    func_rows = self._fetchall("SELECT id FROM functions WHERE file_id = ?", (file_id,))
    function_ids = [r["id"] for r in func_rows]

    content_rows = self._fetchall(
        "SELECT id FROM code_content WHERE file_id = ?", (file_id,)
    )
    content_ids = [row["id"] for row in content_rows]

    # Build entity_cross_ref DELETE (same WHERE logic as delete_entity_cross_ref_for_file)
    conditions = ["file_id = ?"]
    params: List[Any] = [file_id]
    if class_ids:
        ph = ",".join("?" * len(class_ids))
        conditions.append(f"caller_class_id IN ({ph})")
        params.extend(class_ids)
        conditions.append(f"callee_class_id IN ({ph})")
        params.extend(class_ids)
    if method_ids:
        ph = ",".join("?" * len(method_ids))
        conditions.append(f"caller_method_id IN ({ph})")
        params.extend(method_ids)
        conditions.append(f"callee_method_id IN ({ph})")
        params.extend(method_ids)
    if function_ids:
        ph = ",".join("?" * len(function_ids))
        conditions.append(f"caller_function_id IN ({ph})")
        params.extend(function_ids)
        conditions.append(f"callee_function_id IN ({ph})")
        params.extend(function_ids)
    where_clause = " OR ".join(conditions)
    ops: List[tuple] = [
        (f"DELETE FROM entity_cross_ref WHERE {where_clause}", tuple(params))
    ]

    if content_ids:
        ph = ",".join("?" * len(content_ids))
        ops.append(
            (f"DELETE FROM code_content_fts WHERE rowid IN ({ph})", tuple(content_ids))
        )
    if class_ids:
        ph = ",".join("?" * len(class_ids))
        ops.append((f"DELETE FROM methods WHERE class_id IN ({ph})", tuple(class_ids)))
    ops.extend(
        [
            ("DELETE FROM classes WHERE file_id = ?", (file_id,)),
            ("DELETE FROM functions WHERE file_id = ?", (file_id,)),
            ("DELETE FROM imports WHERE file_id = ?", (file_id,)),
            ("DELETE FROM issues WHERE file_id = ?", (file_id,)),
            ("DELETE FROM usages WHERE file_id = ?", (file_id,)),
            ("DELETE FROM code_content WHERE file_id = ?", (file_id,)),
            ("DELETE FROM ast_trees WHERE file_id = ?", (file_id,)),
            ("DELETE FROM cst_trees WHERE file_id = ?", (file_id,)),
        ]
    )
    self.execute_batch(ops)
    self._commit()
