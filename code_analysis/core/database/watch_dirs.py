"""
Module watch_dirs - database operations for watch directories.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional

from code_analysis.core.sql_portable import sql_julian_timestamp_now_expr

from .watch_dir_sql import (
    watch_dir_paths_insert_or_replace_null_sql,
    watch_dir_paths_insert_or_replace_sql,
    watch_dirs_insert_or_replace_sql,
)
from .watch_dirs_partition import current_server_instance_id, sql_server_instance_filter

logger = logging.getLogger(__name__)


def create_watch_dir(
    self,
    watch_dir_id: str,
    name: Optional[str] = None,
    *,
    server_instance_id: Optional[str] = None,
) -> None:
    """
    Create a new watch directory entry for the current server instance.

    Args:
        watch_dir_id: UUID4 identifier for watch directory
        name: Optional human-readable name
        server_instance_id: Override partition key (default: config instance_uuid)
    """
    sid = server_instance_id or current_server_instance_id()
    self._execute(
        watch_dirs_insert_or_replace_sql(self),
        (sid, watch_dir_id, name),
    )
    self._commit()
    logger.debug(
        "Created watch_dir: server_instance_id=%s id=%s name=%s",
        sid,
        watch_dir_id,
        name,
    )


def get_watch_dir(
    self,
    watch_dir_id: str,
    *,
    server_instance_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get watch directory by ID for the current server instance.

    Args:
        watch_dir_id: UUID4 identifier

    Returns:
        Watch directory record as dictionary or None if not found
    """
    sid = server_instance_id or current_server_instance_id()
    where_sql, params = sql_server_instance_filter("server_instance_id")
    return self._fetchone(
        f"SELECT * FROM watch_dirs WHERE {where_sql} AND id = ?",
        params + (watch_dir_id,),
    )


def get_all_watch_dirs(
    self,
    *,
    server_instance_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get all watch directories for the current server instance.

    Returns:
        List of watch directory records
    """
    sid = server_instance_id or current_server_instance_id()
    where_sql, params = sql_server_instance_filter("server_instance_id")
    return self._fetchall(
        f"SELECT * FROM watch_dirs WHERE {where_sql} ORDER BY created_at",
        params,
    )


def update_watch_dir_path(
    self,
    watch_dir_id: str,
    absolute_path: Optional[str],
    *,
    server_instance_id: Optional[str] = None,
) -> None:
    """
    Update or create watch directory path mapping for the current server instance.

    Args:
        watch_dir_id: UUID4 identifier
        absolute_path: Absolute normalized path, or None if not found
    """
    sid = server_instance_id or current_server_instance_id()
    where_sql, where_params = sql_server_instance_filter(
        "server_instance_id", config=None
    )
    existing = self._fetchone(
        f"SELECT watch_dir_id FROM watch_dir_paths "
        f"WHERE {where_sql} AND watch_dir_id = ?",
        where_params + (watch_dir_id,),
    )

    _now = sql_julian_timestamp_now_expr(self)
    if existing:
        self._execute(
            f"""
            UPDATE watch_dir_paths
            SET absolute_path = ?, updated_at = {_now}
            WHERE server_instance_id = ? AND watch_dir_id = ?
            """,
            (absolute_path, sid, watch_dir_id),
        )
    else:
        self._execute(
            watch_dir_paths_insert_or_replace_sql(self),
            (sid, watch_dir_id, absolute_path),
        )
    self._commit()
    logger.debug(
        "Updated watch_dir_path: server_instance_id=%s %s -> %s",
        sid,
        watch_dir_id,
        absolute_path,
    )


def get_watch_dir_path(
    self,
    watch_dir_id: str,
    *,
    server_instance_id: Optional[str] = None,
) -> Optional[str]:
    """
    Get absolute path for watch directory on the current server instance.

    Args:
        watch_dir_id: UUID4 identifier

    Returns:
        Absolute normalized path or None if not found
    """
    sid = server_instance_id or current_server_instance_id()
    row = self._fetchone(
        "SELECT absolute_path FROM watch_dir_paths "
        "WHERE server_instance_id = ? AND watch_dir_id = ?",
        (sid, watch_dir_id),
    )
    return row["absolute_path"] if row else None


def get_watch_dir_by_path(
    self,
    absolute_path: str,
    *,
    server_instance_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get watch directory by absolute path for the current server instance.

    Args:
        absolute_path: Absolute normalized path

    Returns:
        Watch directory record with path mapping or None if not found
    """
    from ..path_normalization import normalize_path_simple

    normalized_path = normalize_path_simple(absolute_path)
    sid = server_instance_id or current_server_instance_id()

    row = self._fetchone(
        """
        SELECT wd.*, wdp.absolute_path
        FROM watch_dirs wd
        JOIN watch_dir_paths wdp
          ON wd.server_instance_id = wdp.server_instance_id
         AND wd.id = wdp.watch_dir_id
        WHERE wd.server_instance_id = ?
          AND wdp.absolute_path = ?
        """,
        (sid, normalized_path),
    )
    return row


def get_all_watch_dir_paths(
    self,
    *,
    server_instance_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get all watch directory path mappings for the current server instance.

    Returns:
        List of watch directory records with paths
    """
    sid = server_instance_id or current_server_instance_id()
    return self._fetchall(
        """
        SELECT wd.*, wdp.absolute_path
        FROM watch_dirs wd
        LEFT JOIN watch_dir_paths wdp
          ON wd.server_instance_id = wdp.server_instance_id
         AND wd.id = wdp.watch_dir_id
        WHERE wd.server_instance_id = ?
        ORDER BY wd.created_at
        """,
        (sid,),
    )


def delete_watch_dir(
    self,
    watch_dir_id: str,
    *,
    server_instance_id: Optional[str] = None,
) -> None:
    """
    Delete watch directory and its path mapping for the current server instance.

    Args:
        watch_dir_id: UUID4 identifier
    """
    sid = server_instance_id or current_server_instance_id()
    self._execute(
        "DELETE FROM watch_dirs WHERE server_instance_id = ? AND id = ?",
        (sid, watch_dir_id),
    )
    self._commit()
    logger.debug(
        "Deleted watch_dir: server_instance_id=%s id=%s", sid, watch_dir_id
    )
