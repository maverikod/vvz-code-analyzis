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
            
            db.disconnect()
            
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

    @classmethod
    def metadata(cls: type["GetClassHierarchyMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The get_class_hierarchy command retrieves class inheritance hierarchy (inheritance tree) "
                "for a specific class or all classes in the project. It builds parent-child relationships "
                "based on base classes stored in the database.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Queries classes table for project classes\n"
                "5. If class_name provided, filters to that class\n"
                "6. If file_path provided, filters to classes in that file\n"
                "7. Parses bases field (JSON array of base class names)\n"
                "8. Builds hierarchy map with parent-child relationships\n"
                "9. Returns hierarchy structure with bases and children\n\n"
                "Hierarchy Structure:\n"
                "- Each class entry contains: name, file_path, line, bases (list), children (list)\n"
                "- bases: List of base/parent class names\n"
                "- children: List of derived/child class names\n"
                "- Hierarchy is built by matching base names to class names\n\n"
                "Use cases:\n"
                "- Understand class inheritance structure\n"
                "- Find all subclasses of a base class\n"
                "- Find all parent classes of a derived class\n"
                "- Visualize inheritance relationships\n"
                "- Analyze class design patterns\n\n"
                "Important notes:\n"
                "- Bases are stored as JSON array in database\n"
                "- Base class names are extracted from full qualified names (module.Class -> Class)\n"
                "- If class_name provided, returns hierarchy for that class only\n"
                "- If class_name not provided, returns all hierarchies in project"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                },
                "class_name": {
                    "description": (
                        "Optional class name to get hierarchy for. If provided, returns hierarchy "
                        "for that specific class only. If null, returns all class hierarchies."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["BaseHandler", "DataProcessor", "Task"],
                },
                "file_path": {
                    "description": (
                        "Optional file path to filter by. If provided, only includes classes "
                        "from this file. Can be absolute or relative to root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Get hierarchy for specific class",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "class_name": "BaseHandler",
                    },
                    "explanation": (
                        "Returns inheritance hierarchy for BaseHandler class, showing its bases "
                        "and all classes that inherit from it."
                    ),
                },
                {
                    "description": "Get all class hierarchies in project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Returns complete inheritance hierarchy for all classes in the project."
                    ),
                },
                {
                    "description": "Get hierarchies for classes in specific file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/handlers.py",
                    },
                    "explanation": (
                        "Returns hierarchies for all classes defined in src/handlers.py file."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "GET_CLASS_HIERARCHY_ERROR": {
                    "description": "General error during hierarchy retrieval",
                    "example": "Database error, JSON parsing error, or corrupted data",
                    "solution": (
                        "Check database integrity, verify parameters, ensure project has been analyzed. "
                        "Check that bases field contains valid JSON."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Always true on success",
                        "class_name": "Class name if specified (or null)",
                        "hierarchy": (
                            "Dictionary mapping class names to hierarchy info. Each entry contains:\n"
                            "- name: Class name\n"
                            "- file_path: File where class is defined\n"
                            "- line: Line number where class is defined\n"
                            "- bases: List of base class names\n"
                            "- children: List of child class names"
                        ),
                        "count": "Number of classes in hierarchy",
                    },
                    "example_single": {
                        "success": True,
                        "class_name": "BaseHandler",
                        "hierarchy": {
                            "BaseHandler": {
                                "name": "BaseHandler",
                                "file_path": "src/handlers.py",
                                "line": 10,
                                "bases": [],
                                "children": ["TaskHandler", "DataHandler"],
                            },
                        },
                        "count": 1,
                    },
                    "example_all": {
                        "success": True,
                        "class_name": None,
                        "hierarchy": {
                            "BaseHandler": {
                                "name": "BaseHandler",
                                "file_path": "src/handlers.py",
                                "line": 10,
                                "bases": [],
                                "children": ["TaskHandler"],
                            },
                            "TaskHandler": {
                                "name": "TaskHandler",
                                "file_path": "src/handlers.py",
                                "line": 20,
                                "bases": ["BaseHandler"],
                                "children": [],
                            },
                        },
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, GET_CLASS_HIERARCHY_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use class_name parameter to focus on specific class hierarchy",
                "Use file_path filter to analyze classes in specific module",
                "Combine with export_graph (graph_type='hierarchy') for visualization",
                "Check bases and children arrays to understand inheritance flow",
                "Use for design pattern analysis and refactoring planning",
            ],
        }
