"""
File trash: mark_file_deleted, unmark_file_deleted, get_deleted_files, hard_delete_file.

:class:`~code_analysis.core.database.base.CodeDatabase` mixes these in as methods; each
implementation delegates to :mod:`~code_analysis.core.database.files.trash_standalone`
via :func:`~code_analysis.core.database.files.trash_codedatabase_adapter.trash_driver_for_codedatabase` (see that module for why the facade exists).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List, Optional

from .trash_codedatabase_adapter import trash_driver_for_codedatabase
from .trash_standalone import (
    get_deleted_files_via_driver,
    hard_delete_file_via_driver,
    mark_file_deleted_via_driver,
    unmark_file_deleted_via_driver,
)


def mark_file_deleted(
    self,
    file_path: str,
    project_id: str,
    version_dir: Optional[str] = None,
    reason: Optional[str] = None,
    trash_dir: Optional[str] = None,
) -> bool:
    """
    Mark file as deleted (soft delete) and move to file trash.

    Delegates to :func:`~code_analysis.core.database.files.trash_standalone.mark_file_deleted_via_driver`.
    """
    d = trash_driver_for_codedatabase(self)
    ok = mark_file_deleted_via_driver(
        d,
        file_path,
        project_id,
        version_dir=version_dir,
        reason=reason,
        trash_dir=trash_dir,
    )
    if ok:
        self._commit()
    return ok


def unmark_file_deleted(
    self,
    file_path: str,
    project_id: str,
    out_error: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Unmark file as deleted (recovery) and move back to original location.

    Delegates to :func:`~code_analysis.core.database.files.trash_standalone.unmark_file_deleted_via_driver`.
    """
    d = trash_driver_for_codedatabase(self)
    ok = unmark_file_deleted_via_driver(d, file_path, project_id, out_error=out_error)
    if ok:
        self._commit()
    return ok


def get_deleted_files(self, project_id: str) -> List[Dict[str, Any]]:
    """
    Get all deleted files for a project.

    Delegates to :func:`~code_analysis.core.database.files.trash_standalone.get_deleted_files_via_driver`.
    """
    return get_deleted_files_via_driver(trash_driver_for_codedatabase(self), project_id)


def hard_delete_file(self, file_id: str | int) -> None:
    """
    Permanently delete file and all related data (hard delete).

    Delegates to :func:`~code_analysis.core.database.files.trash_standalone.hard_delete_file_via_driver`.
    """
    d = trash_driver_for_codedatabase(self)
    hard_delete_file_via_driver(d, file_id)
    self._commit()
