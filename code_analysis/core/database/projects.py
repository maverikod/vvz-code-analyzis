"""
Module projects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    WHERE_FILES_ACTIVE_F,
    WHERE_FILES_ACTIVE_P,
    WHERE_HAS_DOCSTRING_F,
    WHERE_PROCESSING_ACTIVE_P,
    database_has_sqlite_code_content_fts,
    sql_julian_timestamp_now_expr,
)
from code_analysis.core.project_root_path import (
    enrich_project_dict_resolve_root_path,
    find_project_id_by_resolved_absolute_root,
    persist_projects_root_path_stored_value,
)
from code_analysis.core.vector_search_backend import uses_pgvector_ann_for_database

from .watch_dirs_partition import (
    current_server_instance_id,
    current_server_instance_params,
    sql_projects_server_instance_filter,
)

logger = logging.getLogger(__name__)


def insert_project_row(
    self,
    project_id: str,
    root_path_stored: str,
    name: str,
    *,
    comment: Optional[str] = None,
    watch_dir_id: Optional[str] = None,
    server_instance_id: Optional[str] = None,
) -> None:
    """Insert a ``projects`` row for the current server instance."""
    sid = server_instance_id or current_server_instance_id()
    _now = sql_julian_timestamp_now_expr(self)
    self._execute(
        f"""
        INSERT INTO projects (
            id, server_instance_id, root_path, name, comment, watch_dir_id, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, {_now})
        """,
        (project_id, sid, root_path_stored, name, comment, watch_dir_id),
    )
    self._commit()


def get_or_create_project(
    self,
    root_path: str,
    name: Optional[str] = None,
    comment: Optional[str] = None,
    project_id: Optional[str] = None,
) -> str:
    """
    Get or create project by root path.

    Args:
        root_path: Root directory path of the project
        name: Optional project name
        comment: Optional human-readable comment/identifier
        project_id: Optional project ID to use when creating (e.g. from projectid file).
            If not provided, a new UUID is generated.

    Returns:
        Project ID (UUID4 string)
    """
    existing = find_project_id_by_resolved_absolute_root(self, root_path)
    if existing:
        return existing
    new_id = project_id if project_id else str(uuid.uuid4())
    project_name = name or Path(root_path).name
    stored = persist_projects_root_path_stored_value(
        project_root_absolute=Path(root_path),
        watch_dir_id=None,
        database=self,
    )
    sid = current_server_instance_id()
    _now = sql_julian_timestamp_now_expr(self)
    self._execute(
        f"""
                INSERT INTO projects (
                    id, server_instance_id, root_path, name, comment, updated_at
                )
                VALUES (?, ?, ?, ?, ?, {_now})
            """,
        (new_id, sid, stored, project_name, comment),
    )
    self._commit()
    return new_id


def get_project_id(self, root_path: str) -> Optional[str]:
    """
    Get project ID by root path.

    Args:
        root_path: Resolved absolute root directory path of the project

    Returns:
        Project ID (UUID4 string) or None if not found
    """
    return find_project_id_by_resolved_absolute_root(self, root_path)


def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get project by ID.

    Args:
        project_id: Project ID (UUID4 string)

    Returns:
        Project record as dictionary or None if not found
    """
    where_sql, where_params = sql_projects_server_instance_filter("p")
    row = self._fetchone(
        f"SELECT * FROM projects p WHERE {where_sql} AND p.id = ?",
        where_params + (project_id,),
    )
    if not row:
        return None
    if isinstance(row, dict):
        return enrich_project_dict_resolve_root_path(row, self)
    return enrich_project_dict_resolve_root_path(dict(row), self)


def relocate_project_root_after_disk_move(
    self,
    project_id: str,
    old_root_path: str,
    new_root_path: str,
    new_watch_dir_id: Optional[str] = None,
) -> bool:
    """
    Same ``projectid`` / UUID, new location under a watch directory.

    Updates only the ``projects`` row: resolved ``root_path``, directory ``name``
    (immediate child folder under the watch dir), and optionally ``watch_dir_id``.
    File rows keep project-relative paths; they are not rewritten on relocate.
    """
    try:
        _now = sql_julian_timestamp_now_expr(self)
        old_r = Path(old_root_path).expanduser().resolve()
        new_r = Path(new_root_path).expanduser().resolve()
    except OSError as e:
        logger.warning(
            "relocate_project_root_after_disk_move: cannot resolve old=%s new=%s: %s",
            old_root_path,
            new_root_path,
            e,
        )
        return False

    sid = current_server_instance_id()
    if old_r == new_r:
        if new_watch_dir_id is not None:
            self._execute(
                f"UPDATE projects SET watch_dir_id = ?, updated_at = {_now} "
                "WHERE server_instance_id = ? AND id = ?",
                (new_watch_dir_id, sid, project_id),
            )
            self._commit()
        return True

    cur = self._fetchone(
        "SELECT watch_dir_id FROM projects WHERE server_instance_id = ? AND id = ?",
        (sid, project_id),
    )
    effective_wd = (
        str(new_watch_dir_id)
        if new_watch_dir_id is not None
        else (
            str(cur.get("watch_dir_id"))
            if isinstance(cur, dict) and cur.get("watch_dir_id")
            else ""
        )
    )
    new_stored = persist_projects_root_path_stored_value(
        project_root_absolute=new_r,
        watch_dir_id=effective_wd or None,
        database=self,
    )
    if effective_wd:
        other = self._fetchone(
            "SELECT id FROM projects WHERE server_instance_id = ? "
            "AND watch_dir_id IS NOT NULL AND watch_dir_id = ? "
            "AND root_path = ? AND id != ? LIMIT 1",
            (sid, effective_wd, new_stored, project_id),
        )
    else:
        other = self._fetchone(
            "SELECT id FROM projects WHERE server_instance_id = ? "
            "AND root_path = ? AND id != ? LIMIT 1",
            (sid, new_stored, project_id),
        )
    if other:
        logger.error(
            "relocate_project_root_after_disk_move: root_path %s already used by "
            "project %s; refusing to move project %s from %s",
            new_stored,
            other.get("id"),
            project_id,
            old_r,
        )
        return False

    if not self._fetchone(
        "SELECT id FROM projects WHERE server_instance_id = ? AND id = ?",
        (sid, project_id),
    ):
        logger.warning(
            "relocate_project_root_after_disk_move: project %s not found", project_id
        )
        return False

    new_name = new_r.name
    if new_watch_dir_id is not None:
        self._execute(
            "UPDATE projects SET root_path = ?, name = ?, watch_dir_id = ?, "
            f"updated_at = {_now} WHERE server_instance_id = ? AND id = ?",
            (new_stored, new_name, new_watch_dir_id, sid, project_id),
        )
    else:
        self._execute(
            f"UPDATE projects SET root_path = ?, name = ?, updated_at = {_now} "
            "WHERE server_instance_id = ? AND id = ?",
            (new_stored, new_name, sid, project_id),
        )

    self._commit()
    logger.info(
        "relocate_project_root_after_disk_move: project_id=%s root %s -> %s "
        "(projects row only; file paths unchanged)",
        project_id,
        old_r,
        new_r,
    )
    return True


def get_all_projects(self) -> List[Dict[str, Any]]:
    """Get all active (non-soft-deleted) projects.

    Excludes rows with projects.deleted=1 and projects whose files are all
    soft-deleted. Includes watch_dir_id for path verification on startup.

    Returns:
        List of dicts with id, root_path, name, comment, watch_dir_id, updated_at.
    """
    proj_where, proj_params = sql_projects_server_instance_filter("p")
    rows = self._fetchall(
        "SELECT p.id, p.root_path, p.name, p.comment, p.watch_dir_id, p.updated_at "
        "FROM projects p "
        f"WHERE {proj_where} AND " + WHERE_FILES_ACTIVE_P + " "
        "AND (NOT EXISTS (SELECT 1 FROM files f WHERE f.project_id = p.id) "
        "   OR EXISTS (SELECT 1 FROM files f WHERE f.project_id = p.id "
        "              AND " + WHERE_FILES_ACTIVE_F + ")) "
        "ORDER BY p.name, p.root_path",
        proj_params,
    )
    return rows if rows else []


async def clear_project_data(self, project_id: str) -> None:
    """
    Clear all data for a project and remove the project itself.

    Removes all files, classes, functions, imports, issues, usages,
    code_content, ast_trees, code_chunks, vector_index entries,
    code_duplicates, duplicate_occurrences, and the project record itself.

    Args:
        project_id: Project ID (UUID4 string)
    """
    file_rows = self._fetchall(
        "SELECT id FROM files WHERE project_id = ?", (project_id,)
    )
    file_ids = [row["id"] for row in file_rows]

    # Delete duplicates first (before files)
    try:
        # Delete duplicate occurrences first (foreign key constraint)
        self._execute(
            """
            DELETE FROM duplicate_occurrences
            WHERE duplicate_id IN (
                SELECT id FROM code_duplicates WHERE project_id = ?
            )
            """,
            (project_id,),
        )
        # Delete duplicate groups
        self._execute(
            "DELETE FROM code_duplicates WHERE project_id = ?",
            (project_id,),
        )
    except Exception as e:
        logger.warning(f"Failed to delete duplicates for project {project_id}: {e}")

    # Tables that reference project_id (must be cleared before deleting project)
    try:
        self._execute("DELETE FROM cst_trees WHERE project_id = ?", (project_id,))
    except Exception as e:
        logger.warning(f"Failed to delete cst_trees for project {project_id}: {e}")
    try:
        self._execute("DELETE FROM indexing_errors WHERE project_id = ?", (project_id,))
    except Exception as e:
        logger.warning(
            f"Failed to delete indexing_errors for project {project_id}: {e}"
        )
    try:
        self._execute(
            "DELETE FROM comprehensive_analysis_results WHERE project_id = ?",
            (project_id,),
        )
    except Exception as e:
        logger.warning(
            f"Failed to delete comprehensive_analysis_results for project {project_id}: {e}"
        )

    if not file_ids:
        # Project-scoped issues (e.g. file_id NULL) must go before projects row
        self._execute("DELETE FROM issues WHERE project_id = ?", (project_id,))
        # Delete vector_index even if no files
        self._execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,))
        self._execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._commit()
        logger.info(f"Cleared all data and removed project {project_id} (no files)")
        return

    placeholders = ",".join("?" * len(file_ids))
    class_rows = self._fetchall(
        f"SELECT id FROM classes WHERE file_id IN ({placeholders})", tuple(file_ids)
    )
    class_ids = [row["id"] for row in class_rows]
    content_ids: List[Any] = []
    if database_has_sqlite_code_content_fts(self):
        content_rows = self._fetchall(
            f"SELECT rowid FROM code_content WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
        content_ids = [row["rowid"] for row in content_rows]
    # Delete FTS entries in batches to avoid database corruption
    # If FTS is corrupted, skip it and continue with other deletions
    if content_ids and database_has_sqlite_code_content_fts(self):
        batch_size = 1000
        for i in range(0, len(content_ids), batch_size):
            batch = content_ids[i : i + batch_size]
            batch_placeholders = ",".join("?" * len(batch))
            try:
                self._execute(
                    f"DELETE FROM code_content_fts WHERE rowid IN ({batch_placeholders})",
                    tuple(batch),
                )
            except Exception as e:
                logger.warning(
                    f"Failed to delete FTS batch {i//batch_size + 1} for project {project_id}: {e}. Skipping FTS deletion."
                )
                # If FTS is corrupted, skip remaining batches
                break
    if class_ids:
        method_placeholders = ",".join("?" * len(class_ids))
        self._execute(
            f"DELETE FROM methods WHERE class_id IN ({method_placeholders})",
            tuple(class_ids),
        )
    if file_ids:
        self._execute(
            f"DELETE FROM classes WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM functions WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM imports WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM issues WHERE project_id = ? OR file_id IN ({placeholders})",
            (project_id,) + tuple(file_ids),
        )
    if file_ids:
        self._execute(
            f"DELETE FROM code_content WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    if file_ids:
        self._execute(
            f"DELETE FROM ast_trees WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM code_chunks WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    if file_ids:
        self._execute(
            f"DELETE FROM comprehensive_analysis_results WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )

    self._execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,))
    self._execute("DELETE FROM files WHERE project_id = ?", (project_id,))
    self._execute("DELETE FROM projects WHERE id = ?", (project_id,))
    self._commit()
    logger.info(f"Cleared all data and removed project {project_id}")


def get_projects_with_vectorization_count(self) -> List[Dict[str, Any]]:
    """
    Get projects with count of files/chunks needing vectorization.

    Returns list of projects sorted by pending count (smallest first).
    Count includes:
    - Files needing chunking (have docstrings but no chunks)
    - Chunks needing vectorization (have embeddings but no vector_id)

    **Important**: Deleted files are excluded from counts.
    Projects with zero pending count are excluded from results.

    Returns:
        List of dictionaries with keys: project_id, root_path, pending_count
        Sorted by pending_count ASC (smallest first)
    """
    ann_pending = (
        "cc.embedding_vec IS NULL"
        if uses_pgvector_ann_for_database(self)
        else "cc.vector_id IS NULL"
    )
    rows = self._fetchall(
        f"""
        SELECT 
            p.id AS project_id,
            p.root_path,
            (
                -- Count files needing chunking (project-scoped, all files in project)
                (SELECT COUNT(DISTINCT f.id)
                 FROM files f
                 WHERE f.project_id = p.id
                   AND {WHERE_FILES_ACTIVE_F}
                   AND (
                       {WHERE_HAS_DOCSTRING_F}
                       OR EXISTS (
                           SELECT 1 FROM classes c 
                           WHERE c.file_id = f.id 
                             AND c.docstring IS NOT NULL 
                             AND c.docstring != ''
                       )
                       OR EXISTS (
                           SELECT 1 FROM functions fn 
                           WHERE fn.file_id = f.id 
                             AND fn.docstring IS NOT NULL 
                             AND fn.docstring != ''
                       )
                       OR EXISTS (
                           SELECT 1 FROM methods m 
                           JOIN classes c ON m.class_id = c.id 
                           WHERE c.file_id = f.id 
                             AND m.docstring IS NOT NULL 
                             AND m.docstring != ''
                       )
                   )
                   AND NOT EXISTS (
                       SELECT 1 FROM code_chunks cc 
                       WHERE cc.file_id = f.id
                   ))
                +
                -- Count chunks needing vectorization (project-scoped, all chunks in project)
                (SELECT COUNT(cc.id)
                 FROM code_chunks cc
                 INNER JOIN files f ON cc.file_id = f.id
                 WHERE cc.project_id = p.id
                   AND {WHERE_FILES_ACTIVE_F}
                   AND cc.embedding_vector IS NOT NULL
                   AND {ann_pending})
            ) AS pending_count
        FROM projects p
        WHERE p.server_instance_id = ?
        AND {WHERE_FILES_ACTIVE_P}
        AND {WHERE_PROCESSING_ACTIVE_P}
        AND (
            -- Count files needing chunking
            (SELECT COUNT(DISTINCT f.id)
             FROM files f
             WHERE f.project_id = p.id
               AND {WHERE_FILES_ACTIVE_F}
               AND (
                   {WHERE_HAS_DOCSTRING_F}
                   OR EXISTS (
                       SELECT 1 FROM classes c 
                       WHERE c.file_id = f.id 
                         AND c.docstring IS NOT NULL 
                         AND c.docstring != ''
                   )
                   OR EXISTS (
                       SELECT 1 FROM functions fn 
                       WHERE fn.file_id = f.id 
                         AND fn.docstring IS NOT NULL 
                         AND fn.docstring != ''
                   )
                   OR EXISTS (
                       SELECT 1 FROM methods m 
                       JOIN classes c ON m.class_id = c.id 
                       WHERE c.file_id = f.id 
                         AND m.docstring IS NOT NULL 
                         AND m.docstring != ''
                   )
               )
               AND NOT EXISTS (
                   SELECT 1 FROM code_chunks cc 
                   WHERE cc.file_id = f.id
               ))
            +
            -- Count chunks needing vectorization
            (SELECT COUNT(cc.id)
             FROM code_chunks cc
             INNER JOIN files f ON cc.file_id = f.id
             WHERE cc.project_id = p.id
               AND {WHERE_FILES_ACTIVE_F}
               AND cc.embedding_vector IS NOT NULL
               AND {ann_pending})
        ) > 0
        ORDER BY pending_count ASC
        """,
        current_server_instance_params(),
    )
    return rows if rows else []


def get_project_files(
    self, project_id: str, include_deleted: bool = False
) -> List[Dict[str, Any]]:
    """
    Get all files for a project.

    Args:
        project_id: Project ID (UUID4 string)
        include_deleted: If True, include files marked as deleted (default: False)

    Returns:
        List of file records as dictionaries
    """
    if include_deleted:
        rows = self._fetchall(
            "SELECT id, path, lines, last_modified, has_docstring, deleted FROM files WHERE project_id = ?",
            (project_id,),
        )
    else:
        rows = self._fetchall(
            "SELECT id, path, lines, last_modified, has_docstring, deleted FROM files WHERE project_id = ? AND "
            + WHERE_FILES_ACTIVE,
            (project_id,),
        )
    result = []
    for row in rows:
        result.append(
            {
                "id": row["id"],
                "path": row["path"],
                "lines": row["lines"],
                "last_modified": row["last_modified"],
                "has_docstring": row["has_docstring"],
                "deleted": row.get("deleted", 0),
            }
        )
    return result
