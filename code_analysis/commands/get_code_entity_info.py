"""
Command for getting detailed information about code entities (classes, functions, methods).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class GetCodeEntityInfoCommand:
    """Command for getting detailed information about code entities."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        entity_type: str,  # "class", "function", "method"
        entity_name: str,
        file_path: Optional[str] = None,
        line: Optional[int] = None,
    ):
        """
        Initialize get code entity info command.

        Args:
            database: Database instance
            project_id: Project UUID
            entity_type: Type of entity ("class", "function", "method")
            entity_name: Name of the entity
            file_path: Optional file path to search in (if None, searches all files)
            line: Optional line number for disambiguation
        """
        self.database = database
        self.project_id = project_id
        self.entity_type = entity_type.lower()
        self.entity_name = entity_name
        self.file_path = Path(file_path) if file_path else None
        self.line = line

    async def execute(self) -> Dict[str, Any]:
        """
        Execute entity info retrieval.

        Returns:
            Dictionary with detailed entity information
        """
        try:
            if self.entity_type == "class":
                return await self._get_class_info()
            elif self.entity_type == "function":
                return await self._get_function_info()
            elif self.entity_type == "method":
                return await self._get_method_info()
            else:
                return {
                    "success": False,
                    "message": f"Unknown entity type: {self.entity_type}. Must be 'class', 'function', or 'method'",
                }
        except Exception as e:
            logger.error(f"Error getting entity info: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error getting entity info: {e}",
                "error": str(e),
            }

    async def _get_class_info(self) -> Dict[str, Any]:
        """Get detailed information about a class."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        # Build query to find class
        query = """
            SELECT c.id, c.name, c.line, c.docstring, c.bases, c.file_id,
                   f.path as file_path, f.lines as file_lines
            FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND c.name = ?
        """
        params = [self.project_id, self.entity_name]

        if self.file_path:
            # Try to match both absolute and relative paths
            file_path_str = str(self.file_path)
            if not self.file_path.is_absolute():
                # For relative paths, try direct match first
                query += " AND (f.path = ? OR f.path = ?)"
                params.append(file_path_str)
                # Try to resolve to absolute if project root is known
                project = self.database.get_project(self.project_id)
                if project:
                    project_root = Path(project["root_path"])
                    absolute_path = str((project_root / self.file_path).resolve())
                    params.append(absolute_path)
                else:
                    params.append(file_path_str)
            else:
                # For absolute paths, try both absolute and relative
                query += " AND (f.path = ? OR f.path = ?)"
                params.append(file_path_str)
                params.append(self.file_path.name)

        if self.line:
            query += " AND c.line = ?"
            params.append(self.line)

        query += " ORDER BY c.line LIMIT 1"

        cursor.execute(query, params)
        row = cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": f"Class '{self.entity_name}' not found",
            }

        class_id = row["id"]
        bases = json.loads(row["bases"]) if row["bases"] else []

        # Get all methods for this class
        cursor.execute(
            """
            SELECT id, name, line, args, docstring, is_abstract, has_pass, has_not_implemented
            FROM methods
            WHERE class_id = ?
            ORDER BY line
        """,
            (class_id,),
        )
        method_rows = cursor.fetchall()

        methods = []
        for m_row in method_rows:
            args = json.loads(m_row["args"]) if m_row["args"] else []
            methods.append({
                "id": m_row["id"],
                "name": m_row["name"],
                "line": m_row["line"],
                "args": args,
                "docstring": m_row["docstring"],
                "is_abstract": bool(m_row["is_abstract"]),
                "has_pass": bool(m_row["has_pass"]),
                "has_not_implemented": bool(m_row["has_not_implemented"]),
            })

        # Get AST node if available
        ast_node = None
        ast_record = await self.database.get_ast_tree(row["file_id"])
        if ast_record:
            try:
                ast_json = ast_record["ast_json"]
                ast_dict = json.loads(ast_json) if isinstance(ast_json, str) else ast_json
                ast_node = self._find_class_node(ast_dict, self.entity_name, row["line"])
            except Exception as e:
                logger.debug(f"Error parsing AST for class: {e}")

        # Get chunks related to this class
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM code_chunks
            WHERE class_id = ?
        """,
            (class_id,),
        )
        chunk_count = cursor.fetchone()["count"]

        return {
            "success": True,
            "entity_type": "class",
            "entity_name": self.entity_name,
            "id": class_id,
            "line": row["line"],
            "docstring": row["docstring"],
            "bases": bases,
            "file": {
                "id": row["file_id"],
                "path": row["file_path"],
                "lines": row["file_lines"],
            },
            "methods": methods,
            "method_count": len(methods),
            "chunk_count": chunk_count,
            "ast_node": ast_node,
        }

    async def _get_function_info(self) -> Dict[str, Any]:
        """Get detailed information about a function."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        # Build query to find function
        query = """
            SELECT func.id, func.name, func.line, func.args, func.docstring, func.file_id,
                   f.path as file_path, f.lines as file_lines
            FROM functions func
            JOIN files f ON func.file_id = f.id
            WHERE f.project_id = ? AND func.name = ?
        """
        params = [self.project_id, self.entity_name]

        if self.file_path:
            # Try to match both absolute and relative paths
            file_path_str = str(self.file_path)
            if not self.file_path.is_absolute():
                # For relative paths, try direct match first
                query += " AND (f.path = ? OR f.path = ?)"
                params.append(file_path_str)
                # Try to resolve to absolute if project root is known
                project = self.database.get_project(self.project_id)
                if project:
                    project_root = Path(project["root_path"])
                    absolute_path = str((project_root / self.file_path).resolve())
                    params.append(absolute_path)
                else:
                    params.append(file_path_str)
            else:
                # For absolute paths, try both absolute and relative
                query += " AND (f.path = ? OR f.path = ?)"
                params.append(file_path_str)
                params.append(self.file_path.name)

        if self.line:
            query += " AND func.line = ?"
            params.append(self.line)

        query += " ORDER BY func.line LIMIT 1"

        cursor.execute(query, params)
        row = cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": f"Function '{self.entity_name}' not found",
            }

        function_id = row["id"]
        args = json.loads(row["args"]) if row["args"] else []

        # Get AST node if available
        ast_node = None
        ast_record = await self.database.get_ast_tree(row["file_id"])
        if ast_record:
            try:
                ast_json = ast_record["ast_json"]
                ast_dict = json.loads(ast_json) if isinstance(ast_json, str) else ast_json
                ast_node = self._find_function_node(ast_dict, self.entity_name, row["line"])
            except Exception as e:
                logger.debug(f"Error parsing AST for function: {e}")

        # Get chunks related to this function
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM code_chunks
            WHERE function_id = ?
        """,
            (function_id,),
        )
        chunk_count = cursor.fetchone()["count"]

        return {
            "success": True,
            "entity_type": "function",
            "entity_name": self.entity_name,
            "id": function_id,
            "line": row["line"],
            "args": args,
            "docstring": row["docstring"],
            "file": {
                "id": row["file_id"],
                "path": row["file_path"],
                "lines": row["file_lines"],
            },
            "chunk_count": chunk_count,
            "ast_node": ast_node,
        }

    async def _get_method_info(self) -> Dict[str, Any]:
        """Get detailed information about a method."""
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        # Build query to find method
        query = """
            SELECT m.id, m.name, m.line, m.args, m.docstring, m.is_abstract,
                   m.has_pass, m.has_not_implemented, m.class_id,
                   c.name as class_name, c.line as class_line,
                   f.id as file_id, f.path as file_path, f.lines as file_lines
            FROM methods m
            JOIN classes c ON m.class_id = c.id
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND m.name = ?
        """
        params = [self.project_id, self.entity_name]

        if self.file_path:
            # Try to match both absolute and relative paths
            file_path_str = str(self.file_path)
            if not self.file_path.is_absolute():
                # For relative paths, try direct match first
                query += " AND (f.path = ? OR f.path = ?)"
                params.append(file_path_str)
                # Try to resolve to absolute if project root is known
                project = self.database.get_project(self.project_id)
                if project:
                    project_root = Path(project["root_path"])
                    absolute_path = str((project_root / self.file_path).resolve())
                    params.append(absolute_path)
                else:
                    params.append(file_path_str)
            else:
                # For absolute paths, try both absolute and relative
                query += " AND (f.path = ? OR f.path = ?)"
                params.append(file_path_str)
                params.append(self.file_path.name)

        if self.line:
            query += " AND m.line = ?"
            params.append(self.line)

        query += " ORDER BY m.line LIMIT 1"

        cursor.execute(query, params)
        row = cursor.fetchone()

        if not row:
            return {
                "success": False,
                "message": f"Method '{self.entity_name}' not found",
            }

        method_id = row["id"]
        args = json.loads(row["args"]) if row["args"] else []

        # Get AST node if available
        ast_node = None
        ast_record = await self.database.get_ast_tree(row["file_id"])
        if ast_record:
            try:
                ast_json = ast_record["ast_json"]
                ast_dict = json.loads(ast_json) if isinstance(ast_json, str) else ast_json
                ast_node = self._find_method_node(ast_dict, row["class_name"], self.entity_name, row["line"])
            except Exception as e:
                logger.debug(f"Error parsing AST for method: {e}")

        # Get chunks related to this method
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM code_chunks
            WHERE method_id = ?
        """,
            (method_id,),
        )
        chunk_count = cursor.fetchone()["count"]

        return {
            "success": True,
            "entity_type": "method",
            "entity_name": self.entity_name,
            "id": method_id,
            "line": row["line"],
            "args": args,
            "docstring": row["docstring"],
            "is_abstract": bool(row["is_abstract"]),
            "has_pass": bool(row["has_pass"]),
            "has_not_implemented": bool(row["has_not_implemented"]),
            "class": {
                "id": row["class_id"],
                "name": row["class_name"],
                "line": row["class_line"],
            },
            "file": {
                "id": row["file_id"],
                "path": row["file_path"],
                "lines": row["file_lines"],
            },
            "chunk_count": chunk_count,
            "ast_node": ast_node,
        }

    def _find_class_node(self, ast_dict: Dict[str, Any], class_name: str, line: int) -> Optional[Dict[str, Any]]:
        """Find class node in AST by name and line."""
        return self._find_node_recursive(ast_dict, "ClassDef", class_name, line)

    def _find_function_node(self, ast_dict: Dict[str, Any], func_name: str, line: int) -> Optional[Dict[str, Any]]:
        """Find function node in AST by name and line."""
        return self._find_node_recursive(ast_dict, "FunctionDef", func_name, line)

    def _find_method_node(
        self, ast_dict: Dict[str, Any], class_name: str, method_name: str, line: int
    ) -> Optional[Dict[str, Any]]:
        """Find method node in AST by class name, method name and line."""
        # First find the class
        class_node = self._find_node_recursive(ast_dict, "ClassDef", class_name, None)
        if not class_node:
            return None

        # Then find method in class body
        return self._find_node_recursive(class_node, "FunctionDef", method_name, line)

    def _find_node_recursive(
        self, node: Dict[str, Any], node_type: str, name: str, line: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """Recursively find node in AST."""
        if not isinstance(node, dict):
            return None

        if node.get("_type") == node_type:
            node_name = node.get("name", {}).get("id") if isinstance(node.get("name"), dict) else node.get("name")
            node_line = node.get("lineno")
            if node_name == name and (line is None or node_line == line):
                return node

        # Recursively search children
        for key, value in node.items():
            if key == "_type":
                continue
            if isinstance(value, dict):
                result = self._find_node_recursive(value, node_type, name, line)
                if result:
                    return result
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        result = self._find_node_recursive(item, node_type, name, line)
                        if result:
                            return result

        return None

