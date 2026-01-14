"""
Code mapper commands for listing long files and errors.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Dict, List, Any, Optional

from ..core.constants import DEFAULT_MAX_FILE_LINES
from ..core.database_client.client import DatabaseClient

logger = logging.getLogger(__name__)


class ListLongFilesCommand:
    """
    Command to list files exceeding line limit.

    This is equivalent to old code_mapper functionality for finding oversized files.
    """

    def __init__(
        self,
        database: DatabaseClient,
        project_id: str,
        max_lines: int = DEFAULT_MAX_FILE_LINES,
    ):
        """
        Initialize command.

        Args:
            database: DatabaseClient instance
            project_id: Project UUID
            max_lines: Maximum lines threshold (default: 400)
        """
        self.database = database
        self.project_id = project_id
        self.max_lines = max_lines

    async def execute(self) -> Dict[str, Any]:
        """
        Execute command to list long files.

        Returns:
            Dictionary with:
            - files: List of files exceeding max_lines
            - count: Number of files
            - max_lines: Threshold used
        """
        try:
            # Get files exceeding line limit
            result = self.database.execute(
                """
                SELECT id, path, lines, last_modified, has_docstring
                FROM files
                WHERE project_id = ? 
                  AND lines > ?
                  AND (deleted = 0 OR deleted IS NULL)
                ORDER BY lines DESC
                """,
                (self.project_id, self.max_lines),
            )
            rows = result.get("data", [])

            files = []
            for row in rows:
                files.append(
                    {
                        "id": row["id"],
                        "path": row["path"],
                        "lines": row["lines"],
                        "last_modified": row["last_modified"],
                        "has_docstring": bool(row["has_docstring"]),
                    }
                )

            return {
                "files": files,
                "count": len(files),
                "max_lines": self.max_lines,
                "project_id": self.project_id,
            }
        except Exception as e:
            logger.exception(f"Error listing long files: {e}")
            raise


class ListErrorsByCategoryCommand:
    """
    Command to list errors grouped by category.

    This is equivalent to old code_mapper functionality for listing code issues.
    """

    def __init__(self, database: DatabaseClient, project_id: Optional[str] = None):
        """
        Initialize command.

        Args:
            database: DatabaseClient instance
            project_id: Optional project UUID (if None, returns all projects)
        """
        self.database = database
        self.project_id = project_id

    async def execute(self) -> Dict[str, Any]:
        """
        Execute command to list errors by category.

        Returns:
            Dictionary with:
            - categories: Dict mapping issue_type to list of issues
            - summary: Dict with counts per category
            - total: Total number of issues
        """
        try:
            # Get all issues grouped by type
            if self.project_id:
                result = self.database.execute(
                    """
                    SELECT i.issue_type, i.id, i.file_id, i.line, i.description, 
                           i.metadata, f.path as file_path
                    FROM issues i
                    LEFT JOIN files f ON i.file_id = f.id
                    WHERE i.project_id = ? OR f.project_id = ?
                    ORDER BY i.issue_type, f.path, i.line
                    """,
                    (self.project_id, self.project_id),
                )
            else:
                result = self.database.execute(
                    """
                    SELECT i.issue_type, i.id, i.file_id, i.line, i.description, 
                           i.metadata, f.path as file_path
                    FROM issues i
                    LEFT JOIN files f ON i.file_id = f.id
                    ORDER BY i.issue_type, f.path, i.line
                    """
                )
            rows = result.get("data", [])

            # Group by category
            categories: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                issue_type = row["issue_type"]
                if issue_type not in categories:
                    categories[issue_type] = []

                categories[issue_type].append(
                    {
                        "id": row["id"],
                        "file_id": row["file_id"],
                        "line": row["line"],
                        "description": row["description"],
                        "metadata": row["metadata"],
                        "file_path": row["file_path"],
                    }
                )

            # Create summary
            summary = {
                issue_type: len(issues) for issue_type, issues in categories.items()
            }
            total = sum(summary.values())

            return {
                "categories": categories,
                "summary": summary,
                "total": total,
                "project_id": self.project_id,
            }
        except Exception as e:
            logger.exception(f"Error listing errors by category: {e}")
            raise
