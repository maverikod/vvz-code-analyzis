"""
Watch-directory operations on :class:`~code_analysis.core.database_client.client.DatabaseClient`.

All reads go through RPC ``execute`` / driver SQL with ``server_instance_id`` partition.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.core.database.watch_dirs_query import (
    get_watch_dir_absolute_path as _get_watch_dir_absolute_path,
    list_watch_dirs_with_paths as _list_watch_dirs_with_paths,
    resolve_watch_dir_id_for_project_root as _resolve_watch_dir_id_for_project_root,
    watch_dir_exists as _watch_dir_exists,
)

from .client_base import _DatabaseClientBase


class _ClientAPIWatchDirsMixin(_DatabaseClientBase):
    """Watch-dir helpers for MCP commands (partitioned by current server instance)."""

    def get_watch_dir_absolute_path(self, watch_dir_id: str) -> Optional[str]:
        """Return ``watch_dir_paths.absolute_path`` for ``watch_dir_id``, or None."""
        return _get_watch_dir_absolute_path(self, watch_dir_id)

    def list_watch_dirs_with_paths(self) -> List[Dict[str, Any]]:
        """List watch directories for this server instance."""
        return _list_watch_dirs_with_paths(self)

    def resolve_watch_dir_id_for_project_root(
        self, project_root: Path
    ) -> Optional[str]:
        """Return watch_dir_id whose path is the parent of ``project_root``."""
        return _resolve_watch_dir_id_for_project_root(self, project_root)

    def watch_dir_exists(self, watch_dir_id: str) -> bool:
        """True if ``watch_dir_id`` exists for the current server instance."""
        return _watch_dir_exists(self, watch_dir_id)
