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
    row = self._fetchone(
        "\n            SELECT file_mtime FROM ast_trees\n            WHERE file_id = ?\n            ORDER BY updated_at DESC\n            LIMIT 1\n        ",
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
        ast_json: Serialized AST as JSON string
        ast_hash: Hash of AST for change detection
        file_mtime: File modification time
        overwrite: If True, delete all old AST trees for this file before saving

    Returns:
        AST tree ID
    """
    if overwrite:
        self._execute(
            "\n                DELETE FROM ast_trees\n                WHERE file_id = ?\n            ",
            (file_id,),
        )
    if not overwrite:
        existing = self._fetchone(
            "\n                SELECT id FROM ast_trees\n                WHERE file_id = ? AND ast_hash = ?\n            ",
            (file_id, ast_hash),
        )
        if existing:
            self._execute(
                "\n                    UPDATE ast_trees\n                    SET ast_json = ?, file_mtime = ?, updated_at = julianday('now')\n                    WHERE id = ?\n                ",
                (ast_json, file_mtime, existing["id"]),
            )
            self._commit()
            return existing["id"]
    self._execute(
        "\n            INSERT INTO ast_trees\n            (file_id, project_id, ast_json, ast_hash, file_mtime)\n            VALUES (?, ?, ?, ?, ?)\n        ",
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
        ast_json: Serialized AST as JSON string
        ast_hash: Hash of AST for change detection
        file_mtime: File modification time

    Returns:
        AST tree ID
    """
    return self.save_ast_tree(file_id, project_id, ast_json, ast_hash, file_mtime, overwrite=True)


async def get_ast_tree(self, file_id: int) -> Optional[Dict[str, Any]]:
    """
    Get AST tree for a file.

    Args:
        file_id: File ID

    Returns:
        AST tree record with JSON or None
    """
    row = self._fetchone(
        "\n            SELECT id, file_id, project_id, ast_json, ast_hash, file_mtime, created_at, updated_at\n            FROM ast_trees\n            WHERE file_id = ?\n            ORDER BY updated_at DESC\n            LIMIT 1\n        ",
        (file_id,),
    )
    return row
