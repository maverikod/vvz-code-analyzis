"""
Project management MCP commands.

Re-exports all command classes from dedicated modules.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .change_project_id import ChangeProjectIdMCPCommand
from .clear_trash import ClearTrashMCPCommand
from .create_project import CreateProjectMCPCommand
from .delete_project import DeleteProjectMCPCommand
from .delete_unwatched_projects import DeleteUnwatchedProjectsMCPCommand
from .list_projects import ListProjectsMCPCommand
from .list_trashed_projects import ListTrashedProjectsMCPCommand
from .list_watch_dirs import ListWatchDirsMCPCommand
from .permanently_delete_from_trash import PermanentlyDeleteFromTrashMCPCommand
from .restore_project_from_trash import RestoreProjectFromTrashMCPCommand
from .set_project_processing_paused import SetProjectProcessingPausedMCPCommand

__all__ = [
    "ChangeProjectIdMCPCommand",
    "ClearTrashMCPCommand",
    "CreateProjectMCPCommand",
    "DeleteProjectMCPCommand",
    "DeleteUnwatchedProjectsMCPCommand",
    "ListProjectsMCPCommand",
    "ListTrashedProjectsMCPCommand",
    "ListWatchDirsMCPCommand",
    "PermanentlyDeleteFromTrashMCPCommand",
    "RestoreProjectFromTrashMCPCommand",
    "SetProjectProcessingPausedMCPCommand",
]
