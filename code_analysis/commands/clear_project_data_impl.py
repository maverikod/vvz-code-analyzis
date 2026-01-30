"""
Internal helper: clear all project data from database in a single transaction.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


async def _clear_project_data_impl(database: DatabaseClient, project_id: str) -> None:
    """Clear all data for a project using DatabaseClient atomically.

    This is a helper function that implements clear_project_data for DatabaseClient.
    All operations are performed within a single transaction for atomicity and performance.
    """
    clear_start = time.time()
    logger.info(f"[CLEAR_PROJECT_DATA] Starting clear for project {project_id}")

    transaction_id = None
    try:
        # Begin transaction
        tx_start = time.time()
        transaction_id = database.begin_transaction()
        logger.info(
            f"[CLEAR_PROJECT_DATA] Started transaction {transaction_id} in {time.time() - tx_start:.3f}s"
        )

        # Get all file IDs for this project
        step_start = time.time()
        files = database.select(
            "files", where={"project_id": project_id}, columns=["id"]
        )
        file_ids = [f["id"] for f in files]
        logger.info(
            f"[CLEAR_PROJECT_DATA] Got {len(file_ids)} file IDs in {time.time() - step_start:.3f}s"
        )

        # Delete duplicates first (before files)
        try:
            step_start = time.time()
            # Delete duplicate occurrences first (foreign key constraint)
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
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted duplicate_occurrences in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            # Delete duplicate groups
            database.execute(
                "DELETE FROM code_duplicates WHERE project_id = ?",
                (project_id,),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted code_duplicates in {time.time() - step_start:.3f}s"
            )
        except Exception as e:
            logger.warning(f"Failed to delete duplicates for project {project_id}: {e}")

        if not file_ids:
            # Delete vector_index even if no files
            step_start = time.time()
            database.execute(
                "DELETE FROM vector_index WHERE project_id = ?",
                (project_id,),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted vector_index in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted project record in {time.time() - step_start:.3f}s"
            )

            # Commit transaction
            commit_start = time.time()
            database.commit_transaction(transaction_id)
            logger.info(
                f"[CLEAR_PROJECT_DATA] Committed transaction {transaction_id} in {time.time() - commit_start:.3f}s"
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Completed clear for project {project_id} (no files) in {time.time() - clear_start:.3f}s"
            )
            return

        # Delete data for all files
        if file_ids:
            step_start = time.time()
            placeholders = ",".join("?" * len(file_ids))
            # Get class IDs
            classes = database.execute(
                f"SELECT id FROM classes WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Got class IDs in {time.time() - step_start:.3f}s"
            )
            # Handle different result formats
            if isinstance(classes, list):
                classes_data = classes
            elif isinstance(classes, dict):
                classes_data = classes.get("data", [])
            else:
                classes_data = []
            class_ids = [c["id"] for c in classes_data]

            # Get content IDs for FTS
            step_start = time.time()
            content_rows = database.execute(
                f"SELECT id FROM code_content WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Got content IDs in {time.time() - step_start:.3f}s"
            )
            # Handle different result formats
            if isinstance(content_rows, list):
                content_data = content_rows
            elif isinstance(content_rows, dict):
                content_data = content_rows.get("data", [])
            else:
                content_data = []
            content_ids = [c["id"] for c in content_data]

            # Delete FTS entries in batches
            if content_ids:
                batch_size = 1000
                batch_count = 0
                for i in range(0, len(content_ids), batch_size):
                    batch = content_ids[i : i + batch_size]
                    batch_placeholders = ",".join("?" * len(batch))
                    try:
                        batch_start = time.time()
                        database.execute(
                            f"DELETE FROM code_content_fts WHERE rowid IN ({batch_placeholders})",
                            tuple(batch),
                            transaction_id=transaction_id,
                        )
                        batch_count += 1
                        logger.debug(
                            f"[CLEAR_PROJECT_DATA] Deleted FTS batch {batch_count} ({len(batch)} rows) in {time.time() - batch_start:.3f}s"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete FTS batch {i//batch_size + 1} for project {project_id}: {e}"
                        )
                        break
                logger.info(
                    f"[CLEAR_PROJECT_DATA] Deleted {batch_count} FTS batches ({len(content_ids)} total rows)"
                )

            # Delete methods
            if class_ids:
                step_start = time.time()
                method_placeholders = ",".join("?" * len(class_ids))
                database.execute(
                    f"DELETE FROM methods WHERE class_id IN ({method_placeholders})",
                    tuple(class_ids),
                    transaction_id=transaction_id,
                )
                logger.info(
                    f"[CLEAR_PROJECT_DATA] Deleted methods in {time.time() - step_start:.3f}s"
                )

            # Delete other file-related data
            step_start = time.time()
            database.execute(
                f"DELETE FROM classes WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted classes in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                f"DELETE FROM functions WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted functions in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                f"DELETE FROM imports WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted imports in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                f"DELETE FROM issues WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted issues in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                f"DELETE FROM code_content WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted code_content in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                f"DELETE FROM ast_trees WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted ast_trees in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                f"DELETE FROM cst_trees WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted cst_trees in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                f"DELETE FROM code_chunks WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted code_chunks in {time.time() - step_start:.3f}s"
            )

            step_start = time.time()
            database.execute(
                "DELETE FROM files WHERE id IN ({})".format(placeholders),
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(
                f"[CLEAR_PROJECT_DATA] Deleted files in {time.time() - step_start:.3f}s"
            )

        # Delete project-level data
        step_start = time.time()
        database.execute(
            "DELETE FROM vector_index WHERE project_id = ?",
            (project_id,),
            transaction_id=transaction_id,
        )
        logger.info(
            f"[CLEAR_PROJECT_DATA] Deleted vector_index in {time.time() - step_start:.3f}s"
        )

        step_start = time.time()
        database.execute(
            "DELETE FROM projects WHERE id = ?",
            (project_id,),
            transaction_id=transaction_id,
        )
        logger.info(
            f"[CLEAR_PROJECT_DATA] Deleted project record in {time.time() - step_start:.3f}s"
        )

        # Commit transaction
        commit_start = time.time()
        database.commit_transaction(transaction_id)
        logger.info(
            f"[CLEAR_PROJECT_DATA] Committed transaction {transaction_id} in {time.time() - commit_start:.3f}s"
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
