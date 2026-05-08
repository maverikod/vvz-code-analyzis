"""
Internal helper: clear all project data from database in one logical write.

Deletion runs as a single execute_logical_write_operation (one RPC, one server
transaction). SQL uses subqueries keyed by project_id only — no client-side ID
discovery inside the transaction.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, TYPE_CHECKING

from ..core.database.logical_write_program import LogicalWriteProgramV1, SqlParamPair
from ..core.sql_portable import database_has_sqlite_code_content_fts

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)

_FILES_OF = "SELECT id FROM files WHERE project_id = ?"
_CLASSES_OF = f"SELECT id FROM classes WHERE file_id IN ({_FILES_OF})"


def build_delete_project_full_clear_batch(
    project_id: str, *, include_code_content_fts: bool = True
) -> List[SqlParamPair]:
    """Build one batch of (sql, params) DELETEs in FK-safe order; params use project_id only.

    ``include_code_content_fts``: set False for PostgreSQL (no FTS5 virtual table).
    """
    pid = project_id
    ops: List[SqlParamPair] = []

    # Duplicates (duplicate_occurrences -> code_duplicates)
    ops.append(
        (
            "DELETE FROM duplicate_occurrences WHERE duplicate_id IN "
            "(SELECT id FROM code_duplicates WHERE project_id = ?)",
            (pid,),
        )
    )
    ops.append(("DELETE FROM code_duplicates WHERE project_id = ?", (pid,)))

    # FTS rows for project content (SQLite / sqlite_proxy only)
    if include_code_content_fts:
        ops.append(
            (
                "DELETE FROM code_content_fts WHERE rowid IN ("
                "SELECT rowid FROM code_content WHERE file_id IN (" + _FILES_OF + "))",
                (pid,),
            )
        )

    # code_chunks (depends on files / classes / functions / methods)
    ops.append(
        (
            "DELETE FROM code_chunks WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )
    ops.append(("DELETE FROM code_chunks WHERE project_id = ?", (pid,)))

    # issues: project-scoped and entity-linked
    ops.append(_pair_issues_delete(pid))

    # entity_cross_ref: caller/callee class, method, function + file_id
    ops.append(_pair_entity_cross_ref_delete(pid))

    # methods before classes
    ops.append(
        (
            "DELETE FROM methods WHERE class_id IN (" + _CLASSES_OF + ")",
            (pid,),
        )
    )

    ops.append(
        (
            "DELETE FROM classes WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )
    ops.append(
        (
            "DELETE FROM functions WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )
    ops.append(
        (
            "DELETE FROM imports WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )
    ops.append(
        (
            "DELETE FROM code_content WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )
    ops.append(
        (
            "DELETE FROM ast_trees WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )
    ops.append(("DELETE FROM ast_trees WHERE project_id = ?", (pid,)))
    ops.append(
        (
            "DELETE FROM cst_trees WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )
    ops.append(("DELETE FROM cst_trees WHERE project_id = ?", (pid,)))
    ops.append(
        (
            "DELETE FROM usages WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )
    ops.append(
        (
            "DELETE FROM comprehensive_analysis_results WHERE file_id IN ("
            + _FILES_OF
            + ")",
            (pid,),
        )
    )
    ops.append(
        (
            "DELETE FROM comprehensive_analysis_results WHERE project_id = ?",
            (pid,),
        )
    )

    # duplicate_occurrences also references files(id)
    ops.append(
        (
            "DELETE FROM duplicate_occurrences WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )

    # file_tree_* (snapshots depend on files)
    ops.append(
        (
            "DELETE FROM file_tree_snapshot_nodes WHERE snapshot_id IN ("
            "SELECT id FROM file_tree_snapshots WHERE file_id IN (" + _FILES_OF + "))",
            (pid,),
        )
    )
    ops.append(
        (
            "DELETE FROM file_tree_snapshot_roots WHERE snapshot_id IN ("
            "SELECT id FROM file_tree_snapshots WHERE file_id IN (" + _FILES_OF + "))",
            (pid,),
        )
    )
    ops.append(
        (
            "DELETE FROM file_tree_snapshots WHERE file_id IN (" + _FILES_OF + ")",
            (pid,),
        )
    )

    ops.append(("DELETE FROM files WHERE project_id = ?", (pid,)))

    ops.append(("DELETE FROM indexing_errors WHERE project_id = ?", (pid,)))
    ops.append(("DELETE FROM vector_index WHERE project_id = ?", (pid,)))
    ops.append(("DELETE FROM projects WHERE id = ?", (pid,)))

    return ops


def _pair_issues_delete(project_id: str) -> SqlParamPair:
    """DELETE issues for project: project_id, files, classes, methods, functions."""
    sql = """
DELETE FROM issues WHERE
  project_id = ?
  OR file_id IN (SELECT id FROM files WHERE project_id = ?)
  OR class_id IN (SELECT id FROM classes WHERE file_id IN (SELECT id FROM files WHERE project_id = ?))
  OR method_id IN (
    SELECT id FROM methods WHERE class_id IN (
      SELECT id FROM classes WHERE file_id IN (SELECT id FROM files WHERE project_id = ?)
    )
  )
  OR function_id IN (SELECT id FROM functions WHERE file_id IN (SELECT id FROM files WHERE project_id = ?))
""".strip()
    # 5 placeholders, all project_id
    return sql, (project_id,) * 5


def _pair_entity_cross_ref_delete(project_id: str) -> SqlParamPair:
    sql = """
DELETE FROM entity_cross_ref WHERE
  file_id IN (SELECT id FROM files WHERE project_id = ?)
  OR caller_class_id IN (SELECT id FROM classes WHERE file_id IN (SELECT id FROM files WHERE project_id = ?))
  OR callee_class_id IN (SELECT id FROM classes WHERE file_id IN (SELECT id FROM files WHERE project_id = ?))
  OR caller_method_id IN (SELECT id FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id IN (SELECT id FROM files WHERE project_id = ?)))
  OR callee_method_id IN (SELECT id FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id IN (SELECT id FROM files WHERE project_id = ?)))
  OR caller_function_id IN (SELECT id FROM functions WHERE file_id IN (SELECT id FROM files WHERE project_id = ?))
  OR callee_function_id IN (SELECT id FROM functions WHERE file_id IN (SELECT id FROM files WHERE project_id = ?))
""".strip()
    # One project_id bind per OR branch (innermost files filter).
    return sql, (project_id,) * 7


def build_mark_deleted_program(project_id: str) -> LogicalWriteProgramV1:
    """Soft-delete project and all files in one logical write."""
    return {
        "batches": [
            [
                (
                    "UPDATE files SET deleted = 1 WHERE project_id = ?",
                    (project_id,),
                ),
                (
                    "UPDATE projects SET deleted = 1 WHERE id = ?",
                    (project_id,),
                ),
            ]
        ]
    }


def build_unmark_deleted_program(project_id: str) -> LogicalWriteProgramV1:
    """Restore deleted flag for project and all files in one logical write."""
    return {
        "batches": [
            [
                (
                    "UPDATE files SET deleted = 0 WHERE project_id = ?",
                    (project_id,),
                ),
                (
                    "UPDATE projects SET deleted = 0 WHERE id = ?",
                    (project_id,),
                ),
            ]
        ]
    }


async def mark_project_deleted_impl(database: DatabaseClient, project_id: str) -> None:
    """Mark all project files as deleted (soft delete) in one logical write."""
    logger.info(f"[MARK_PROJECT_DELETED] Marking project {project_id} as deleted")
    try:
        database.execute_logical_write_operation(build_mark_deleted_program(project_id))
        logger.info(f"[MARK_PROJECT_DELETED] Marked project {project_id} as deleted")
    except Exception as e:
        logger.error(f"[MARK_PROJECT_DELETED] Failed for {project_id}: {e}")
        raise


async def unmark_project_deleted_impl(
    database: DatabaseClient, project_id: str
) -> None:
    """Unmark all project files (restore from trash) in one logical write."""
    logger.info(f"[UNMARK_PROJECT_DELETED] Unmarking project {project_id}")
    try:
        database.execute_logical_write_operation(
            build_unmark_deleted_program(project_id)
        )
        logger.info(f"[UNMARK_PROJECT_DELETED] Unmarked project {project_id}")
    except Exception as e:
        logger.error(f"[UNMARK_PROJECT_DELETED] Failed for {project_id}: {e}")
        raise


async def _clear_project_data_impl(database: DatabaseClient, project_id: str) -> None:
    """Clear all data for project_id in one execute_logical_write_operation call."""
    clear_start = time.time()
    logger.info(f"[CLEAR_PROJECT_DATA] Starting clear for project {project_id}")

    batch = build_delete_project_full_clear_batch(
        project_id,
        include_code_content_fts=database_has_sqlite_code_content_fts(database),
    )
    program: LogicalWriteProgramV1 = {"batches": [batch]}
    try:
        database.execute_logical_write_operation(program)
    except Exception as e:
        logger.error(f"[CLEAR_PROJECT_DATA] Logical write failed for {project_id}: {e}")
        raise

    logger.info(
        f"[CLEAR_PROJECT_DATA] Completed clear for project {project_id} "
        f"({len(batch)} statements) in {time.time() - clear_start:.3f}s"
    )
