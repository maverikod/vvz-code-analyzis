"""
Database file operations: CRUD, update, trash, versions, atomic.

All functions are attached to CodeDatabase by database/__init__.py.
Split into submodules to keep file size under limit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .atomic import update_file_data_atomic
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
from .update import update_file_data
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
    "get_deleted_files",
    "get_file_by_id",
    "get_file_by_path",
    "get_file_id",
    "get_file_summary",
    "get_file_versions",
    "get_files_needing_chunking",
    "hard_delete_file",
    "mark_file_deleted",
    "mark_file_needs_chunking",
    "remove_missing_files",
    "unmark_file_deleted",
    "update_and_vectorize_file",
    "update_file_data",
    "update_file_data_atomic",
    "vectorize_file_immediately",
]
