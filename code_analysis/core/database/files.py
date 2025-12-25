"""
Module files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def get_file_by_path(self, path: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get file record by path and project ID.

    Args:
        path: File path
        project_id: Project ID

    Returns:
        File record as dictionary or None if not found
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        "SELECT * FROM files WHERE path = ? AND project_id = ?", (path, project_id)
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def add_file(
    self,
    path: str,
    lines: int,
    last_modified: float,
    has_docstring: bool,
    project_id: str,
) -> int:
    """Add or update file record. Returns file_id."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        "\n            INSERT OR REPLACE INTO files\n            (project_id, path, lines, last_modified, has_docstring, updated_at)\n            VALUES (?, ?, ?, ?, ?, julianday('now'))\n        ",
        (project_id, path, lines, last_modified, has_docstring),
    )
    self.conn.commit()
    result = cursor.lastrowid
    assert result is not None
    return result


def get_file_id(self, path: str, project_id: str) -> Optional[int]:
    """Get file ID by path and project."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        "SELECT id FROM files WHERE path = ? AND project_id = ?", (path, project_id)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
    """Get file record by ID."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def delete_file(self, file_id: int) -> None:
    """Delete file and all related records (cascade)."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
    self.conn.commit()


def clear_file_data(self, file_id: int) -> None:
    """
    Clear all data for a file.

    Removes all related data including:
    - classes and their methods
    - functions
    - imports
    - issues
    - usages
    - dependencies (both as source and target)
    - code_content and FTS index
    - AST trees
    - code chunks
    - vector index entries

    NOTE: When FAISS is implemented, this method should:
    1. Get all vector_ids from code_chunks for this file_id
    2. Remove these vectors from FAISS index
    3. Then delete from database
    This ensures FAISS stays in sync when files are updated.
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT id FROM classes WHERE file_id = ?", (file_id,))
    class_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT id FROM code_content WHERE file_id = ?", (file_id,))
    content_ids = [row[0] for row in cursor.fetchall()]
    if content_ids:
        placeholders = ",".join("?" * len(content_ids))
        cursor.execute(
            f"DELETE FROM code_content_fts WHERE rowid IN ({placeholders})", content_ids
        )
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        cursor.execute(
            f"DELETE FROM methods WHERE class_id IN ({placeholders})", class_ids
        )
    cursor.execute("DELETE FROM classes WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM functions WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM imports WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM issues WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM usages WHERE file_id = ?", (file_id,))
    cursor.execute(
        "DELETE FROM dependencies WHERE source_file_id = ? OR target_file_id = ?",
        (file_id, file_id),
    )
    cursor.execute("DELETE FROM code_content WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM ast_trees WHERE file_id = ?", (file_id,))
    cursor.execute(
        "SELECT vector_id FROM code_chunks WHERE file_id = ? AND vector_id IS NOT NULL",
        (file_id,),
    )
    [row[0] for row in cursor.fetchall()]
    cursor.execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
    cursor.execute(
        "\n            SELECT id FROM classes WHERE file_id = ?\n            UNION\n            SELECT id FROM functions WHERE file_id = ?\n        ",
        (file_id, file_id),
    )
    entity_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        "DELETE FROM vector_index WHERE entity_type = 'file' AND entity_id = ?",
        (file_id,),
    )
    if entity_ids:
        placeholders = ",".join("?" * len(entity_ids))
        cursor.execute(
            f"\n                DELETE FROM vector_index\n                WHERE entity_type IN ('class', 'function', 'method')\n                AND entity_id IN ({placeholders})\n            ",
            entity_ids,
        )
    self.conn.commit()


async def remove_missing_files(
    self, project_id: str, root_path: Path
) -> Dict[str, Any]:
    """
    Remove files from database that no longer exist on disk.

    Args:
        project_id: Project ID (UUID4 string)
        root_path: Root directory path of the project

    Returns:
        Dictionary with removal statistics:
        - removed_count: Number of files removed
        - removed_files: List of removed file paths
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    files = self.get_project_files(project_id)
    removed_files = []
    removed_count = 0
    for file_record in files:
        file_path = Path(file_record["path"])
        if not file_path.exists():
            file_id = file_record["id"]
            logger.info(f"File not found on disk, removing from database: {file_path}")
            self.clear_file_data(file_id)
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            removed_files.append(str(file_path))
            removed_count += 1
    if removed_count > 0:
        self.conn.commit()
        logger.info(
            f"Removed {removed_count} missing files from database for project {project_id}"
        )
    return {"removed_count": removed_count, "removed_files": removed_files}


def get_file_summary(self, file_path: str, project_id: str) -> Optional[Dict[str, Any]]:
    """Get summary for a file."""
    file_id = self.get_file_id(file_path, project_id)
    if not file_id:
        return None
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    file_info = dict(cursor.fetchone())
    cursor.execute("SELECT COUNT(*) FROM classes WHERE file_id = ?", (file_id,))
    file_info["class_count"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM functions WHERE file_id = ?", (file_id,))
    file_info["function_count"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM issues WHERE file_id = ?", (file_id,))
    file_info["issue_count"] = cursor.fetchone()[0]
    return file_info


def get_files_needing_chunking(
    self, project_id: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get files that need chunking (have docstrings but no chunks).

    Files are considered needing chunking if:
    - They have docstrings (has_docstring = 1) OR
    - They have classes/functions/methods with docstrings
    - AND they have no chunks in code_chunks table

    Args:
        project_id: Project ID
        limit: Maximum number of files to return

    Returns:
        List of file records that need chunking
    """
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            "\n                SELECT DISTINCT f.id, f.project_id, f.path, f.has_docstring\n                FROM files f\n                WHERE f.project_id = ?\n                AND (\n                    f.has_docstring = 1\n                    OR EXISTS (\n                        SELECT 1 FROM classes c\n                        WHERE c.file_id = f.id AND c.docstring IS NOT NULL AND c.docstring != ''\n                    )\n                    OR EXISTS (\n                        SELECT 1 FROM functions fn\n                        WHERE fn.file_id = f.id AND fn.docstring IS NOT NULL AND fn.docstring != ''\n                    )\n                    OR EXISTS (\n                        SELECT 1 FROM methods m\n                        JOIN classes c ON m.class_id = c.id\n                        WHERE c.file_id = f.id AND m.docstring IS NOT NULL AND m.docstring != ''\n                    )\n                )\n                AND NOT EXISTS (\n                    SELECT 1 FROM code_chunks cc\n                    WHERE cc.file_id = f.id\n                )\n                ORDER BY f.updated_at DESC\n                LIMIT ?\n                ",
            (project_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
