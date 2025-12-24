"""
Command for getting imports information from files or project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class GetImportsCommand:
    """Command for getting imports information."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        file_path: Optional[str] = None,
        import_type: Optional[str] = None,  # "import", "import_from", or None for all
        module_name: Optional[str] = None,  # Filter by module name
        limit: Optional[int] = None,
        offset: int = 0,
    ):
        """
        Initialize get imports command.

        Args:
            database: Database instance
            project_id: Project UUID
            file_path: Optional file path to filter by (if None, lists all files in project)
            import_type: Type of import ("import", "import_from", or None for all)
            module_name: Optional module name to filter by
            limit: Optional limit on number of results
            offset: Offset for pagination
        """
        self.database = database
        self.project_id = project_id
        self.file_path = Path(file_path) if file_path else None
        self.import_type = import_type.lower() if import_type else None
        self.module_name = module_name
        self.limit = limit
        self.offset = offset

    async def execute(self) -> Dict[str, Any]:
        """
        Execute imports retrieval.

        Returns:
            Dictionary with list of imports and metadata
        """
        try:
            assert self.database.conn is not None
            cursor = self.database.conn.cursor()

            query = """
                SELECT i.id, i.name, i.module, i.import_type, i.line, i.file_id,
                       f.path as file_path
                FROM imports i
                JOIN files f ON i.file_id = f.id
                WHERE f.project_id = ?
            """
            params = [self.project_id]

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

            if self.import_type:
                query += " AND i.import_type = ?"
                params.append(self.import_type)

            if self.module_name:
                query += " AND (i.module = ? OR i.module LIKE ?)"
                params.append(self.module_name)
                params.append(f"%{self.module_name}%")

            query += " ORDER BY f.path, i.line"

            if self.limit:
                query += " LIMIT ?"
                params.append(self.limit)
                if self.offset:
                    query += " OFFSET ?"
                    params.append(self.offset)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            imports = []
            for row in rows:
                imports.append({
                    "id": row["id"],
                    "name": row["name"],
                    "module": row["module"],
                    "import_type": row["import_type"],
                    "line": row["line"],
                    "file_id": row["file_id"],
                    "file_path": row["file_path"],
                })

            # Get total count
            count_query = """
                SELECT COUNT(*) as total
                FROM imports i
                JOIN files f ON i.file_id = f.id
                WHERE f.project_id = ?
            """
            count_params = [self.project_id]

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

            if self.import_type:
                count_query += " AND i.import_type = ?"
                count_params.append(self.import_type)

            if self.module_name:
                count_query += " AND (i.module = ? OR i.module LIKE ?)"
                count_params.append(self.module_name)
                count_params.append(f"%{self.module_name}%")

            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()["total"]

            # Group by file for summary
            file_summary = {}
            for imp in imports:
                file_path = imp["file_path"]
                if file_path not in file_summary:
                    file_summary[file_path] = {
                        "file_path": file_path,
                        "import_count": 0,
                        "import_types": {},
                    }
                file_summary[file_path]["import_count"] += 1
                imp_type = imp["import_type"]
                file_summary[file_path]["import_types"][imp_type] = (
                    file_summary[file_path]["import_types"].get(imp_type, 0) + 1
                )

            return {
                "success": True,
                "message": f"Found {len(imports)} imports",
                "total": total_count,
                "limit": self.limit,
                "offset": self.offset,
                "imports": imports,
                "file_summary": list(file_summary.values()),
            }

        except Exception as e:
            logger.error(f"Error getting imports: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error getting imports: {e}",
                "error": str(e),
            }

