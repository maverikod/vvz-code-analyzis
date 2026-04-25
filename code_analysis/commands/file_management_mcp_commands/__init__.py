"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .cleanup_deleted_files import CleanupDeletedFilesMCPCommand
from .unmark_deleted_file import UnmarkDeletedFileMCPCommand
from .delete_file import DeleteFileMCPCommand
from .delete_files_by_mask import DeleteFilesByMaskMCPCommand
from .restore_deleted_files import RestoreDeletedFilesMCPCommand
from .list_deleted_files import ListDeletedFilesMCPCommand
from .collapse_versions import CollapseVersionsMCPCommand
from .repair_database import RepairDatabaseMCPCommand
from .create_text_file import CreateTextFileMCPCommand

__all__ = [
    "CleanupDeletedFilesMCPCommand",
    "UnmarkDeletedFileMCPCommand",
    "DeleteFileMCPCommand",
    "DeleteFilesByMaskMCPCommand",
    "RestoreDeletedFilesMCPCommand",
    "ListDeletedFilesMCPCommand",
    "CollapseVersionsMCPCommand",
    "RepairDatabaseMCPCommand",
    "CreateTextFileMCPCommand",
]
