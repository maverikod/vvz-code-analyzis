"""
Module projects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def get_or_create_project(
    self, root_path: str, name: Optional[str] = None, comment: Optional[str] = None
) -> str:
    """
    Get or create project by root path.

    Args:
        root_path: Root directory path of the project
        name: Optional project name
        comment: Optional human-readable comment/identifier

    Returns:
        Project ID (UUID4 string)
    """
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE root_path = ?", (root_path,))
        row = cursor.fetchone()
        if row:
            return row[0]
        project_id = str(uuid.uuid4())
        project_name = name or Path(root_path).name
        cursor.execute(
            "\n                INSERT INTO projects (id, root_path, name, comment, updated_at)\n                VALUES (?, ?, ?, ?, julianday('now'))\n            ",
            (project_id, root_path, project_name, comment),
        )
        self.conn.commit()
        return project_id


def get_project_id(self, root_path: str) -> Optional[str]:
    """
    Get project ID by root path.

    Args:
        root_path: Root directory path of the project

    Returns:
        Project ID (UUID4 string) or None if not found
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT id FROM projects WHERE root_path = ?", (root_path,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get project by ID.

    Args:
        project_id: Project ID (UUID4 string)

    Returns:
        Project record as dictionary or None if not found
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


async def clear_project_data(self, project_id: str) -> None:
    """
    Clear all data for a project and remove the project itself.

    Removes all files, classes, functions, imports, issues, usages,
    dependencies, code_content, ast_trees, code_chunks, vector_index entries,
    and the project record itself from the database.

    Args:
        project_id: Project ID (UUID4 string)
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT id FROM files WHERE project_id = ?", (project_id,))
    file_ids = [row[0] for row in cursor.fetchall()]
    if not file_ids:
        cursor.execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,))
        self.conn.commit()
        return
    placeholders = ",".join("?" * len(file_ids))
    cursor.execute(
        f"SELECT id FROM classes WHERE file_id IN ({placeholders})", file_ids
    )
    class_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        f"SELECT id FROM code_content WHERE file_id IN ({placeholders})", file_ids
    )
    content_ids = [row[0] for row in cursor.fetchall()]
    if content_ids:
        content_placeholders = ",".join("?" * len(content_ids))
        cursor.execute(
            f"DELETE FROM code_content_fts WHERE rowid IN ({content_placeholders})",
            content_ids,
        )
    if class_ids:
        method_placeholders = ",".join("?" * len(class_ids))
        cursor.execute(
            f"DELETE FROM methods WHERE class_id IN ({method_placeholders})", class_ids
        )
    if file_ids:
        cursor.execute(
            f"DELETE FROM classes WHERE file_id IN ({placeholders})", file_ids
        )
    if file_ids:
        cursor.execute(
            f"DELETE FROM functions WHERE file_id IN ({placeholders})", file_ids
        )
    if file_ids:
        cursor.execute(
            f"DELETE FROM imports WHERE file_id IN ({placeholders})", file_ids
        )
    if file_ids:
        cursor.execute(
            f"DELETE FROM issues WHERE file_id IN ({placeholders})", file_ids
        )
    if file_ids:
        cursor.execute(
            f"DELETE FROM usages WHERE file_id IN ({placeholders})", file_ids
        )
    if file_ids:
        cursor.execute(
            f"\n                DELETE FROM dependencies \n                WHERE source_file_id IN ({placeholders}) \n                OR target_file_id IN ({placeholders})\n            ",
            file_ids + file_ids,
        )
    if file_ids:
        cursor.execute(
            f"DELETE FROM code_content WHERE file_id IN ({placeholders})", file_ids
        )
    if file_ids:
        cursor.execute(
            f"DELETE FROM ast_trees WHERE file_id IN ({placeholders})", file_ids
        )
    if file_ids:
        cursor.execute(
            f"DELETE FROM code_chunks WHERE file_id IN ({placeholders})", file_ids
        )
    cursor.execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,))
    cursor.execute("DELETE FROM files WHERE project_id = ?", (project_id,))
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    self.conn.commit()
    logger.info(f"Cleared all data and removed project {project_id}")


def get_project_files(
    self, project_id: str, include_deleted: bool = False
) -> List[Dict[str, Any]]:
    """
    Get all files for a project.

    Args:
        project_id: Project ID (UUID4 string)
        include_deleted: If True, include files marked as deleted (default: False)

    Returns:
        List of file records as dictionaries
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    if include_deleted:
        cursor.execute(
            "SELECT id, path, lines, last_modified, has_docstring, deleted FROM files WHERE project_id = ?",
            (project_id,),
        )
    else:
        cursor.execute(
            "SELECT id, path, lines, last_modified, has_docstring, deleted FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )
    rows = cursor.fetchall()
    result = []
    for row in rows:
        result.append(
            {
                "id": row[0],
                "path": row[1],
                "lines": row[2],
                "last_modified": row[3],
                "has_docstring": row[4],
                "deleted": row[5] if len(row) > 5 else 0,
            }
        )
    return result
