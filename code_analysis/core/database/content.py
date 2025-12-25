"""
Module content.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Dict, List, Any, Optional


def add_code_content(
    self,
    file_id: int,
    entity_type: str,
    entity_name: str,
    content: str,
    docstring: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> int:
    """
    Add code content for full-text search.

    Args:
        file_id: File ID
        entity_type: Type (class, method, function)
        entity_name: Name of entity
        content: Code content
        docstring: Docstring if available
        entity_id: ID of related entity (class_id, method_id, etc.)

    Returns:
        Content ID
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        "\n            INSERT INTO code_content\n            (file_id, entity_type, entity_id, entity_name, content, docstring)\n            VALUES (?, ?, ?, ?, ?, ?)\n        ",
        (file_id, entity_type, entity_id, entity_name, content, docstring),
    )
    self.conn.commit()
    content_id = cursor.lastrowid
    assert content_id is not None
    cursor.execute(
        "\n            INSERT INTO code_content_fts\n            (rowid, entity_type, entity_name, content, docstring)\n            VALUES (?, ?, ?, ?, ?)\n        ",
        (content_id, entity_type, entity_name, content, docstring or ""),
    )
    self.conn.commit()
    return content_id


def full_text_search(
    self,
    query: str,
    project_id: str,
    entity_type: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Perform full-text search in code content.

    Args:
        query: Search query
        project_id: Project ID to filter by
        entity_type: Filter by entity type
        limit: Maximum results

    Returns:
        List of matching records with file paths
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    fts_query = "\n            SELECT c.*, f.path as file_path\n            FROM code_content_fts fts\n            JOIN code_content c ON fts.rowid = c.id\n            JOIN files f ON c.file_id = f.id\n            WHERE code_content_fts MATCH ? AND f.project_id = ?\n        "
    params = [query, project_id]
    if entity_type:
        fts_query += " AND c.entity_type = ?"
        params.append(entity_type)
    fts_query += " ORDER BY rank LIMIT ?"
    params.append(limit)
    cursor.execute(fts_query, params)
    return [dict(row) for row in cursor.fetchall()]
