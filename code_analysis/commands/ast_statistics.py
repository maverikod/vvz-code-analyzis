"""
Command for getting AST statistics.

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


class ASTStatisticsCommand:
    """Command for getting AST statistics."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        file_path: Optional[str] = None,
    ):
        """
        Initialize AST statistics command.

        Args:
            database: Database instance
            project_id: Project UUID
            file_path: Optional file path (if None, returns project-wide statistics)
        """
        self.database = database
        self.project_id = project_id
        self.file_path = Path(file_path) if file_path else None

    def _calculate_statistics(self, node: Dict[str, Any], stats: Dict[str, Any], depth: int = 0) -> None:
        """
        Recursively calculate statistics for AST node.

        Args:
            node: AST node dictionary
            stats: Statistics dictionary to update
            depth: Current depth in tree
        """
        if not isinstance(node, dict):
            return

        node_type = node.get("_type")
        if node_type:
            # Count node types
            stats["node_types"][node_type] = stats["node_types"].get(node_type, 0) + 1
            stats["total_nodes"] += 1
            
            # Track max depth
            if depth > stats["max_depth"]:
                stats["max_depth"] = depth

        # Recursively process children
        for key, value in node.items():
            if key == "_type":
                continue
            if isinstance(value, dict):
                self._calculate_statistics(value, stats, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._calculate_statistics(item, stats, depth + 1)

    async def execute(self) -> Dict[str, Any]:
        """
        Execute AST statistics calculation.

        Returns:
            Dictionary with AST statistics
        """
        try:
            if self.file_path:
                # Statistics for single file
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

                file_id = file_record["id"]
                ast_record = await self.database.get_ast_tree(file_id)
                if not ast_record:
                    return {
                        "success": False,
                        "message": f"AST tree not found for file: {self.file_path}",
                    }

                try:
                    ast_json = ast_record["ast_json"]
                    ast_dict = json.loads(ast_json) if isinstance(ast_json, str) else ast_json
                    
                    stats = {
                        "total_nodes": 0,
                        "max_depth": 0,
                        "node_types": {},
                    }
                    self._calculate_statistics(ast_dict, stats)
                    
                    return {
                        "success": True,
                        "message": f"AST statistics for {self.file_path}",
                        "file_id": file_id,
                        "file_path": str(self.file_path),
                        "statistics": stats,
                    }
                except (json.JSONDecodeError, KeyError) as e:
                    return {
                        "success": False,
                        "message": f"Error parsing AST JSON: {e}",
                        "error": str(e),
                    }
            else:
                # Project-wide statistics
                assert self.database.conn is not None
                cursor = self.database.conn.cursor()
                cursor.execute(
                    """
                    SELECT f.id, f.path, a.ast_json
                    FROM files f
                    JOIN ast_trees a ON f.id = a.file_id
                    WHERE f.project_id = ?
                """,
                    (self.project_id,),
                )
                rows = cursor.fetchall()

                project_stats = {
                    "total_files": 0,
                    "files_with_ast": 0,
                    "total_nodes": 0,
                    "max_depth": 0,
                    "node_types": {},
                    "file_statistics": [],
                }

                for row in rows:
                    file_id, file_path, ast_json = row
                    project_stats["total_files"] += 1
                    
                    try:
                        ast_dict = json.loads(ast_json) if isinstance(ast_json, str) else ast_json
                        project_stats["files_with_ast"] += 1
                        
                        file_stats = {
                            "total_nodes": 0,
                            "max_depth": 0,
                            "node_types": {},
                        }
                        self._calculate_statistics(ast_dict, file_stats)
                        
                        # Aggregate to project stats
                        project_stats["total_nodes"] += file_stats["total_nodes"]
                        if file_stats["max_depth"] > project_stats["max_depth"]:
                            project_stats["max_depth"] = file_stats["max_depth"]
                        
                        for node_type, count in file_stats["node_types"].items():
                            project_stats["node_types"][node_type] = (
                                project_stats["node_types"].get(node_type, 0) + count
                            )
                        
                        project_stats["file_statistics"].append({
                            "file_id": file_id,
                            "file_path": file_path,
                            "statistics": file_stats,
                        })
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.debug(f"Error parsing AST for file_id={file_id}: {e}")
                        continue

                return {
                    "success": True,
                    "message": f"AST statistics for project {self.project_id}",
                    "project_id": self.project_id,
                    "statistics": project_stats,
                }

        except Exception as e:
            logger.error(f"Error calculating AST statistics: {e}")
            return {
                "success": False,
                "message": f"Error calculating AST statistics: {e}",
                "error": str(e),
            }

