"""
Module statistics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Dict, Any


def get_statistics(self) -> Dict[str, Any]:
    """Get overall statistics."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    stats = {}
    cursor.execute("SELECT COUNT(*) FROM files")
    stats["total_files"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM classes")
    stats["total_classes"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM functions")
    stats["total_functions"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM methods")
    stats["total_methods"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM issues")
    stats["total_issues"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT issue_type) FROM issues")
    stats["issue_types"] = cursor.fetchone()[0]
    cursor.execute(
        "\n            SELECT issue_type, COUNT(*) as count\n            FROM issues\n            GROUP BY issue_type\n            ORDER BY count DESC\n        "
    )
    stats["issues_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}
    return stats
