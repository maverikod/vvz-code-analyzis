"""
Module watch_dirs - database operations for watch directories.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def create_watch_dir(
    self, watch_dir_id: str, name: Optional[str] = None
) -> None:
    """
    Create a new watch directory entry.

    Args:
        watch_dir_id: UUID4 identifier for watch directory
        name: Optional human-readable name
    """
    self._execute(
        """
        INSERT OR REPLACE INTO watch_dirs (id, name, updated_at)
        VALUES (?, ?, julianday('now'))
        """,
        (watch_dir_id, name),
    )
    self._commit()
    logger.debug(f"Created watch_dir: {watch_dir_id} with name: {name}")


def get_watch_dir(self, watch_dir_id: str) -> Optional[Dict[str, Any]]:
    """
    Get watch directory by ID.

    Args:
        watch_dir_id: UUID4 identifier

    Returns:
        Watch directory record as dictionary or None if not found
    """
    return self._fetchone(
        "SELECT * FROM watch_dirs WHERE id = ?",
        (watch_dir_id,),
    )


def get_all_watch_dirs(self) -> List[Dict[str, Any]]:
    """
    Get all watch directories.

    Returns:
        List of watch directory records
    """
    return self._fetchall("SELECT * FROM watch_dirs ORDER BY created_at")


def update_watch_dir_path(
    self, watch_dir_id: str, absolute_path: Optional[str]
) -> None:
    """
    Update or create watch directory path mapping.

    Args:
        watch_dir_id: UUID4 identifier
        absolute_path: Absolute normalized path, or None if not found
    """
    # Check if entry exists
    existing = self._fetchone(
        "SELECT watch_dir_id FROM watch_dir_paths WHERE watch_dir_id = ?",
        (watch_dir_id,),
    )

    if existing:
        # Update existing entry
        self._execute(
            """
            UPDATE watch_dir_paths
            SET absolute_path = ?, updated_at = julianday('now')
            WHERE watch_dir_id = ?
            """,
            (absolute_path, watch_dir_id),
        )
    else:
        # Create new entry
        self._execute(
            """
            INSERT INTO watch_dir_paths (watch_dir_id, absolute_path, updated_at)
            VALUES (?, ?, julianday('now'))
            """,
            (watch_dir_id, absolute_path),
        )
    self._commit()
    logger.debug(
        f"Updated watch_dir_path: {watch_dir_id} -> {absolute_path}"
    )


def get_watch_dir_path(self, watch_dir_id: str) -> Optional[str]:
    """
    Get absolute path for watch directory.

    Args:
        watch_dir_id: UUID4 identifier

    Returns:
        Absolute normalized path or None if not found
    """
    row = self._fetchone(
        "SELECT absolute_path FROM watch_dir_paths WHERE watch_dir_id = ?",
        (watch_dir_id,),
    )
    return row["absolute_path"] if row else None


def get_watch_dir_by_path(self, absolute_path: str) -> Optional[Dict[str, Any]]:
    """
    Get watch directory by absolute path.

    Args:
        absolute_path: Absolute normalized path

    Returns:
        Watch directory record with path mapping or None if not found
    """
    # Normalize path
    from ..path_normalization import normalize_path_simple

    normalized_path = normalize_path_simple(absolute_path)

    row = self._fetchone(
        """
        SELECT wd.*, wdp.absolute_path
        FROM watch_dirs wd
        JOIN watch_dir_paths wdp ON wd.id = wdp.watch_dir_id
        WHERE wdp.absolute_path = ?
        """,
        (normalized_path,),
    )
    return row


def get_all_watch_dir_paths(self) -> List[Dict[str, Any]]:
    """
    Get all watch directory path mappings.

    Returns:
        List of watch directory records with paths
    """
    return self._fetchall(
        """
        SELECT wd.*, wdp.absolute_path
        FROM watch_dirs wd
        LEFT JOIN watch_dir_paths wdp ON wd.id = wdp.watch_dir_id
        ORDER BY wd.created_at
        """
    )


def delete_watch_dir(self, watch_dir_id: str) -> None:
    """
    Delete watch directory and its path mapping.

    Args:
        watch_dir_id: UUID4 identifier
    """
    # Path mapping will be deleted by CASCADE
    self._execute("DELETE FROM watch_dirs WHERE id = ?", (watch_dir_id,))
    self._commit()
    logger.debug(f"Deleted watch_dir: {watch_dir_id}")
