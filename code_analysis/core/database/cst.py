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
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        """
        SELECT file_mtime FROM cst_trees
        WHERE file_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (file_id,),
    )
    row = cursor.fetchone()
    if not row:
        return True

    db_mtime = row[0]
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
    assert self.conn is not None
    cursor = self.conn.cursor()
    if overwrite:
        cursor.execute(
            """
                DELETE FROM cst_trees
                WHERE file_id = ?
            """,
            (file_id,),
        )
    if not overwrite:
        cursor.execute(
            """
                SELECT id FROM cst_trees
                WHERE file_id = ? AND cst_hash = ?
            """,
            (file_id, cst_hash),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                    UPDATE cst_trees
                    SET cst_code = ?, file_mtime = ?, updated_at = julianday('now')
                    WHERE id = ?
                """,
                (cst_code, file_mtime, existing[0]),
            )
            self.conn.commit()
            return existing[0]
    cursor.execute(
        """
            INSERT INTO cst_trees
            (file_id, project_id, cst_code, cst_hash, file_mtime)
            VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, project_id, cst_code, cst_hash, file_mtime),
    )
    self.conn.commit()
    result = cursor.lastrowid
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
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        """
        SELECT id, file_id, project_id, cst_code, cst_hash, file_mtime, created_at, updated_at
        FROM cst_trees
        WHERE file_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (file_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    return {
        "id": row[0],
        "file_id": row[1],
        "project_id": row[2],
        "cst_code": row[3],
        "cst_hash": row[4],
        "file_mtime": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    }

