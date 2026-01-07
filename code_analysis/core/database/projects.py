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
    row = self._fetchone("SELECT id FROM projects WHERE root_path = ?", (root_path,))
    if row:
        return row["id"]
    project_id = str(uuid.uuid4())
    project_name = name or Path(root_path).name
    self._execute(
        "\n                INSERT INTO projects (id, root_path, name, comment, updated_at)\n                VALUES (?, ?, ?, ?, julianday('now'))\n            ",
        (project_id, root_path, project_name, comment),
    )
    self._commit()
    return project_id


def get_project_id(self, root_path: str) -> Optional[str]:
    """
    Get project ID by root path.

    Args:
        root_path: Root directory path of the project

    Returns:
        Project ID (UUID4 string) or None if not found
    """
    row = self._fetchone("SELECT id FROM projects WHERE root_path = ?", (root_path,))
    return row["id"] if row else None


def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get project by ID.

    Args:
        project_id: Project ID (UUID4 string)

    Returns:
        Project record as dictionary or None if not found
    """
    return self._fetchone("SELECT * FROM projects WHERE id = ?", (project_id,))


async def clear_project_data(self, project_id: str) -> None:
    """
    Clear all data for a project and remove the project itself.

    Removes all files, classes, functions, imports, issues, usages,
    dependencies, code_content, ast_trees, code_chunks, vector_index entries,
    code_duplicates, duplicate_occurrences, datasets, and the project record itself.

    Args:
        project_id: Project ID (UUID4 string)
    """
    file_rows = self._fetchall("SELECT id FROM files WHERE project_id = ?", (project_id,))
    file_ids = [row["id"] for row in file_rows]
    
    # Delete duplicates first (before files)
    try:
        # Delete duplicate occurrences first (foreign key constraint)
        self._execute(
            """
            DELETE FROM duplicate_occurrences
            WHERE duplicate_id IN (
                SELECT id FROM code_duplicates WHERE project_id = ?
            )
            """,
            (project_id,),
        )
        # Delete duplicate groups
        self._execute(
            "DELETE FROM code_duplicates WHERE project_id = ?",
            (project_id,),
        )
    except Exception as e:
        logger.warning(f"Failed to delete duplicates for project {project_id}: {e}")
    
    if not file_ids:
        # Delete datasets and vector_index even if no files
        self._execute("DELETE FROM datasets WHERE project_id = ?", (project_id,))
        self._execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,))
        self._execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._commit()
        logger.info(f"Cleared all data and removed project {project_id} (no files)")
        return
    
    placeholders = ",".join("?" * len(file_ids))
    class_rows = self._fetchall(
        f"SELECT id FROM classes WHERE file_id IN ({placeholders})", tuple(file_ids)
    )
    class_ids = [row["id"] for row in class_rows]
    content_rows = self._fetchall(
        f"SELECT id FROM code_content WHERE file_id IN ({placeholders})", tuple(file_ids)
    )
    content_ids = [row["id"] for row in content_rows]
    # Delete FTS entries in batches to avoid database corruption
    # If FTS is corrupted, skip it and continue with other deletions
    if content_ids:
        batch_size = 1000
        for i in range(0, len(content_ids), batch_size):
            batch = content_ids[i:i + batch_size]
            batch_placeholders = ",".join("?" * len(batch))
            try:
                self._execute(
                    f"DELETE FROM code_content_fts WHERE rowid IN ({batch_placeholders})",
                    tuple(batch),
                )
            except Exception as e:
                logger.warning(f"Failed to delete FTS batch {i//batch_size + 1} for project {project_id}: {e}. Skipping FTS deletion.")
                # If FTS is corrupted, skip remaining batches
                break
    if class_ids:
        method_placeholders = ",".join("?" * len(class_ids))
        self._execute(
            f"DELETE FROM methods WHERE class_id IN ({method_placeholders})", tuple(class_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM classes WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM functions WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM imports WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM issues WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"\n                DELETE FROM dependencies \n                WHERE source_file_id IN ({placeholders}) \n                OR target_file_id IN ({placeholders})\n            ",
            tuple(file_ids + file_ids),
        )
    if file_ids:
        self._execute(
            f"DELETE FROM code_content WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM ast_trees WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    if file_ids:
        self._execute(
            f"DELETE FROM code_chunks WHERE file_id IN ({placeholders})", tuple(file_ids)
        )
    
    # Delete datasets (CASCADE should handle files, but explicit is better)
    self._execute("DELETE FROM datasets WHERE project_id = ?", (project_id,))
    self._execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,))
    self._execute("DELETE FROM files WHERE project_id = ?", (project_id,))
    self._execute("DELETE FROM projects WHERE id = ?", (project_id,))
    self._commit()
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
    if include_deleted:
        rows = self._fetchall(
            "SELECT id, path, lines, last_modified, has_docstring, deleted FROM files WHERE project_id = ?",
            (project_id,),
        )
    else:
        rows = self._fetchall(
            "SELECT id, path, lines, last_modified, has_docstring, deleted FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )
    result = []
    for row in rows:
        result.append(
            {
                "id": row["id"],
                "path": row["path"],
                "lines": row["lines"],
                "last_modified": row["last_modified"],
                "has_docstring": row["has_docstring"],
                "deleted": row.get("deleted", 0),
            }
        )
    return result
