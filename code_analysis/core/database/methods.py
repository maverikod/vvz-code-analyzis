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
    assert self.conn is not None
    cursor = self.conn.cursor()
    args_json = json.dumps(args) if args else None
    cursor.execute(
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
    self.conn.commit()
    result = cursor.lastrowid
    assert result is not None
    return result


def search_methods(
    self, name_pattern: Optional[str] = None, project_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search methods by name pattern."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    if name_pattern:
        if project_id:
            cursor.execute(
                "\n                    SELECT m.*, c.name as class_name, f.path as file_path\n                    FROM methods m\n                    JOIN classes c ON m.class_id = c.id\n                    JOIN files f ON c.file_id = f.id\n                    WHERE m.name LIKE ? AND f.project_id = ?\n                    ORDER BY c.name, m.name, m.line\n                ",
                (f"%{name_pattern}%", project_id),
            )
        else:
            cursor.execute(
                "\n                    SELECT m.*, c.name as class_name, f.path as file_path\n                    FROM methods m\n                    JOIN classes c ON m.class_id = c.id\n                    JOIN files f ON c.file_id = f.id\n                    WHERE m.name LIKE ?\n                    ORDER BY c.name, m.name, m.line\n                ",
                (f"%{name_pattern}%",),
            )
    elif project_id:
        cursor.execute(
            "\n                    SELECT m.*, c.name as class_name, f.path as file_path\n                    FROM methods m\n                    JOIN classes c ON m.class_id = c.id\n                    JOIN files f ON c.file_id = f.id\n                    WHERE f.project_id = ?\n                    ORDER BY c.name, m.name, m.line\n                ",
            (project_id,),
        )
    else:
        cursor.execute(
            "\n                    SELECT m.*, c.name as class_name, f.path as file_path\n                    FROM methods m\n                    JOIN classes c ON m.class_id = c.id\n                    JOIN files f ON c.file_id = f.id\n                    ORDER BY c.name, m.name, m.line\n                "
        )
    return [dict(row) for row in cursor.fetchall()]
