"""
Module functions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from typing import Dict, List, Any, Optional


def add_function(
    self, file_id: int, name: str, line: int, args: List[str], docstring: Optional[str]
) -> int:
    """Add function record. Returns function_id."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    args_json = json.dumps(args) if args else None
    cursor.execute(
        "\n            INSERT OR REPLACE INTO functions (file_id, name, line, args, docstring)\n            VALUES (?, ?, ?, ?, ?)\n        ",
        (file_id, name, line, args_json, docstring),
    )
    self.conn.commit()
    result = cursor.lastrowid
    assert result is not None
    return result


def search_functions(
    self, name_pattern: Optional[str] = None, project_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search functions by name pattern.

    Args:
        name_pattern: Name pattern to search (optional)
        project_id: Project ID to filter by (optional)

    Returns:
        List of function records
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    if name_pattern:
        if project_id:
            cursor.execute(
                "\n                    SELECT func.*, f.path as file_path\n                    FROM functions func\n                    JOIN files f ON func.file_id = f.id\n                    WHERE func.name LIKE ? AND f.project_id = ?\n                    ORDER BY func.name, func.line\n                ",
                (f"%{name_pattern}%", project_id),
            )
        else:
            cursor.execute(
                "\n                    SELECT func.*, f.path as file_path\n                    FROM functions func\n                    JOIN files f ON func.file_id = f.id\n                    WHERE func.name LIKE ?\n                    ORDER BY func.name, func.line\n                ",
                (f"%{name_pattern}%",),
            )
    elif project_id:
        cursor.execute(
            "\n                    SELECT func.*, f.path as file_path\n                    FROM functions func\n                    JOIN files f ON func.file_id = f.id\n                    WHERE f.project_id = ?\n                    ORDER BY func.name, func.line\n                ",
            (project_id,),
        )
    else:
        cursor.execute(
            "\n                    SELECT func.*, f.path as file_path\n                    FROM functions func\n                    JOIN files f ON func.file_id = f.id\n                    ORDER BY func.name, func.line\n                "
        )
    return [dict(row) for row in cursor.fetchall()]
