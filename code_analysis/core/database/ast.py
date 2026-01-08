"""
Module AST (Abstract Syntax Tree) storage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def is_ast_outdated(self, file_id: int, file_mtime: float) -> bool:
    """
    Check if AST tree is outdated based on file modification time.

    Args:
        file_id: File ID
        file_mtime: File modification time

    Returns:
        True if AST is outdated, False otherwise
    """
    row = self._fetchone(
        """
        SELECT file_mtime FROM ast_trees
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


def save_ast_tree(
    self,
    file_id: int,
    project_id: str,
    ast_json: str,
    ast_hash: str,
    file_mtime: float,
    overwrite: bool = False,
) -> int:
    """
    Save AST tree for a file.

    Args:
        file_id: File ID
        project_id: Project ID
        ast_json: JSON representation of AST (from ast.dump)
        ast_hash: Hash of AST for change detection
        file_mtime: File modification time
        overwrite: If True, delete all old AST trees for this file before saving

    Returns:
        AST tree ID
    """
    if overwrite:
        self._execute(
            """
                DELETE FROM ast_trees
                WHERE file_id = ?
            """,
            (file_id,),
        )
    if not overwrite:
        existing = self._fetchone(
            """
                SELECT id FROM ast_trees
                WHERE file_id = ? AND ast_hash = ?
            """,
            (file_id, ast_hash),
        )
        if existing:
            self._execute(
                """
                    UPDATE ast_trees
                    SET ast_json = ?, file_mtime = ?, updated_at = julianday('now')
                    WHERE id = ?
                """,
                (ast_json, file_mtime, existing["id"]),
            )
            self._commit()
            return existing["id"]
    self._execute(
        """
            INSERT INTO ast_trees
            (file_id, project_id, ast_json, ast_hash, file_mtime)
            VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, project_id, ast_json, ast_hash, file_mtime),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def overwrite_ast_tree(
    self, file_id: int, project_id: str, ast_json: str, ast_hash: str, file_mtime: float
) -> int:
    """
    Overwrite AST tree for a file (delete old, insert new).

    Args:
        file_id: File ID
        project_id: Project ID
        ast_json: JSON representation of AST
        ast_hash: Hash of AST for change detection
        file_mtime: File modification time

    Returns:
        AST tree ID
    """
    return self.save_ast_tree(
        file_id, project_id, ast_json, ast_hash, file_mtime, overwrite=True
    )


def get_ast_tree(self, file_id: int) -> Optional[Dict[str, Any]]:
    """
    Get AST tree for a file.

    Args:
        file_id: File ID

    Returns:
        Dictionary with AST data or None if not found:
        {
            "id": int,
            "file_id": int,
            "project_id": str,
            "ast_json": str,  # JSON representation of AST
            "ast_hash": str,
            "file_mtime": float,
            "created_at": float,
            "updated_at": float
        }
    """
    row = self._fetchone(
        """
        SELECT id, file_id, project_id, ast_json, ast_hash, file_mtime, created_at, updated_at
        FROM ast_trees
        WHERE file_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (file_id,),
    )
    return row

