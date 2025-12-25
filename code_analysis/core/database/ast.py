"""
Module ast.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Dict, Any, Optional


def is_ast_outdated(self, file_id: int, file_mtime: float) -> bool:
    """
    Check if AST tree is outdated compared to file modification time.

    Args:
        file_id: File ID
        file_mtime: File modification time

    Returns:
        True if AST is outdated or doesn't exist, False otherwise
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        "\n            SELECT file_mtime FROM ast_trees\n            WHERE file_id = ?\n            ORDER BY updated_at DESC\n            LIMIT 1\n        ",
        (file_id,),
    )
    row = cursor.fetchone()
    if not row:
        return True
    db_mtime = row[0]
    return file_mtime > db_mtime


async def save_ast_tree(
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
        ast_json: Serialized AST as JSON string
        ast_hash: Hash of AST for change detection
        file_mtime: File modification time
        overwrite: If True, delete all old AST trees for this file before saving

    Returns:
        AST tree ID
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    if overwrite:
        cursor.execute(
            "\n                DELETE FROM ast_trees\n                WHERE file_id = ?\n            ",
            (file_id,),
        )
    if not overwrite:
        cursor.execute(
            "\n                SELECT id FROM ast_trees\n                WHERE file_id = ? AND ast_hash = ?\n            ",
            (file_id, ast_hash),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                "\n                    UPDATE ast_trees\n                    SET ast_json = ?, file_mtime = ?, updated_at = julianday('now')\n                    WHERE id = ?\n                ",
                (ast_json, file_mtime, existing[0]),
            )
            self.conn.commit()
            return existing[0]
    cursor.execute(
        "\n            INSERT INTO ast_trees\n            (file_id, project_id, ast_json, ast_hash, file_mtime)\n            VALUES (?, ?, ?, ?, ?)\n        ",
        (file_id, project_id, ast_json, ast_hash, file_mtime),
    )
    self.conn.commit()
    result = cursor.lastrowid
    assert result is not None
    return result


async def overwrite_ast_tree(
    self, file_id: int, project_id: str, ast_json: str, ast_hash: str, file_mtime: float
) -> int:
    """
    Overwrite AST tree for a file (delete old, insert new).

    Args:
        file_id: File ID
        project_id: Project ID
        ast_json: Serialized AST as JSON string
        ast_hash: Hash of AST for change detection
        file_mtime: File modification time

    Returns:
        AST tree ID
    """
    return await self.save_ast_tree(
        file_id, project_id, ast_json, ast_hash, file_mtime, overwrite=True
    )


async def get_ast_tree(self, file_id: int) -> Optional[Dict[str, Any]]:
    """
    Get AST tree for a file.

    Args:
        file_id: File ID

    Returns:
        AST tree record with JSON or None
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        "\n            SELECT id, file_id, project_id, ast_json, ast_hash, file_mtime, created_at, updated_at\n            FROM ast_trees\n            WHERE file_id = ?\n            ORDER BY updated_at DESC\n            LIMIT 1\n        ",
        (file_id,),
    )
    row = cursor.fetchone()
    if row:
        return {
            "id": row[0],
            "file_id": row[1],
            "project_id": row[2],
            "ast_json": row[3],
            "ast_hash": row[4],
            "file_mtime": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }
    return None
