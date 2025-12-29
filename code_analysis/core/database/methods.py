"""
Module methods.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from typing import Dict, List, Any, Optional


def add_method(
    self,
    class_id: int,
    name: str,
    line: int,
    args: List[str],
    docstring: Optional[str],
    is_abstract: bool = False,
    has_pass: bool = False,
    has_not_implemented: bool = False,
) -> int:
    """Add method record. Returns method_id."""
    args_json = json.dumps(args) if args else None
    self._execute(
        "\n            INSERT OR REPLACE INTO methods\n            (class_id, name, line, args, docstring, is_abstract,\n             has_pass, has_not_implemented)\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?)\n        ",
        (
            class_id,
            name,
            line,
            args_json,
            docstring,
            is_abstract,
            has_pass,
            has_not_implemented,
        ),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def search_methods(
    self,
    name_pattern: Optional[str] = None,
    class_name: Optional[str] = None,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search methods by name pattern and/or class name.

    Args:
        name_pattern: Optional name pattern to search
        class_name: Optional class name to filter by
        project_id: Optional project ID to filter by

    Returns:
        List of matching methods
    """
    # Build query with filters
    query = """
        SELECT m.*, c.name as class_name, f.path as file_path
        FROM methods m
        JOIN classes c ON m.class_id = c.id
        JOIN files f ON c.file_id = f.id
        WHERE 1=1
    """
    params = []

    if name_pattern:
        query += " AND m.name LIKE ?"
        params.append(f"%{name_pattern}%")

    if class_name:
        query += " AND c.name = ?"
        params.append(class_name)

    if project_id:
        query += " AND f.project_id = ?"
        params.append(project_id)

    query += " ORDER BY c.name, m.name, m.line"

    return self._fetchall(query, tuple(params))
