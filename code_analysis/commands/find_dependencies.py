"""
Command for finding dependencies - where classes, functions, or modules are used.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class FindDependenciesCommand:
    """Command for finding dependencies."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        entity_name: str,
        entity_type: Optional[
            str
        ] = None,  # "class", "function", "method", "module", or None for all
        target_class: Optional[str] = None,  # For methods, filter by class
        limit: Optional[int] = None,
        offset: int = 0,
    ):
        """
        Initialize find dependencies command.

        Args:
            database: Database instance
            project_id: Project UUID
            entity_name: Name of entity to find dependencies for
            entity_type: Type of entity ("class", "function", "method", "module", or None for all)
            target_class: Optional class name for methods
            limit: Optional limit on number of results
            offset: Offset for pagination
        """
        self.database = database
        self.project_id = project_id
        self.entity_name = entity_name
        self.entity_type = entity_type.lower() if entity_type else None
        self.target_class = target_class
        self.limit = limit
        self.offset = offset

    async def execute(self) -> Dict[str, Any]:
        """
        Execute dependency search.

        Returns:
            Dictionary with list of dependencies and metadata
        """
        try:
            results = []

            # Search in usages table (for methods, properties, classes)
            if self.entity_type in (None, "method", "function", "class"):
                usage_results = await self._find_in_usages()
                results.extend(usage_results)

            # Search in imports table (for modules)
            if self.entity_type in (None, "module"):
                import_results = await self._find_in_imports()
                results.extend(import_results)

            # Remove duplicates and sort
            seen = set()
            unique_results = []
            for result in results:
                key = (result["file_path"], result["line"], result["source"])
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)

            unique_results.sort(key=lambda x: (x["file_path"], x["line"]))

            # Apply pagination
            total = len(unique_results)
            if self.limit:
                unique_results = unique_results[self.offset : self.offset + self.limit]
            elif self.offset:
                unique_results = unique_results[self.offset :]

            # Group by file
            file_groups = {}
            for result in unique_results:
                file_path = result["file_path"]
                if file_path not in file_groups:
                    file_groups[file_path] = {
                        "file_path": file_path,
                        "file_id": result.get("file_id"),
                        "usages": [],
                    }
                file_groups[file_path]["usages"].append(
                    {
                        "line": result["line"],
                        "source": result["source"],
                        "usage_type": result.get("usage_type"),
                        "context": result.get("context"),
                    }
                )

            return {
                "success": True,
                "message": f"Found {len(unique_results)} dependencies for '{self.entity_name}'",
                "entity_name": self.entity_name,
                "entity_type": self.entity_type or "all",
                "total": total,
                "limit": self.limit,
                "offset": self.offset,
                "dependencies": list(file_groups.values()),
            }

        except Exception as e:
            logger.error(f"Error finding dependencies: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error finding dependencies: {e}",
                "error": str(e),
            }

    async def _find_in_usages(self) -> List[Dict[str, Any]]:
        """Find dependencies in usages table."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        query = """
            SELECT u.id, u.file_id, u.line, u.usage_type, u.target_type,
                   u.target_class, u.target_name, u.context, f.path as file_path
            FROM usages u
            JOIN files f ON u.file_id = f.id
            WHERE u.target_name = ? AND f.project_id = ?
        """
        params = [self.entity_name, self.project_id]

        if self.entity_type == "method":
            query += " AND u.target_type = 'method'"
        elif self.entity_type == "function":
            query += " AND u.target_type = 'function'"
        elif self.entity_type == "class":
            query += " AND u.target_type = 'class'"

        if self.target_class:
            query += " AND u.target_class = ?"
            params.append(self.target_class)

        query += " ORDER BY f.path, u.line"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "file_id": row["file_id"],
                    "file_path": row["file_path"],
                    "line": row["line"],
                    "source": "usage",
                    "usage_type": row["usage_type"],
                    "target_type": row["target_type"],
                    "target_class": row["target_class"],
                    "context": row["context"],
                }
            )

        return results

    async def _find_in_imports(self) -> List[Dict[str, Any]]:
        """Find dependencies in imports table."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        # Search by module name or import name
        query = """
            SELECT i.id, i.file_id, i.line, i.name, i.module, i.import_type, f.path as file_path
            FROM imports i
            JOIN files f ON i.file_id = f.id
            WHERE f.project_id = ? AND (i.name = ? OR i.module = ? OR i.module LIKE ?)
        """
        params = [
            self.project_id,
            self.entity_name,
            self.entity_name,
            f"%{self.entity_name}%",
        ]

        query += " ORDER BY f.path, i.line"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "file_id": row["file_id"],
                    "file_path": row["file_path"],
                    "line": row["line"],
                    "source": "import",
                    "import_type": row["import_type"],
                    "name": row["name"],
                    "module": row["module"],
                }
            )

        return results
