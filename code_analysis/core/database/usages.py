"""
Module usages.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Dict, List, Any, Optional


def add_usage(
    self,
    file_id: int,
    line: int,
    usage_type: str,
    target_type: str,
    target_name: str,
    target_class: Optional[str] = None,
    context: Optional[str] = None,
) -> int:
    """
    Add usage record.

    Args:
        file_id: File ID where usage occurs
        line: Line number
        usage_type: Type of usage (method_call, attribute_access, etc.)
        target_type: Type of target (method, property, class, etc.)
        target_name: Name of target
        target_class: Class name if target is a method/property
        context: Additional context

    Returns:
        Usage ID
    """
    self._execute(
        "\n            INSERT INTO usages\n            (file_id, line, usage_type, target_type, target_class, target_name, context)\n            VALUES (?, ?, ?, ?, ?, ?, ?)\n        ",
        (file_id, line, usage_type, target_type, target_class, target_name, context),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def find_usages(
    self,
    target_name: str,
    project_id: str,
    target_type: Optional[str] = None,
    target_class: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find all usages of a method or property.

    Args:
        target_name: Name of method/property to find
        project_id: Project ID to filter by
        target_type: Type filter (method, property, etc.)
        target_class: Class name filter

    Returns:
        List of usage records with file paths
    """
    query = "\n            SELECT u.*, f.path as file_path\n            FROM usages u\n            JOIN files f ON u.file_id = f.id\n            WHERE u.target_name = ? AND f.project_id = ?\n        "
    params = [target_name, project_id]
    if target_type:
        query += " AND u.target_type = ?"
        params.append(target_type)
    if target_class:
        query += " AND u.target_class = ?"
        params.append(target_class)
    query += " ORDER BY f.path, u.line"
    return self._fetchall(query, tuple(params))
