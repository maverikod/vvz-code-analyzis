"""
Module duplicates - database operations for code duplicates.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Dict, List, Any, Optional


def add_duplicate(
    self,
    project_id: str,
    duplicate_hash: str,
    similarity: float,
) -> int:
    """Add duplicate group record. Returns duplicate_id.

    Args:
        project_id: Project ID.
        duplicate_hash: Hash of normalized code.
        similarity: Similarity score (0.0-1.0).

    Returns:
        Duplicate ID.
    """
    self._execute(
        """
            INSERT OR REPLACE INTO code_duplicates
            (project_id, duplicate_hash, similarity)
            VALUES (?, ?, ?)
        """,
        (project_id, duplicate_hash, similarity),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def add_duplicate_occurrence(
    self,
    duplicate_id: int,
    file_id: int,
    start_line: int,
    end_line: int,
    code_snippet: Optional[str] = None,
    ast_node_id: Optional[int] = None,
) -> int:
    """Add duplicate occurrence record. Returns occurrence_id.

    Args:
        duplicate_id: Duplicate group ID.
        file_id: File ID.
        start_line: Start line number.
        end_line: End line number.
        code_snippet: Optional code snippet.
        ast_node_id: Optional AST node ID.

    Returns:
        Occurrence ID.
    """
    self._execute(
        """
            INSERT OR REPLACE INTO duplicate_occurrences
            (duplicate_id, file_id, start_line, end_line, code_snippet, ast_node_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
        (duplicate_id, file_id, start_line, end_line, code_snippet, ast_node_id),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def get_duplicates_for_project(self, project_id: str) -> List[Dict[str, Any]]:
    """
    Get all duplicate groups for a project.

    Args:
        project_id: Project ID.

    Returns:
        List of duplicate groups with occurrences.
    """
    duplicates = self._fetchall(
        """
            SELECT d.*, COUNT(do.id) as occurrence_count
            FROM code_duplicates d
            LEFT JOIN duplicate_occurrences do ON d.id = do.duplicate_id
            WHERE d.project_id = ?
            GROUP BY d.id
            HAVING occurrence_count > 1
            ORDER BY d.similarity DESC, occurrence_count DESC
        """,
        (project_id,),
    )

    result = []
    for dup in duplicates:
        occurrences = self._fetchall(
            """
                SELECT do.*, f.path as file_path
                FROM duplicate_occurrences do
                JOIN files f ON do.file_id = f.id
                WHERE do.duplicate_id = ?
                ORDER BY f.path, do.start_line
            """,
            (dup["id"],),
        )

        result.append(
            {
                "id": dup["id"],
                "hash": dup["duplicate_hash"],
                "similarity": dup["similarity"],
                "occurrence_count": dup["occurrence_count"],
                "occurrences": occurrences,
            }
        )

    return result


def get_duplicates_for_file(self, file_id: int) -> List[Dict[str, Any]]:
    """
    Get all duplicate groups for a specific file.

    Args:
        file_id: File ID.

    Returns:
        List of duplicate groups.
    """
    return self._fetchall(
        """
            SELECT DISTINCT d.*
            FROM code_duplicates d
            JOIN duplicate_occurrences do ON d.id = do.duplicate_id
            WHERE do.file_id = ?
            ORDER BY d.similarity DESC
        """,
        (file_id,),
    )


def delete_duplicates_for_project(self, project_id: str) -> None:
    """
    Delete all duplicates for a project.

    Args:
        project_id: Project ID.
    """
    # Delete occurrences first (foreign key constraint)
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
    self._commit()
