"""
Module issues.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from typing import Dict, List, Any, Optional


def add_issue(
    self,
    issue_type: str,
    description: str,
    line: Optional[int] = None,
    file_id: Optional[int] = None,
    class_id: Optional[int] = None,
    function_id: Optional[int] = None,
    method_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    project_id: Optional[str] = None,
) -> int:
    """
    Add issue record. Returns issue_id.

    If project_id is not provided, it will be retrieved from file_id.
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    if project_id is None and file_id is not None:
        cursor.execute("SELECT project_id FROM files WHERE id = ?", (file_id,))
        result = cursor.fetchone()
        if result:
            project_id = result[0]
    metadata_json = json.dumps(metadata) if metadata else None
    cursor.execute(
        "\n            INSERT INTO issues\n            (file_id, project_id, class_id, function_id, method_id, issue_type,\n             line, description, metadata)\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)\n        ",
        (
            file_id,
            project_id,
            class_id,
            function_id,
            method_id,
            issue_type,
            line,
            description,
            metadata_json,
        ),
    )
    self.conn.commit()
    result = cursor.lastrowid
    assert result is not None
    return result


def get_issues_by_type(
    self, issue_type: str, project_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all issues of a specific type."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    if project_id:
        cursor.execute(
            "\n                SELECT i.*, f.path as file_path\n                FROM issues i\n                LEFT JOIN files f ON i.file_id = f.id\n                WHERE i.issue_type = ? AND (f.project_id = ? OR f.project_id IS NULL)\n                ORDER BY f.path, i.line\n            ",
            (issue_type, project_id),
        )
    else:
        cursor.execute(
            "\n                SELECT i.*, f.path as file_path\n                FROM issues i\n                LEFT JOIN files f ON i.file_id = f.id\n                WHERE i.issue_type = ?\n                ORDER BY f.path, i.line\n            ",
            (issue_type,),
        )
    return [dict(row) for row in cursor.fetchall()]
