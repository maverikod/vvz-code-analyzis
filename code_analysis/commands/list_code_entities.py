"""
Command for listing code entities (classes, functions, methods) in a file or project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class ListCodeEntitiesCommand:
    """Command for listing code entities in a file or project."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        entity_type: Optional[
            str
        ] = None,  # "class", "function", "method", or None for all
        file_path: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ):
        """
        Initialize list code entities command.

        Args:
            database: Database instance
            project_id: Project UUID
            entity_type: Type of entity to list ("class", "function", "method", or None for all)
            file_path: Optional file path to filter by (if None, lists all files in project)
            limit: Optional limit on number of results
            offset: Offset for pagination
        """
        self.database = database
        self.project_id = project_id
        self.entity_type = entity_type.lower() if entity_type else None
        self.file_path = Path(file_path) if file_path else None
        self.limit = limit
        self.offset = offset

    async def execute(self) -> Dict[str, Any]:
        """
        Execute entity listing.

        Returns:
            Dictionary with list of entities and metadata
        """
        try:
            if self.entity_type == "class":
                return await self._list_classes()
            elif self.entity_type == "function":
                return await self._list_functions()
            elif self.entity_type == "method":
                return await self._list_methods()
            elif self.entity_type is None:
                return await self._list_all()
            else:
                return {
                    "success": False,
                    "message": f"Unknown entity type: {self.entity_type}. Must be 'class', 'function', 'method', or None for all",
                }
        except Exception as e:
            logger.error(f"Error listing code entities: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error listing code entities: {e}",
                "error": str(e),
            }

    async def _list_classes(self) -> Dict[str, Any]:
        """List all classes."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        query = """
            SELECT c.id, c.name, c.line, c.docstring, c.bases, c.file_id,
                   f.path as file_path
            FROM classes c
            JOIN files f ON c.file_id = f.id
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

        query += " ORDER BY f.path, c.line"

        if self.limit:
            query += " LIMIT ?"
            params.append(self.limit)
            if self.offset:
                query += " OFFSET ?"
                params.append(self.offset)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        classes = []
        for row in rows:
            bases = json.loads(row["bases"]) if row["bases"] else []
            classes.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "line": row["line"],
                    "docstring": row["docstring"],
                    "bases": bases,
                    "file_id": row["file_id"],
                    "file_path": row["file_path"],
                }
            )

        # Get total count
        count_query = "SELECT COUNT(*) as total FROM classes c JOIN files f ON c.file_id = f.id WHERE f.project_id = ?"
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

        cursor.execute(count_query, count_params)
        total_count = cursor.fetchone()["total"]

        return {
            "success": True,
            "message": f"Found {len(classes)} classes",
            "entity_type": "class",
            "total": total_count,
            "limit": self.limit,
            "offset": self.offset,
            "entities": classes,
        }

    async def _list_functions(self) -> Dict[str, Any]:
        """List all functions."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        query = """
            SELECT func.id, func.name, func.line, func.args, func.docstring, func.file_id,
                   f.path as file_path
            FROM functions func
            JOIN files f ON func.file_id = f.id
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

        query += " ORDER BY f.path, func.line"

        if self.limit:
            query += " LIMIT ?"
            params.append(self.limit)
            if self.offset:
                query += " OFFSET ?"
                params.append(self.offset)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        functions = []
        for row in rows:
            args = json.loads(row["args"]) if row["args"] else []
            functions.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "line": row["line"],
                    "args": args,
                    "docstring": row["docstring"],
                    "file_id": row["file_id"],
                    "file_path": row["file_path"],
                }
            )

        # Get total count
        count_query = "SELECT COUNT(*) as total FROM functions func JOIN files f ON func.file_id = f.id WHERE f.project_id = ?"
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

        cursor.execute(count_query, count_params)
        total_count = cursor.fetchone()["total"]

        return {
            "success": True,
            "message": f"Found {len(functions)} functions",
            "entity_type": "function",
            "total": total_count,
            "limit": self.limit,
            "offset": self.offset,
            "entities": functions,
        }

    async def _list_methods(self) -> Dict[str, Any]:
        """List all methods."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        query = """
            SELECT m.id, m.name, m.line, m.args, m.docstring, m.is_abstract,
                   m.has_pass, m.has_not_implemented, m.class_id,
                   c.name as class_name, c.line as class_line,
                   f.id as file_id, f.path as file_path
            FROM methods m
            JOIN classes c ON m.class_id = c.id
            JOIN files f ON c.file_id = f.id
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

        query += " ORDER BY f.path, c.line, m.line"

        if self.limit:
            query += " LIMIT ?"
            params.append(self.limit)
            if self.offset:
                query += " OFFSET ?"
                params.append(self.offset)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        methods = []
        for row in rows:
            args = json.loads(row["args"]) if row["args"] else []
            methods.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "line": row["line"],
                    "args": args,
                    "docstring": row["docstring"],
                    "is_abstract": bool(row["is_abstract"]),
                    "has_pass": bool(row["has_pass"]),
                    "has_not_implemented": bool(row["has_not_implemented"]),
                    "class_id": row["class_id"],
                    "class_name": row["class_name"],
                    "class_line": row["class_line"],
                    "file_id": row["file_id"],
                    "file_path": row["file_path"],
                }
            )

        # Get total count
        count_query = """
            SELECT COUNT(*) as total
            FROM methods m
            JOIN classes c ON m.class_id = c.id
            JOIN files f ON c.file_id = f.id
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

        cursor.execute(count_query, count_params)
        total_count = cursor.fetchone()["total"]

        return {
            "success": True,
            "message": f"Found {len(methods)} methods",
            "entity_type": "method",
            "total": total_count,
            "limit": self.limit,
            "offset": self.offset,
            "entities": methods,
        }

    async def _list_all(self) -> Dict[str, Any]:
        """List all entities (classes, functions, methods)."""
        classes_result = await self._list_classes()
        functions_result = await self._list_functions()
        methods_result = await self._list_methods()

        if not all(
            r.get("success") for r in [classes_result, functions_result, methods_result]
        ):
            return {
                "success": False,
                "message": "Error listing some entities",
            }

        return {
            "success": True,
            "message": f"Found {classes_result['total']} classes, {functions_result['total']} functions, {methods_result['total']} methods",
            "entity_type": "all",
            "total": {
                "classes": classes_result["total"],
                "functions": functions_result["total"],
                "methods": methods_result["total"],
            },
            "limit": self.limit,
            "offset": self.offset,
            "entities": {
                "classes": classes_result["entities"],
                "functions": functions_result["entities"],
                "methods": methods_result["entities"],
            },
        }
