"""
Command for getting class hierarchy (inheritance tree).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class GetClassHierarchyCommand:
    """Command for getting class hierarchy."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        class_name: Optional[str] = None,  # If None, returns all hierarchies
        file_path: Optional[str] = None,
    ):
        """
        Initialize get class hierarchy command.

        Args:
            database: Database instance
            project_id: Project UUID
            class_name: Optional class name to get hierarchy for (if None, returns all)
            file_path: Optional file path to filter by
        """
        self.database = database
        self.project_id = project_id
        self.class_name = class_name
        self.file_path = Path(file_path) if file_path else None

    async def execute(self) -> Dict[str, Any]:
        """
        Execute hierarchy retrieval.

        Returns:
            Dictionary with class hierarchy information
        """
        try:
            assert self.database.conn is not None
            cursor = self.database.conn.cursor()

            # Get all classes in project
            query = """
                SELECT c.id, c.name, c.line, c.bases, c.file_id, f.path as file_path
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

            # Don't filter by class_name here - we need all classes to build hierarchy
            # We'll filter the result later if needed
            query += " ORDER BY f.path, c.line"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Build class map
            class_map: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                bases = json.loads(row["bases"]) if row["bases"] else []
                class_map[row["name"]] = {
                    "id": row["id"],
                    "name": row["name"],
                    "line": row["line"],
                    "bases": bases,
                    "file_id": row["file_id"],
                    "file_path": row["file_path"],
                    "children": [],
                }

            # Build hierarchy - first pass: identify root classes
            root_classes: List[str] = []
            for class_name, class_info in class_map.items():
                if not class_info["bases"]:
                    root_classes.append(class_name)
            
            # Second pass: add children to base classes
            for class_name, class_info in class_map.items():
                for base in class_info["bases"]:
                    if base in class_map:
                        if class_name not in class_map[base]["children"]:
                            class_map[base]["children"].append(class_name)

            # Build hierarchy tree
            if self.class_name:
                # Return hierarchy for specific class
                if self.class_name not in class_map:
                    return {
                        "success": False,
                        "message": f"Class '{self.class_name}' not found",
                    }

                # Build full hierarchy starting from requested class
                hierarchy = self._build_class_tree(self.class_name, class_map, set())
                return {
                    "success": True,
                    "message": f"Class hierarchy for '{self.class_name}'",
                    "class_name": self.class_name,
                    "hierarchy": hierarchy,
                }
            else:
                # Return all hierarchies
                hierarchies = []
                processed = set()

                def add_hierarchy(class_name: str) -> Optional[Dict[str, Any]]:
                    if class_name in processed:
                        return None
                    processed.add(class_name)
                    return self._build_class_tree(class_name, class_map, processed)

                for root in root_classes:
                    hierarchy = add_hierarchy(root)
                    if hierarchy:
                        hierarchies.append(hierarchy)

                # Also include classes that have bases but bases are not in project
                for class_name, class_info in class_map.items():
                    if class_name not in processed:
                        hierarchy = add_hierarchy(class_name)
                        if hierarchy:
                            hierarchies.append(hierarchy)

                return {
                    "success": True,
                    "message": f"Found {len(hierarchies)} class hierarchies",
                    "hierarchies": hierarchies,
                    "total_classes": len(class_map),
                }

        except Exception as e:
            logger.error(f"Error getting class hierarchy: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error getting class hierarchy: {e}",
                "error": str(e),
            }

    def _build_class_tree(
        self, class_name: str, class_map: Dict[str, Any], visited: Set[str]
    ) -> Dict[str, Any]:
        """Build class tree recursively."""
        if class_name not in class_map:
            return {
                "name": class_name,
                "file_path": None,
                "line": None,
                "bases": [],
                "children": [],
            }

        # Prevent infinite loops (circular inheritance or already visited)
        if class_name in visited:
            return {
                "name": class_name,
                "file_path": class_map[class_name].get("file_path"),
                "line": class_map[class_name].get("line"),
                "bases": [],
                "children": [],
            }

        visited.add(class_name)
        class_info = class_map[class_name]

        # Build children trees - include current class in visited to prevent going back up
        children = []
        for child_name in class_info["children"]:
            if child_name in class_map:
                child_visited = visited.copy()  # Include current class to prevent cycles
                child_tree = self._build_class_tree(child_name, class_map, child_visited)
                children.append(child_tree)

        # Build bases trees - use visited to prevent infinite loops up
        bases = []
        for base_name in class_info["bases"]:
            base_visited = visited.copy()  # Continue with current visited to prevent loops
            base_tree = self._build_class_tree(base_name, class_map, base_visited)
            bases.append(base_tree)

        return {
            "name": class_info["name"],
            "id": class_info["id"],
            "file_path": class_info["file_path"],
            "line": class_info["line"],
            "bases": bases,
            "children": children,
        }

