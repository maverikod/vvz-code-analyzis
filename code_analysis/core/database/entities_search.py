"""
Entity search operations (classes, methods) for code analysis database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from typing import Any, Dict, List, Optional


def search_classes(
    self,
    name_pattern: Optional[str] = None,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search classes by name pattern.

    Args:
        name_pattern: Optional name pattern (SQL LIKE syntax, e.g., '%Manager')
        project_id: Optional project ID to filter by

    Returns:
        List of matching classes with file paths and metadata
    """
    query = """
        SELECT 
            c.id,
            c.name,
            c.line,
            c.docstring,
            c.bases,
            f.path as file_path,
            f.project_id
        FROM classes c
        JOIN files f ON c.file_id = f.id
        WHERE 1=1
    """
    params = []

    if project_id:
        query += " AND f.project_id = ?"
        params.append(project_id)

    if name_pattern:
        query += " AND c.name LIKE ?"
        params.append(name_pattern)

    query += " ORDER BY c.name"

    rows = self._fetchall(query, tuple(params))

    results = []
    for row in rows:
        bases = []
        if row["bases"]:
            try:
                bases = json.loads(row["bases"])
            except (json.JSONDecodeError, TypeError):
                bases = []

        results.append(
            {
                "id": row["id"],
                "name": row["name"],
                "line": row["line"],
                "docstring": row["docstring"],
                "bases": bases,
                "file_path": row["file_path"],
                "project_id": row["project_id"],
            }
        )

    return results


def search_methods(
    self,
    name_pattern: Optional[str] = None,
    class_name: Optional[str] = None,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search methods, optionally filtered by class name.

    Args:
        name_pattern: Optional method name pattern (SQL LIKE syntax)
        class_name: Optional class name to filter by (exact match)
        project_id: Optional project ID to filter by

    Returns:
        List of matching methods with class and file information
    """
    query = """
        SELECT 
            m.id,
            m.name,
            m.line,
            m.args,
            m.docstring,
            c.name as class_name,
            c.id as class_id,
            f.path as file_path,
            f.project_id
        FROM methods m
        JOIN classes c ON m.class_id = c.id
        JOIN files f ON c.file_id = f.id
        WHERE 1=1
    """
    params = []

    if project_id:
        query += " AND f.project_id = ?"
        params.append(project_id)

    if class_name:
        query += " AND c.name = ?"
        params.append(class_name)

    if name_pattern:
        query += " AND m.name LIKE ?"
        params.append(name_pattern)

    query += " ORDER BY c.name, m.line"

    rows = self._fetchall(query, tuple(params))

    results = []
    for row in rows:
        args = []
        if row["args"]:
            try:
                args = json.loads(row["args"])
            except (json.JSONDecodeError, TypeError):
                args = []

        results.append(
            {
                "id": row["id"],
                "name": row["name"],
                "line": row["line"],
                "args": args,
                "docstring": row["docstring"],
                "class_name": row["class_name"],
                "class_id": row["class_id"],
                "file_path": row["file_path"],
                "project_id": row["project_id"],
            }
        )

    return results
