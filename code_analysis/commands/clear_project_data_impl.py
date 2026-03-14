"""
Internal helper: clear all project data from database in a single transaction.

All DELETE commands are sent in one execute_batch() to reduce RPC round-trips
and database write bottleneck.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from typing import Any, List, Optional, Tuple, Union, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


def _build_mark_deleted_batch(project_id: str) -> List[Tuple[str, Tuple[Any, ...]]]:
    """Build list of (sql, params) to mark all project files as deleted in one batch.

    Deletion mark is stored only in the files table; other logic checks via this table.
    """
    return [
        ("UPDATE files SET deleted = 1 WHERE project_id = ?", (project_id,)),
    ]


def _build_unmark_deleted_batch(project_id: str) -> List[Tuple[str, Tuple[Any, ...]]]:
    """Build list of (sql, params) to unmark all project files in one batch."""
    return [
        ("UPDATE files SET deleted = 0 WHERE project_id = ?", (project_id,)),
    ]


async def mark_project_deleted_impl(database: DatabaseClient, project_id: str) -> None:
    """Mark project and all its files as deleted (soft delete) in one batch.

    Used when moving project to trash: mark first, then move folder.
    """
    logger.info(f"[MARK_PROJECT_DELETED] Marking project {project_id} as deleted")
    transaction_id = None
    try:
        transaction_id = database.begin_transaction()
        ops = _build_mark_deleted_batch(project_id)
        database.execute_batch(
            cast(
                List[Tuple[str, Optional[Union[tuple, list]]]],
                ops,
            ),
            transaction_id=transaction_id,
        )
        database.commit_transaction(transaction_id)
        logger.info(f"[MARK_PROJECT_DELETED] Marked project {project_id} as deleted")
    except Exception as e:
        if transaction_id:
            try:
                database.rollback_transaction(transaction_id)
            except Exception:
                pass
        logger.error(f"[MARK_PROJECT_DELETED] Failed for {project_id}: {e}")
        raise


async def unmark_project_deleted_impl(
    database: DatabaseClient, project_id: str
) -> None:
    """Unmark all project files (restore from trash): one batch.

    Used after moving folder back from trash. Deletion mark is only in files table.
    """
    logger.info(f"[UNMARK_PROJECT_DELETED] Unmarking project {project_id}")
    transaction_id = None
    try:
        transaction_id = database.begin_transaction()
        ops = _build_unmark_deleted_batch(project_id)
        database.execute_batch(
            cast(
                List[Tuple[str, Optional[Union[tuple, list]]]],
                ops,
            ),
            transaction_id=transaction_id,
        )
        database.commit_transaction(transaction_id)
        logger.info(f"[UNMARK_PROJECT_DELETED] Unmarked project {project_id}")
    except Exception as e:
        if transaction_id:
            try:
                database.rollback_transaction(transaction_id)
            except Exception:
                pass
        logger.error(f"[UNMARK_PROJECT_DELETED] Failed for {project_id}: {e}")
        raise


def _build_delete_batch_no_files(project_id: str) -> List[Tuple[str, Tuple[Any, ...]]]:
    """Build list of (sql, params) for project with no files.

    Order must respect FK: duplicate_occurrences -> code_duplicates -> projects.
    """
    return [
        ("DELETE FROM cst_trees WHERE project_id = ?", (project_id,)),
        ("DELETE FROM indexing_errors WHERE project_id = ?", (project_id,)),
        (
            "DELETE FROM comprehensive_analysis_results WHERE project_id = ?",
            (project_id,),
        ),
        ("DELETE FROM vector_index WHERE project_id = ?", (project_id,)),
        (
            "DELETE FROM duplicate_occurrences WHERE duplicate_id IN "
            "(SELECT id FROM code_duplicates WHERE project_id = ?)",
            (project_id,),
        ),
        ("DELETE FROM code_duplicates WHERE project_id = ?", (project_id,)),
        ("DELETE FROM projects WHERE id = ?", (project_id,)),
    ]


def _append_entity_cross_ref_deletes(
    ops: List[Tuple[str, Tuple[Any, ...]]],
    file_ids: List[int],
    class_ids: List[int],
    method_ids: List[int],
    function_ids: List[int],
    placeholders: str,
) -> None:
    """Append DELETE(s) for entity_cross_ref by file_id and caller/callee entity ids.

    Schema: entity_cross_ref has FK to classes(id), methods(id), functions(id).
    Rows can reference our entities with file_id from another file or NULL;
    so we must delete by file_id IN (...) OR caller_class_id IN (...) OR ...
    """
    conditions = [f"file_id IN ({placeholders})"]
    params: List[Any] = list(file_ids)
    if class_ids:
        ph = ",".join("?" * len(class_ids))
        conditions.append(f"caller_class_id IN ({ph})")
        conditions.append(f"callee_class_id IN ({ph})")
        params.extend(class_ids)
        params.extend(class_ids)
    if method_ids:
        ph = ",".join("?" * len(method_ids))
        conditions.append(f"caller_method_id IN ({ph})")
        conditions.append(f"callee_method_id IN ({ph})")
        params.extend(method_ids)
        params.extend(method_ids)
    if function_ids:
        ph = ",".join("?" * len(function_ids))
        conditions.append(f"caller_function_id IN ({ph})")
        conditions.append(f"callee_function_id IN ({ph})")
        params.extend(function_ids)
        params.extend(function_ids)
    ops.append(
        (
            "DELETE FROM entity_cross_ref WHERE " + " OR ".join(conditions),
            tuple(params),
        )
    )


def _append_issues_deletes(
    ops: List[Tuple[str, Tuple[Any, ...]]],
    file_ids: List[int],
    class_ids: List[int],
    method_ids: List[int],
    function_ids: List[int],
    placeholders: str,
) -> None:
    """Append DELETE for issues by file_id and by class_id, function_id, method_id.

    Schema: issues has FK to files(id), classes(id), functions(id), methods(id).
    Remove all issue rows that reference our files or our entities first.
    """
    conditions = [f"file_id IN ({placeholders})"]
    params: List[Any] = list(file_ids)
    if class_ids:
        ph = ",".join("?" * len(class_ids))
        conditions.append(f"class_id IN ({ph})")
        params.extend(class_ids)
    if method_ids:
        ph = ",".join("?" * len(method_ids))
        conditions.append(f"method_id IN ({ph})")
        params.extend(method_ids)
    if function_ids:
        ph = ",".join("?" * len(function_ids))
        conditions.append(f"function_id IN ({ph})")
        params.extend(function_ids)
    ops.append(
        (
            "DELETE FROM issues WHERE " + " OR ".join(conditions),
            tuple(params),
        )
    )


def _build_delete_batch_with_files(
    project_id: str,
    file_ids: List[int],
    class_ids: List[int],
    method_ids: List[int],
    function_ids: List[int],
    content_ids: List[int],
    placeholders: str,
) -> List[Tuple[str, Tuple[Any, ...]]]:
    """Build list of (sql, params) for all deletes in FK order (one RPC batch).

    Order: dependents first, then parents. Key dependencies (from schema):
    - duplicate_occurrences -> code_duplicates, files
    - code_chunks -> files, classes, functions, methods
    - issues, entity_cross_ref -> files, classes, functions, methods
    - methods -> classes -> files
    - file_tree_snapshot_nodes/roots -> file_tree_snapshots -> files
    - files -> projects

    entity_cross_ref has FK to classes, methods, functions (caller_*/callee_*);
    must delete by all of class_ids, method_ids, function_ids and file_id.
    """
    ops: List[Tuple[str, Tuple[Any, ...]]] = []

    # Duplicates first (duplicate_occurrences -> code_duplicates)
    ops.append(
        (
            "DELETE FROM duplicate_occurrences WHERE duplicate_id IN "
            "(SELECT id FROM code_duplicates WHERE project_id = ?)",
            (project_id,),
        )
    )
    ops.append(("DELETE FROM code_duplicates WHERE project_id = ?", (project_id,)))

    # FTS in batches of 1000
    batch_size = 1000
    for i in range(0, len(content_ids), batch_size):
        batch = content_ids[i : i + batch_size]
        batch_ph = ",".join("?" * len(batch))
        ops.append(
            (
                f"DELETE FROM code_content_fts WHERE rowid IN ({batch_ph})",
                tuple(batch),
            )
        )

    # code_chunks first (references class_id, function_id, method_id)
    ops.append(
        (
            f"DELETE FROM code_chunks WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    # issues have FK to file_id, class_id, function_id, method_id; delete by all before entities
    _append_issues_deletes(
        ops, file_ids, class_ids, method_ids, function_ids, placeholders
    )
    # entity_cross_ref has FK to classes, methods, functions (caller_*/callee_*);
    # delete by file_id and by all entity ids so no row references our classes/methods/functions
    _append_entity_cross_ref_deletes(
        ops, file_ids, class_ids, method_ids, function_ids, placeholders
    )
    # Child tables (methods before classes)
    if class_ids:
        method_ph = ",".join("?" * len(class_ids))
        ops.append(
            (
                f"DELETE FROM methods WHERE class_id IN ({method_ph})",
                tuple(class_ids),
            )
        )

    # File-related tables (no FK to classes/methods/functions)
    ops.append(
        (f"DELETE FROM classes WHERE file_id IN ({placeholders})", tuple(file_ids))
    )
    ops.append(
        (f"DELETE FROM functions WHERE file_id IN ({placeholders})", tuple(file_ids))
    )
    ops.append(
        (f"DELETE FROM imports WHERE file_id IN ({placeholders})", tuple(file_ids))
    )
    ops.append(
        (
            f"DELETE FROM code_content WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    ops.append(
        (
            f"DELETE FROM ast_trees WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    ops.append(
        (
            f"DELETE FROM cst_trees WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    ops.append(
        (f"DELETE FROM usages WHERE file_id IN ({placeholders})", tuple(file_ids))
    )
    ops.append(
        (
            f"DELETE FROM comprehensive_analysis_results WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    # duplicate_occurrences has FK to files(id); delete by file_id before deleting files
    ops.append(
        (
            f"DELETE FROM duplicate_occurrences WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    # file_tree_* (optional schema): nodes/roots -> snapshots -> files; delete before files
    ops.append(
        (
            f"DELETE FROM file_tree_snapshot_nodes WHERE snapshot_id IN "
            f"(SELECT id FROM file_tree_snapshots WHERE file_id IN ({placeholders}))",
            tuple(file_ids),
        )
    )
    ops.append(
        (
            f"DELETE FROM file_tree_snapshot_roots WHERE snapshot_id IN "
            f"(SELECT id FROM file_tree_snapshots WHERE file_id IN ({placeholders}))",
            tuple(file_ids),
        )
    )
    ops.append(
        (
            f"DELETE FROM file_tree_snapshots WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    ops.append(
        (
            "DELETE FROM files WHERE id IN ({})".format(placeholders),
            tuple(file_ids),
        )
    )

    # Project-level (tables that reference project_id only)
    ops.append(("DELETE FROM indexing_errors WHERE project_id = ?", (project_id,)))
    ops.append(("DELETE FROM vector_index WHERE project_id = ?", (project_id,)))
    ops.append(("DELETE FROM projects WHERE id = ?", (project_id,)))

    return ops


async def _clear_project_data_impl(database: DatabaseClient, project_id: str) -> None:
    """Clear all data for a project using DatabaseClient atomically.

    All DELETE operations are sent in one execute_batch() to minimize
    RPC round-trips and database write load.
    """
    clear_start = time.time()
    logger.info(f"[CLEAR_PROJECT_DATA] Starting clear for project {project_id}")

    transaction_id = None
    try:
        tx_start = time.time()
        transaction_id = database.begin_transaction()
        logger.info(
            f"[CLEAR_PROJECT_DATA] Started transaction {transaction_id} in {time.time() - tx_start:.3f}s"
        )

        step_start = time.time()
        files = database.select(
            "files", where={"project_id": project_id}, columns=["id"]
        )
        file_ids = [f["id"] for f in files]
        logger.info(
            f"[CLEAR_PROJECT_DATA] Got {len(file_ids)} file IDs in {time.time() - step_start:.3f}s"
        )

        if not file_ids:
            delete_ops = _build_delete_batch_no_files(project_id)
            batch_start = time.time()
            database.execute_batch(
                cast(
                    List[Tuple[str, Optional[Union[tuple, list]]]],
                    delete_ops,
                ),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] execute_batch ({len(delete_ops)} ops) in {time.time() - batch_start:.3f}s"
            )
            commit_start = time.time()
            database.commit_transaction(transaction_id)
            logger.info(
                f"[CLEAR_PROJECT_DATA] Committed in {time.time() - commit_start:.3f}s"
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Completed clear for project {project_id} (no files) in {time.time() - clear_start:.3f}s"
            )
            return

        placeholders = ",".join("?" * len(file_ids))
        file_ids_tuple = tuple(file_ids)

        step_start = time.time()
        select_ops: List[Tuple[str, Optional[Union[tuple, list]]]] = [
            (
                f"SELECT id FROM classes WHERE file_id IN ({placeholders})",
                file_ids_tuple,
            ),
            (
                f"SELECT id FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id IN ({placeholders}))",
                file_ids_tuple,
            ),
            (
                f"SELECT id FROM functions WHERE file_id IN ({placeholders})",
                file_ids_tuple,
            ),
            (
                f"SELECT id FROM code_content WHERE file_id IN ({placeholders})",
                file_ids_tuple,
            ),
        ]
        select_results = database.execute_batch(
            select_ops, transaction_id=transaction_id
        )

        def _ids_at(idx: int) -> List[int]:
            if idx < len(select_results):
                data = select_results[idx].get("data", [])
                return [r["id"] for r in data]
            return []

        class_ids = _ids_at(0)
        method_ids = _ids_at(1)
        function_ids = _ids_at(2)
        content_ids = _ids_at(3)
        logger.info(
            f"[CLEAR_PROJECT_DATA] Got class/method/function/content IDs in {time.time() - step_start:.3f}s"
        )

        # Optional schema: duplicates (one execute_batch of two DELETEs)
        try:
            database.execute_batch(
                [
                    (
                        """
                DELETE FROM duplicate_occurrences
                WHERE duplicate_id IN (
                    SELECT id FROM code_duplicates WHERE project_id = ?
                )
                """,
                        (project_id,),
                    ),
                    (
                        "DELETE FROM code_duplicates WHERE project_id = ?",
                        (project_id,),
                    ),
                ],
                transaction_id=transaction_id,
            )
        except Exception as e:
            logger.warning(f"Failed to delete duplicates for project {project_id}: {e}")

        # Optional schema: file_tree_* (FK: nodes/roots -> snapshots -> files)
        try:
            database.execute_batch(
                [
                    (
                        f"DELETE FROM file_tree_snapshot_nodes WHERE snapshot_id IN "
                        f"(SELECT id FROM file_tree_snapshots WHERE file_id IN ({placeholders}))",
                        tuple(file_ids),
                    ),
                    (
                        f"DELETE FROM file_tree_snapshot_roots WHERE snapshot_id IN "
                        f"(SELECT id FROM file_tree_snapshots WHERE file_id IN ({placeholders}))",
                        tuple(file_ids),
                    ),
                    (
                        f"DELETE FROM file_tree_snapshots WHERE file_id IN ({placeholders})",
                        tuple(file_ids),
                    ),
                ],
                transaction_id=transaction_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to delete file_tree_* for project %s: %s", project_id, e
            )

        delete_ops = _build_delete_batch_with_files(
            project_id,
            file_ids,
            class_ids,
            method_ids,
            function_ids,
            content_ids,
            placeholders,
        )
        batch_start = time.time()
        database.execute_batch(
            cast(
                List[Tuple[str, Optional[Union[tuple, list]]]],
                delete_ops,
            ),
            transaction_id=transaction_id,
        )
        logger.info(
            f"[CLEAR_PROJECT_DATA] execute_batch ({len(delete_ops)} ops) in {time.time() - batch_start:.3f}s"
        )

        commit_start = time.time()
        database.commit_transaction(transaction_id)
        logger.info(
            f"[CLEAR_PROJECT_DATA] Committed in {time.time() - commit_start:.3f}s"
        )
        logger.info(
            f"[CLEAR_PROJECT_DATA] Completed clear for project {project_id} in {time.time() - clear_start:.3f}s"
        )

    except Exception as e:
        # Rollback transaction on error
        if transaction_id:
            try:
                rollback_start = time.time()
                database.rollback_transaction(transaction_id)
                logger.error(
                    f"[CLEAR_PROJECT_DATA] Rolled back transaction {transaction_id} in {time.time() - rollback_start:.3f}s due to error: {e}"
                )
            except Exception as rollback_error:
                logger.error(
                    f"[CLEAR_PROJECT_DATA] Error during rollback: {rollback_error}"
                )
        raise
