"""
Module classes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from typing import Dict, List, Any, Optional


def add_class(
    self, file_id: int, name: str, line: int, docstring: Optional[str], bases: List[str]
) -> int:
    """Add class record. Returns class_id."""
    cursor = self.conn.cursor()
    bases_json = json.dumps(bases) if bases else None
    cursor.execute(
        "\n            INSERT OR REPLACE INTO classes (file_id, name, line, docstring, bases)\n            VALUES (?, ?, ?, ?, ?)\n        ",
        (file_id, name, line, docstring, bases_json),
    )
    self.conn.commit()
    return cursor.lastrowid


def get_class_id(self, file_id: int, name: str, line: int) -> Optional[int]:
    """Get class ID."""
    cursor = self.conn.cursor()
    cursor.execute(
        "SELECT id FROM classes WHERE file_id = ? AND name = ? AND line = ?",
        (file_id, name, line),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def search_classes(
    self, name_pattern: Optional[str] = None, project_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search classes by name pattern."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    if name_pattern:
        if project_id:
            cursor.execute(
                "\n                    SELECT c.*, f.path as file_path\n                    FROM classes c\n                    JOIN files f ON c.file_id = f.id\n                    WHERE c.name LIKE ? AND f.project_id = ?\n                    ORDER BY c.name, c.line\n                ",
                (f"%{name_pattern}%", project_id),
            )
        else:
            cursor.execute(
                "\n                    SELECT c.*, f.path as file_path\n                    FROM classes c\n                    JOIN files f ON c.file_id = f.id\n                    WHERE c.name LIKE ?\n                    ORDER BY c.name, c.line\n                ",
                (f"%{name_pattern}%",),
            )
    elif project_id:
        cursor.execute(
            "\n                    SELECT c.*, f.path as file_path\n                    FROM classes c\n                    JOIN files f ON c.file_id = f.id\n                    WHERE f.project_id = ?\n                    ORDER BY c.name, c.line\n                ",
            (project_id,),
        )
    else:
        cursor.execute(
            "\n                    SELECT c.*, f.path as file_path\n                    FROM classes c\n                    JOIN files f ON c.file_id = f.id\n                    ORDER BY c.name, c.line\n                "
        )
    return [dict(row) for row in cursor.fetchall()]
