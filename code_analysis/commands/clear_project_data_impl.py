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


def _build_delete_batch_no_files(project_id: str) -> List[Tuple[str, Tuple[Any, ...]]]:
    """Build list of (sql, params) for project with no files."""
    return [
        ("DELETE FROM vector_index WHERE project_id = ?", (project_id,)),
        ("DELETE FROM projects WHERE id = ?", (project_id,)),
    ]


def _build_delete_batch_with_files(
    project_id: str,
    file_ids: List[int],
    class_ids: List[int],
    content_ids: List[int],
    placeholders: str,
) -> List[Tuple[str, Tuple[Any, ...]]]:
    """Build list of (sql, params) for all deletes in FK order (one RPC batch).
    Duplicate tables are run separately (optional schema) before this batch.
    """
    ops: List[Tuple[str, Tuple[Any, ...]]] = []

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

    # Child tables (methods before classes)
    if class_ids:
        method_ph = ",".join("?" * len(class_ids))
        ops.append(
            (
                f"DELETE FROM methods WHERE class_id IN ({method_ph})",
                tuple(class_ids),
            )
        )

    # File-related tables
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
        (f"DELETE FROM issues WHERE file_id IN ({placeholders})", tuple(file_ids))
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
        (
            f"DELETE FROM code_chunks WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    ops.append(
        (f"DELETE FROM usages WHERE file_id IN ({placeholders})", tuple(file_ids))
    )
    # entity_cross_ref may not exist in all schemas
    ops.append(
        (
            f"DELETE FROM entity_cross_ref WHERE file_id IN ({placeholders})",
            tuple(file_ids),
        )
    )
    ops.append(
        (
            "DELETE FROM files WHERE id IN ({})".format(placeholders),
            tuple(file_ids),
        )
    )

    # Project-level
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

        step_start = time.time()
        classes = database.execute(
            f"SELECT id FROM classes WHERE file_id IN ({placeholders})",
            tuple(file_ids),
            transaction_id=transaction_id,
        )
        if isinstance(classes, list):
            classes_data = classes
        elif isinstance(classes, dict):
            classes_data = classes.get("data", [])
        else:
            classes_data = []
        class_ids = [c["id"] for c in classes_data]
        logger.info(
            f"[CLEAR_PROJECT_DATA] Got class IDs in {time.time() - step_start:.3f}s"
        )

        step_start = time.time()
        content_rows = database.execute(
            f"SELECT id FROM code_content WHERE file_id IN ({placeholders})",
            tuple(file_ids),
            transaction_id=transaction_id,
        )
        if isinstance(content_rows, list):
            content_data = content_rows
        elif isinstance(content_rows, dict):
            content_data = content_rows.get("data", [])
        else:
            content_data = []
        content_ids = [c["id"] for c in content_data]
        logger.info(
            f"[CLEAR_PROJECT_DATA] Got content IDs in {time.time() - step_start:.3f}s"
        )

        # Optional schema: duplicates (run separately so batch does not fail if missing)
        try:
            database.execute(
                """
                DELETE FROM duplicate_occurrences
                WHERE duplicate_id IN (
                    SELECT id FROM code_duplicates WHERE project_id = ?
                )
                """,
                (project_id,),
                transaction_id=transaction_id,
            )
            database.execute(
                "DELETE FROM code_duplicates WHERE project_id = ?",
                (project_id,),
                transaction_id=transaction_id,
            )
        except Exception as e:
            logger.warning(f"Failed to delete duplicates for project {project_id}: {e}")

        delete_ops = _build_delete_batch_with_files(
            project_id, file_ids, class_ids, content_ids, placeholders
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
