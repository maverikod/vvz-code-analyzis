"""
Command for searching nodes in AST trees.

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


class SearchASTNodesCommand:
    """Command for searching nodes in AST trees."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        node_type: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: int = 100,
    ):
        """
        Initialize search AST nodes command.

        Args:
            database: Database instance
            project_id: Project UUID
            node_type: Type of AST node to search for (e.g., "ClassDef", "FunctionDef")
            file_path: Optional file path to search in (if None, searches all files)
            limit: Maximum number of results to return
        """
        self.database = database
        self.project_id = project_id
        self.node_type = node_type
        self.file_path = Path(file_path) if file_path else None
        self.limit = limit

    def _search_nodes_recursive(
        self,
        node: Dict[str, Any],
        node_type: Optional[str],
        results: List[Dict[str, Any]],
        path: str = "",
    ) -> None:
        """
        Recursively search for nodes in AST dictionary.

        Args:
            node: AST node dictionary
            node_type: Type of node to search for
            results: List to append results to
            path: Current path in AST tree
        """
        if not isinstance(node, dict):
            return

        # Check if this node matches the type
        current_type = node.get("_type")
        if node_type is None or current_type == node_type:
            node_info = {
                "type": current_type,
                "path": path,
            }
            # Add relevant fields based on node type
            if "name" in node:
                node_info["name"] = node["name"]
            if "lineno" in node:
                node_info["lineno"] = node["lineno"]
            if "col_offset" in node:
                node_info["col_offset"] = node["col_offset"]

            # Add node-specific fields
            if current_type == "ClassDef":
                if "bases" in node:
                    node_info["bases"] = node["bases"]
            elif current_type in ("FunctionDef", "AsyncFunctionDef"):
                if "args" in node:
                    args = node["args"]
                    if isinstance(args, dict) and "args" in args:
                        node_info["args"] = [arg.get("arg", "") for arg in args["args"]]

            results.append(node_info)

            if len(results) >= self.limit:
                return

        # Recursively search children
        for key, value in node.items():
            if key == "_type":
                continue
            if isinstance(value, dict):
                new_path = f"{path}.{key}" if path else key
                self._search_nodes_recursive(value, node_type, results, new_path)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        new_path = f"{path}.{key}[{i}]" if path else f"{key}[{i}]"
                        self._search_nodes_recursive(item, node_type, results, new_path)

    async def execute(self) -> Dict[str, Any]:
        """
        Execute AST node search.

        Returns:
            Dictionary with search results
        """
        try:
            # Get files to search
            if self.file_path:
                # Resolve file path
                if not self.file_path.is_absolute():
                    project = self.database.get_project(self.project_id)
                    if not project:
                        return {
                            "success": False,
                            "message": f"Project {self.project_id} not found",
                        }
                    project_root = Path(project["root_path"])
                    self.file_path = project_root / self.file_path
                else:
                    self.file_path = self.file_path.resolve()

                file_record = self.database.get_file_by_path(
                    str(self.file_path), self.project_id
                )
                if not file_record:
                    return {
                        "success": False,
                        "message": f"File not found in database: {self.file_path}",
                    }
                file_ids = [file_record["id"]]
            else:
                # Get all files in project
                assert self.database.conn is not None
                cursor = self.database.conn.cursor()
                cursor.execute(
                    "SELECT id FROM files WHERE project_id = ?",
                    (self.project_id,),
                )
                file_ids = [row[0] for row in cursor.fetchall()]

            if not file_ids:
                return {
                    "success": True,
                    "message": "No files found in project",
                    "results": [],
                    "count": 0,
                }

            # Search AST trees
            all_results = []
            for file_id in file_ids:
                ast_record = await self.database.get_ast_tree(file_id)
                if not ast_record:
                    continue

                try:
                    ast_json = ast_record["ast_json"]
                    ast_dict = (
                        json.loads(ast_json) if isinstance(ast_json, str) else ast_json
                    )

                    # Get file path for context
                    file_record = self.database.get_file_by_id(file_id)
                    file_path = file_record["path"] if file_record else None

                    # Search nodes
                    file_results = []
                    self._search_nodes_recursive(ast_dict, self.node_type, file_results)

                    # Add file context to results
                    for result in file_results:
                        result["file_id"] = file_id
                        result["file_path"] = file_path
                        all_results.append(result)

                    if len(all_results) >= self.limit:
                        break

                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Error parsing AST for file_id={file_id}: {e}")
                    continue

            return {
                "success": True,
                "message": f"Found {len(all_results)} nodes",
                "results": all_results[: self.limit],
                "count": len(all_results),
                "node_type": self.node_type,
                "limit": self.limit,
            }

        except Exception as e:
            logger.error(f"Error searching AST nodes: {e}")
            return {
                "success": False,
                "message": f"Error searching AST nodes: {e}",
                "error": str(e),
            }
