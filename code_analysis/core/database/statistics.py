"""
Module statistics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Dict, Any


def get_statistics(self) -> Dict[str, Any]:
    """Get overall statistics."""
    stats = {}
    files_row = self._fetchone("SELECT COUNT(*) as count FROM files")
    stats["total_files"] = files_row["count"] if files_row else 0
    classes_row = self._fetchone("SELECT COUNT(*) as count FROM classes")
    stats["total_classes"] = classes_row["count"] if classes_row else 0
    functions_row = self._fetchone("SELECT COUNT(*) as count FROM functions")
    stats["total_functions"] = functions_row["count"] if functions_row else 0
    methods_row = self._fetchone("SELECT COUNT(*) as count FROM methods")
    stats["total_methods"] = methods_row["count"] if methods_row else 0
    issues_row = self._fetchone("SELECT COUNT(*) as count FROM issues")
    stats["total_issues"] = issues_row["count"] if issues_row else 0
    issue_types_row = self._fetchone("SELECT COUNT(DISTINCT issue_type) as count FROM issues")
    stats["issue_types"] = issue_types_row["count"] if issue_types_row else 0
    issues_by_type_rows = self._fetchall(
        "\n            SELECT issue_type, COUNT(*) as count\n            FROM issues\n            GROUP BY issue_type\n            ORDER BY count DESC\n        "
    )
    stats["issues_by_type"] = {row["issue_type"]: row["count"] for row in issues_by_type_rows}
    return stats
