"""
File management commands package: cleanup, mark/unmark deleted, restore, collapse, repair.

Re-exports command classes for backward compatibility:
from code_analysis.commands.file_management import CleanupDeletedFilesCommand, ...

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .cleanup_deleted_files import CleanupDeletedFilesCommand
from .collapse_versions import CollapseVersionsCommand
from .mark_file_deleted import MarkFileDeletedCommand
from .repair_database import RepairDatabaseCommand
from .restore_deleted_files import RestoreDeletedFilesCommand
from .unmark_deleted_file import UnmarkDeletedFileCommand

__all__ = [
    "CleanupDeletedFilesCommand",
    "CollapseVersionsCommand",
    "MarkFileDeletedCommand",
    "RepairDatabaseCommand",
    "RestoreDeletedFilesCommand",
    "UnmarkDeletedFileCommand",
]
