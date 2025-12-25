"""
Command for finding usages of methods, properties, classes, or functions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class FindUsagesCommand:
    """Command for finding usages."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        target_name: str,
        target_type: Optional[
            str
        ] = None,  # "method", "property", "class", "function", or None for all
        target_class: Optional[str] = None,  # For methods/properties, filter by class
        file_path: Optional[str] = None,  # Filter by file where usage occurs
        limit: Optional[int] = None,
        offset: int = 0,
    ):
        """
        Initialize find usages command.

        Args:
            database: Database instance
            project_id: Project UUID
            target_name: Name of target to find usages for
            target_type: Type of target ("method", "property", "class", "function", or None for all)
            target_class: Optional class name for methods/properties
            file_path: Optional file path to filter by (where usage occurs)
            limit: Optional limit on number of results
            offset: Offset for pagination
        """
        self.database = database
        self.project_id = project_id
        self.target_name = target_name
        self.target_type = target_type.lower() if target_type else None
        self.target_class = target_class
        self.file_path = Path(file_path) if file_path else None
        self.limit = limit
        self.offset = offset

    async def execute(self) -> Dict[str, Any]:
        """
        Execute usage search.

        Returns:
            Dictionary with list of usages and metadata
        """
        try:
            assert self.database.conn is not None
            cursor = self.database.conn.cursor()

            query = """
                SELECT u.id, u.file_id, u.line, u.usage_type, u.target_type,
                       u.target_class, u.target_name, u.context, f.path as file_path
                FROM usages u
                JOIN files f ON u.file_id = f.id
                WHERE u.target_name = ? AND f.project_id = ?
            """
            params = [self.target_name, self.project_id]

            if self.target_type:
                query += " AND u.target_type = ?"
                params.append(self.target_type)

            if self.target_class:
                query += " AND u.target_class = ?"
                params.append(self.target_class)

            if self.file_path:
                file_path_str = str(self.file_path)
                if not self.file_path.is_absolute():
                    query += " AND (f.path = ? OR f.path = ?)"
                    params.append(file_path_str)
                    project = self.database.get_project(self.project_id)
                    if project:
                        project_root = Path(project["root_path"])
                        absolute_path = str((project_root / self.file_path).resolve())
                        params.append(absolute_path)
                    else:
                        params.append(file_path_str)
                else:
                    query += " AND (f.path = ? OR f.path = ?)"
                    params.append(file_path_str)
                    params.append(self.file_path.name)

            query += " ORDER BY f.path, u.line"

            if self.limit:
                query += " LIMIT ?"
                params.append(self.limit)
                if self.offset:
                    query += " OFFSET ?"
                    params.append(self.offset)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            usages = []
            for row in rows:
                usages.append(
                    {
                        "id": row["id"],
                        "file_id": row["file_id"],
                        "file_path": row["file_path"],
                        "line": row["line"],
                        "usage_type": row["usage_type"],
                        "target_type": row["target_type"],
                        "target_class": row["target_class"],
                        "target_name": row["target_name"],
                        "context": row["context"],
                    }
                )

            # Get total count
            count_query = """
                SELECT COUNT(*) as total
                FROM usages u
                JOIN files f ON u.file_id = f.id
                WHERE u.target_name = ? AND f.project_id = ?
            """
            count_params = [self.target_name, self.project_id]

            if self.target_type:
                count_query += " AND u.target_type = ?"
                count_params.append(self.target_type)

            if self.target_class:
                count_query += " AND u.target_class = ?"
                count_params.append(self.target_class)

            if self.file_path:
                file_path_str = str(self.file_path)
                if not self.file_path.is_absolute():
                    count_query += " AND (f.path = ? OR f.path = ?)"
                    count_params.append(file_path_str)
                    project = self.database.get_project(self.project_id)
                    if project:
                        project_root = Path(project["root_path"])
                        absolute_path = str((project_root / self.file_path).resolve())
                        count_params.append(absolute_path)
                    else:
                        count_params.append(file_path_str)
                else:
                    count_query += " AND (f.path = ? OR f.path = ?)"
                    count_params.append(file_path_str)
                    count_params.append(self.file_path.name)

            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()["total"]

            # Group by file
            file_groups = {}
            for usage in usages:
                file_path = usage["file_path"]
                if file_path not in file_groups:
                    file_groups[file_path] = {
                        "file_path": file_path,
                        "file_id": usage["file_id"],
                        "usages": [],
                    }
                file_groups[file_path]["usages"].append(
                    {
                        "line": usage["line"],
                        "usage_type": usage["usage_type"],
                        "target_type": usage["target_type"],
                        "target_class": usage["target_class"],
                        "context": usage["context"],
                    }
                )

            return {
                "success": True,
                "message": f"Found {len(usages)} usages for '{self.target_name}'",
                "target_name": self.target_name,
                "target_type": self.target_type or "all",
                "target_class": self.target_class,
                "total": total_count,
                "limit": self.limit,
                "offset": self.offset,
                "usages": list(file_groups.values()),
            }

        except Exception as e:
            logger.error(f"Error finding usages: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error finding usages: {e}",
                "error": str(e),
            }
