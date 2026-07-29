"""
Database file operations: CRUD, update, trash, versions.

Split into submodules to keep file size under limit.

``atomic.py`` (``update_file_data_atomic``, the legacy in-transaction
``CodeDatabase``-bound updater) was removed as dead code (bug 3e7177d6
inventory): ``CodeDatabase`` itself no longer exists post the SQLite/DB-layer
collapse, and grep confirmed zero callers anywhere in the repo besides this
re-export. The live file-data write path is
``code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch``
(driver-direct), reached via ``sync_file_to_db_atomic`` /
``compose_cst_writer.apply_changes`` / ``restore_backup_file``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .crud import (
    _clear_file_vectors,
    add_file,
    clear_file_data,
    delete_file,
    get_file_by_id,
    get_file_by_path,
    get_file_id,
)
from .query import (
    get_file_summary,
    get_files_needing_chunking,
    mark_file_needs_chunking,
)
from .trash import (
    get_deleted_files,
    hard_delete_file,
    mark_file_deleted,
    unmark_file_deleted,
)
from .trash_standalone import (
    get_deleted_files_via_driver,
    hard_delete_file_via_driver,
    mark_file_deleted_via_driver,
    unmark_file_deleted_via_driver,
)
from .update import update_file_data
from .update_standalone import update_file_data_via_driver
from .update_vectorize import (
    remove_missing_files,
    update_and_vectorize_file,
    vectorize_file_immediately,
)
from .versions import collapse_file_versions, get_file_versions

__all__ = [
    "_clear_file_vectors",
    "add_file",
    "clear_file_data",
    "collapse_file_versions",
    "delete_file",
    "get_deleted_files_via_driver",
    "get_deleted_files",
    "get_file_by_id",
    "get_file_by_path",
    "get_file_id",
    "get_file_summary",
    "get_file_versions",
    "get_files_needing_chunking",
    "hard_delete_file_via_driver",
    "hard_delete_file",
    "mark_file_deleted_via_driver",
    "mark_file_deleted",
    "mark_file_needs_chunking",
    "remove_missing_files",
    "unmark_file_deleted_via_driver",
    "unmark_file_deleted",
    "update_and_vectorize_file",
    "update_file_data",
    "update_file_data_via_driver",
    "vectorize_file_immediately",
]
