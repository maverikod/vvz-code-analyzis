"""
MCP command wrapper: get_class_hierarchy.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class GetClassHierarchyMCPCommand(BaseMCPCommand):
    """Get class hierarchy (inheritance tree)."""

    name = "get_class_hierarchy"
    version = "1.0.0"
    descr = "Get class inheritance hierarchy for a specific class or all classes"
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "class_name": {
                    "type": "string",
                    "description": "Optional class name to get hierarchy for (if null, returns all hierarchies)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (absolute or relative)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        class_name: Optional[str] = None,
        file_path: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            # Get class hierarchy from database
            # Classes table has 'bases' field (JSON array of base class names)
            import json
            
            # Build hierarchy map
            hierarchy = {}
            all_classes = []
            
            # Get all classes for the project
            query = """
                SELECT c.*, f.path as file_path
                FROM classes c
                JOIN files f ON c.file_id = f.id
                WHERE f.project_id = ?
            """
            params = [proj_id]
            
            if class_name:
                query += " AND c.name = ?"
                params.append(class_name)
            
            if file_path:
                from pathlib import Path
                file_path_obj = Path(file_path)
                root_path = Path(root_dir).resolve()
                if file_path_obj.is_absolute():
                    try:
                        normalized_path = file_path_obj.relative_to(root_path)
                        file_path = str(normalized_path)
                    except ValueError:
                        pass
                else:
                    file_path = str(file_path_obj)
                
                # Try to find file
                file_record = db.get_file_by_path(file_path, proj_id)
                if not file_record:
                    # Try versioned path
                    row = db._fetchone(
                        "SELECT id FROM files WHERE project_id = ? AND path LIKE ?",
                        (proj_id, f"%{file_path}")
                    )
                    if row:
                        file_record = {"id": row["id"]}
                
                if file_record:
                    query += " AND c.file_id = ?"
                    params.append(file_record["id"])
            
            rows = db._fetchall(query, tuple(params))
            
            for row in rows:
                class_info = row
                class_name_val = class_info["name"]
                bases_str = class_info.get("bases")
                
                # Parse bases (JSON array or string)
                bases = []
                if bases_str:
                    try:
                        if isinstance(bases_str, str):
                            bases = json.loads(bases_str)
                        else:
                            bases = bases_str
                        if not isinstance(bases, list):
                            bases = [bases] if bases else []
                    except (json.JSONDecodeError, TypeError):
                        # Try to parse as AST string representation
                        bases = []
                
                hierarchy[class_name_val] = {
                    "name": class_name_val,
                    "file_path": class_info.get("file_path"),
                    "line": class_info.get("line"),
                    "bases": bases,
                    "children": [],
                }
                all_classes.append(class_info)
            
            # Build parent-child relationships
            for class_name_val, class_info in hierarchy.items():
                for base in class_info["bases"]:
                    # Extract class name from base (could be "BaseClass" or "module.BaseClass")
                    base_name = base.split(".")[-1] if isinstance(base, str) else str(base)
                    if base_name in hierarchy:
                        hierarchy[base_name]["children"].append(class_name_val)
            
            # Filter by class_name if specified
            if class_name:
                result_hierarchy = hierarchy.get(class_name, {})
            else:
                result_hierarchy = hierarchy
            
            db.close()
            
            return SuccessResult(
                data={
                    "success": True,
                    "class_name": class_name,
                    "hierarchy": result_hierarchy,
                    "count": len(result_hierarchy) if isinstance(result_hierarchy, dict) else 1,
                }
            )
        except Exception as e:
            return self._handle_error(
                e, "GET_CLASS_HIERARCHY_ERROR", "get_class_hierarchy"
            )
