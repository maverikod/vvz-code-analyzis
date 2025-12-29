"""
Module CST (Concrete Syntax Tree) storage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import hashlib
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def is_cst_outdated(self, file_id: int, file_mtime: float) -> bool:
    """
    Check if CST tree is outdated based on file modification time.

    Args:
        file_id: File ID
        file_mtime: File modification time

    Returns:
        True if CST is outdated, False otherwise
    """
    row = self._fetchone(
        """
        SELECT file_mtime FROM cst_trees
        WHERE file_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (file_id,),
    )
    if not row:
        return True

    db_mtime = row["file_mtime"]
    return file_mtime > db_mtime


def save_cst_tree(
    self,
    file_id: int,
    project_id: str,
    cst_code: str,
    cst_hash: str,
    file_mtime: float,
    overwrite: bool = False,
) -> int:
    """
    Save CST tree (source code) for a file.

    Args:
        file_id: File ID
        project_id: Project ID
        cst_code: Source code of the file (can be restored via cst.Module.code)
        cst_hash: Hash of CST for change detection
        file_mtime: File modification time
        overwrite: If True, delete all old CST trees for this file before saving

    Returns:
        CST tree ID
    """
    if overwrite:
        self._execute(
            """
                DELETE FROM cst_trees
                WHERE file_id = ?
            """,
            (file_id,),
        )
    if not overwrite:
        existing = self._fetchone(
            """
                SELECT id FROM cst_trees
                WHERE file_id = ? AND cst_hash = ?
            """,
            (file_id, cst_hash),
        )
        if existing:
            self._execute(
                """
                    UPDATE cst_trees
                    SET cst_code = ?, file_mtime = ?, updated_at = julianday('now')
                    WHERE id = ?
                """,
                (cst_code, file_mtime, existing["id"]),
            )
            self._commit()
            return existing["id"]
    self._execute(
        """
            INSERT INTO cst_trees
            (file_id, project_id, cst_code, cst_hash, file_mtime)
            VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, project_id, cst_code, cst_hash, file_mtime),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def overwrite_cst_tree(
    self, file_id: int, project_id: str, cst_code: str, cst_hash: str, file_mtime: float
) -> int:
    """
    Overwrite CST tree for a file (delete old, insert new).

    Args:
        file_id: File ID
        project_id: Project ID
        cst_code: Source code of the file
        cst_hash: Hash of CST for change detection
        file_mtime: File modification time

    Returns:
        CST tree ID
    """
    return self.save_cst_tree(file_id, project_id, cst_code, cst_hash, file_mtime, overwrite=True)


async def get_cst_tree(self, file_id: int) -> Optional[Dict[str, Any]]:
    """
    Get CST tree (source code) for a file.

    Args:
        file_id: File ID

    Returns:
        Dictionary with CST data or None if not found:
        {
            "id": int,
            "file_id": int,
            "project_id": str,
            "cst_code": str,  # Source code that can be restored
            "cst_hash": str,
            "file_mtime": float,
            "created_at": float,
            "updated_at": float
        }
    """
    row = self._fetchone(
        """
        SELECT id, file_id, project_id, cst_code, cst_hash, file_mtime, created_at, updated_at
        FROM cst_trees
        WHERE file_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (file_id,),
    )
    return row

