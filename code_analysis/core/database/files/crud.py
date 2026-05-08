"""
File CRUD: get/add/delete/clear by path or id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid

from pathlib import Path

from typing import Any, Dict, List, Optional, cast

from code_analysis.core.project_root_path import (
    resolve_projects_root_path_row_to_absolute_str,
)
from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    WHERE_FILES_ACTIVE_F,
    WHERE_PROJECTS_ACTIVE_P,
    database_has_sqlite_code_content_fts,
    sql_julian_timestamp_now_expr,
)


logger = logging.getLogger(__name__)


def _cross_project_active_file_same_absolute(
    self, abs_path: str, exclude_project_id: str
) -> Optional[Dict[str, Any]]:
    """Find an active file row in another project that denotes the same absolute path."""
    from ...path_normalization import normalize_path_simple
    from ...file_identity import absolute_path_for_indexed_file

    want = normalize_path_simple(abs_path)
    legacy = self._fetchone(
        f"""
        SELECT id, project_id FROM files
        WHERE path = ?
        AND project_id != ?
        AND {WHERE_FILES_ACTIVE}
        LIMIT 1
        """,
        (want, exclude_project_id),
    )
    if legacy:
        return legacy

    rows = self._fetchall(
        f"""
        SELECT f.id, f.project_id, p.root_path, p.watch_dir_id, f.path, f.relative_path
        FROM files f
        INNER JOIN projects p ON p.id = f.project_id
        WHERE f.project_id != ?
        AND {WHERE_FILES_ACTIVE_F}
        AND {WHERE_PROJECTS_ACTIVE_P}
        """,
        (exclude_project_id,),
    )
    for row in rows:
        try:
            resolved_root = resolve_projects_root_path_row_to_absolute_str(
                root_path_stored=str(row.get("root_path") or ""),
                watch_dir_id=(
                    str(row["watch_dir_id"])
                    if row.get("watch_dir_id") is not None
                    else None
                ),
                database=self,
            )
            row_for_abs = {**row, "root_path": resolved_root}
            if absolute_path_for_indexed_file(resolved_root, row_for_abs) == want:
                return {"id": row["id"], "project_id": row["project_id"]}
        except Exception:
            continue
    return None


def get_file_by_path(
    self, path: str, project_id: str, include_deleted: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Get file record by filesystem path and project ID.

    ``path`` is normalized to an absolute path; the row may store a project-relative
    ``path`` / ``relative_path`` or a legacy absolute ``path``.
    """
    from ...path_normalization import normalize_path_simple
    from ...file_identity import (
        FILE_ROW_PATH_MATCH_SQL,
        file_row_path_match_values,
    )

    abs_path = normalize_path_simple(path)

    if path != abs_path:
        logger.debug(
            f"[get_file_by_path] Path normalized: {path!r} -> {abs_path!r} | "
            f"project_id={project_id} | include_deleted={include_deleted}"
        )

    project = self.get_project(project_id)
    if not project:
        return None

    try:
        r1, r2, r3 = file_row_path_match_values(
            project_root=project["root_path"], absolute_path=abs_path
        )
    except ValueError:
        row = self._fetchone(
            "SELECT * FROM files WHERE project_id = ? AND path = ?"
            + ("" if include_deleted else f" AND {WHERE_FILES_ACTIVE}"),
            (project_id, abs_path),
        )
        if not isinstance(row, dict):
            return None
        return cast(Dict[str, Any], row)

    active_sql = "" if include_deleted else f" AND {WHERE_FILES_ACTIVE}"
    row = self._fetchone(
        f"SELECT * FROM files WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}"
        f"{active_sql}",
        (project_id, r1, r2, r3),
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
) -> str:
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
        File ID (UUID string)
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

    abs_path = normalize_project_file_path(path)
    abs_path_obj = Path(abs_path)

    # Project-relative POSIX path; stored in both ``path`` and ``relative_path``
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

    existing_file = _cross_project_active_file_same_absolute(self, abs_path, project_id)

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
            _now = sql_julian_timestamp_now_expr(self)
            self._execute(
                f"""
                UPDATE files 
                SET deleted = 1, updated_at = {_now}
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

    from ...file_identity import FILE_ROW_PATH_MATCH_SQL, file_row_path_match_values

    r1, r2, r3 = file_row_path_match_values(
        project_root=project_root, absolute_path=abs_path
    )
    existing_in_correct_project = self._fetchone(
        f"""
        SELECT id FROM files
        WHERE project_id = ?
        AND {FILE_ROW_PATH_MATCH_SQL}
        """,
        (project_id, r1, r2, r3),
    )

    if existing_in_correct_project:
        # Update existing file (including relative_path and watch_dir_id)
        file_id_raw = (
            existing_in_correct_project.get("id")
            if isinstance(existing_in_correct_project, dict)
            else None
        )
        if file_id_raw is None:
            raise ValueError("Existing file record has no id in add_file update path")
        file_id = str(file_id_raw)
        self._execute(
            """
            UPDATE files 
            SET watch_dir_id = ?, path = ?, relative_path = ?, lines = ?, 
                last_modified = ?, has_docstring = ?, updated_at = julianday('now')
            WHERE id = ?
            """,
            (
                watch_dir_id,
                relative_path_str,
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
        # Insert new file with explicit UUID primary key (no reliance on lastrowid).
        new_id = str(uuid.uuid4())
        self._execute(
            """
                INSERT INTO files
                (id, project_id, watch_dir_id, path, relative_path, lines, last_modified, has_docstring, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))
            """,
            (
                new_id,
                project_id,
                watch_dir_id,
                relative_path_str,
                relative_path_str,
                lines,
                last_modified,
                has_docstring,
            ),
        )
        # Only commit if not in a transaction (transaction will commit all changes)
        if not self._in_transaction():
            self._commit()
        return new_id


def get_file_id(
    self, path: str, project_id: str, include_deleted: bool = False
) -> Optional[str]:
    """Return file id for an absolute (or normalizable) path within ``project_id``."""
    rec = get_file_by_path(self, path, project_id, include_deleted=include_deleted)
    if not rec:
        return None
    return str(rec["id"])


def get_file_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
    """Get file record by ID."""
    row = self._fetchone("SELECT * FROM files WHERE id = ?", (file_id,))
    if not isinstance(row, dict):
        return None
    return cast(Dict[str, Any], row)


def delete_file(self, file_id: str) -> None:
    """Delete file and all related records (cascade)."""
    self._execute("DELETE FROM files WHERE id = ?", (file_id,))
    self._commit()


def _clear_file_vectors(self, file_id: str) -> None:
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


def clear_file_data(self, file_id: str) -> None:
    """
    Clear all data for a file.

    Removes all related data including:
    - code chunks and vector index (via _clear_file_vectors, entity ids fetched first)
    - entity_cross_ref, code_content_fts (SQLite only), methods, classes, functions,
      imports, issues, usages, code_content, ast_trees, cst_trees (via execute_batch).

    Vector cleanup uses _clear_file_vectors so entity ids are read before any deletions.
    """
    self._clear_file_vectors(file_id)

    class_rows = self._fetchall("SELECT id FROM classes WHERE file_id = ?", (file_id,))
    class_ids = [row["id"] for row in class_rows]

    method_ids: List[Any] = []
    if class_ids:
        ph = ",".join("?" * len(class_ids))
        method_rows = self._fetchall(
            f"SELECT id FROM methods WHERE class_id IN ({ph})",
            tuple(class_ids),
        )
        method_ids = [r["id"] for r in method_rows]

    func_rows = self._fetchall("SELECT id FROM functions WHERE file_id = ?", (file_id,))
    function_ids = [r["id"] for r in func_rows]

    content_ids: List[Any] = []
    if database_has_sqlite_code_content_fts(self):
        content_rows = self._fetchall(
            "SELECT rowid FROM code_content WHERE file_id = ?", (file_id,)
        )
        content_ids = [row["rowid"] for row in content_rows]

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

    # FTS5 virtual table only exists on SQLite; skip DELETE on PostgreSQL.
    if content_ids and database_has_sqlite_code_content_fts(self):
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
