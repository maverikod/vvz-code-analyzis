"""
MCP command: cst_load_file

Load Python file into CST tree and return tree_id with node metadata.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_builder import load_file_to_tree

logger = logging.getLogger(__name__)


class CSTLoadFileCommand(BaseMCPCommand):
    """Load file into CST tree."""

    name = "cst_load_file"
    version = "1.0.0"
    descr = "Load Python file into CST tree and return tree_id with node metadata"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {"type": "string", "description": "Project root directory"},
                "file_path": {
                    "type": "string",
                    "description": "Target Python file path (absolute or relative to root_dir)",
                },
                "node_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter by node types (e.g., ['FunctionDef', 'ClassDef'])",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Optional maximum depth for node filtering",
                },
                "include_children": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to include children information in metadata",
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        node_types: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        include_children: bool = True,
        **kwargs,
    ) -> SuccessResult:
        try:
            root = Path(root_dir).resolve()
            target = Path(file_path)
            if not target.is_absolute():
                target = (root / target).resolve()

            if target.suffix != ".py":
                return ErrorResult(
                    message="Target file must be a .py file",
                    code="INVALID_FILE",
                    details={"file_path": str(target)},
                )
            if not target.exists():
                return ErrorResult(
                    message="Target file does not exist",
                    code="FILE_NOT_FOUND",
                    details={"file_path": str(target)},
                )

            # Load file into tree
            tree = load_file_to_tree(
                str(target),
                node_types=node_types,
                max_depth=max_depth,
                include_children=include_children,
            )

            # Convert metadata to dictionaries
            nodes = [meta.to_dict() for meta in tree.metadata_map.values()]

            data = {
                "success": True,
                "tree_id": tree.tree_id,
                "file_path": str(target),
                "nodes": nodes,
                "total_nodes": len(nodes),
            }

            return SuccessResult(data=data)

        except FileNotFoundError as e:
            return ErrorResult(
                message=f"File not found: {e}",
                code="FILE_NOT_FOUND",
                details={"file_path": file_path},
            )
        except ValueError as e:
            return ErrorResult(
                message=f"Invalid file: {e}",
                code="INVALID_FILE",
                details={"file_path": file_path},
            )
        except Exception as e:
            logger.exception("cst_load_file failed: %s", e)
            return ErrorResult(message=f"cst_load_file failed: {e}", code="CST_LOAD_ERROR")

    @classmethod
    def metadata(cls: type["CSTLoadFileCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

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
                "The cst_load_file command loads a Python file into a CST tree and stores it in memory. "
                "It returns a tree_id that can be used with other CST tree commands (cst_modify_tree, "
                "cst_save_tree, cst_find_node). The full CST tree is stored on the server, and only "
                "node metadata is returned to the client.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Resolves file_path (absolute or relative to root_dir)\n"
                "3. Validates file is a .py file\n"
                "4. Validates file exists\n"
                "5. Reads file source code\n"
                "6. Parses source using LibCST\n"
                "7. Builds node index and metadata\n"
                "8. Stores tree in memory with tree_id\n"
                "9. Returns tree_id and node metadata\n\n"
                "Node Metadata:\n"
                "Each node includes:\n"
                "- node_id: Stable identifier for operations\n"
                "- type: LibCST node type (FunctionDef, ClassDef, etc.)\n"
                "- kind: Node kind (function, class, method, stmt, smallstmt, etc.)\n"
                "- name: Node name (if applicable)\n"
                "- qualname: Qualified name (if applicable)\n"
                "- start_line, start_col, end_line, end_col: Position\n"
                "- children_count: Number of children\n"
                "- children_ids: List of child node IDs (if include_children=True)\n"
                "- parent_id: Parent node ID (if applicable)\n\n"
                "Filters:\n"
                "- node_types: Filter by node types (e.g., ['FunctionDef', 'ClassDef'])\n"
                "- max_depth: Limit depth of nodes returned\n"
                "- include_children: Whether to include children information\n\n"
                "Use cases:\n"
                "- Load file for modification operations\n"
                "- Analyze code structure\n"
                "- Find specific nodes for refactoring\n"
                "- Prepare for batch operations\n\n"
                "Important notes:\n"
                "- Tree is stored in memory on the server\n"
                "- Tree persists until explicitly removed or server restarts\n"
                "- Use tree_id with other CST commands\n"
                "- Filters reduce returned metadata, but full tree is still stored"
            ),
            "parameters": {
                "root_dir": {
                    "description": "Project root directory path. Use absolute path for reliability.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": "Target Python file path. Can be absolute or relative to root_dir.",
                    "type": "string",
                    "required": True,
                },
                "node_types": {
                    "description": "Optional filter by node types. Only nodes matching these types will be included in metadata.",
                    "type": "array",
                    "items": {"type": "string"},
                    "required": False,
                    "examples": [["FunctionDef", "ClassDef"], ["If", "For", "Try"]],
                },
                "max_depth": {
                    "description": "Optional maximum depth for node filtering. Nodes deeper than this will be excluded.",
                    "type": "integer",
                    "required": False,
                    "examples": [1, 2, 3],
                },
                "include_children": {
                    "description": "Whether to include children information in metadata. Default is True.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
            },
            "return_value": {
                "success": {
                    "description": "File loaded successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "Tree ID for use with other CST commands",
                        "file_path": "Path to loaded file",
                        "nodes": "List of node metadata dictionaries",
                        "total_nodes": "Total number of nodes returned",
                    },
                    "example": {
                        "success": True,
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "nodes": [
                            {
                                "node_id": "function:main:FunctionDef:10:0-25:0",
                                "type": "FunctionDef",
                                "kind": "function",
                                "name": "main",
                                "qualname": "main",
                                "start_line": 10,
                                "start_col": 0,
                                "end_line": 25,
                                "end_col": 0,
                                "children_count": 3,
                                "children_ids": ["stmt:If:12:4-20:0", "smallstmt:Return:22:4-22:12"],
                            }
                        ],
                        "total_nodes": 42,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., FILE_NOT_FOUND, INVALID_FILE, CST_LOAD_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "Load file without filters",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Loads entire file into CST tree. Returns all nodes with full metadata. "
                        "Use this when you need to work with all nodes in the file."
                    ),
                },
                {
                    "description": "Load only functions and classes",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models.py",
                        "node_types": ["FunctionDef", "ClassDef"],
                    },
                    "explanation": (
                        "Loads file but returns metadata only for functions and classes. "
                        "Useful when you only need to work with top-level definitions. "
                        "Full tree is still stored, but metadata is filtered."
                    ),
                },
                {
                    "description": "Load with depth limit",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "max_depth": 2,
                    },
                    "explanation": (
                        "Loads file but returns nodes only up to depth 2. "
                        "Useful for analyzing top-level structure without deep nesting details."
                    ),
                },
                {
                    "description": "Load without children information",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/utils.py",
                        "include_children": False,
                    },
                    "explanation": (
                        "Loads file but excludes children_ids from metadata. "
                        "Reduces response size when children information is not needed."
                    ),
                },
                {
                    "description": "Load specific statement types",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "node_types": ["If", "For", "Try", "With"],
                    },
                    "explanation": (
                        "Loads file but returns only control flow statements (if, for, try, with). "
                        "Useful for analyzing control flow patterns."
                    ),
                },
            ],
            "error_cases": {
                "FILE_NOT_FOUND": {
                    "description": "File does not exist",
                    "message": "File not found: {file_path}",
                    "solution": "Verify file_path is correct and file exists",
                },
                "INVALID_FILE": {
                    "description": "File is not a Python file",
                    "message": "File must be a .py file: {file_path}",
                    "solution": "Ensure file_path points to a .py file",
                },
                "CST_LOAD_ERROR": {
                    "description": "Error during file loading",
                    "examples": [
                        {
                            "case": "Syntax error in file",
                            "message": "cst_load_file failed: SyntaxError",
                            "solution": (
                                "Fix syntax errors in the file. "
                                "LibCST requires valid Python syntax to parse."
                            ),
                        },
                        {
                            "case": "File encoding error",
                            "message": "cst_load_file failed: UnicodeDecodeError",
                            "solution": (
                                "Ensure file is UTF-8 encoded. "
                                "Check file encoding and convert if needed."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Use absolute paths for root_dir for reliability",
                "Use node_types filter to reduce metadata size when only specific types are needed",
                "Use max_depth to limit analysis scope",
                "Set include_children=False if children information is not needed",
                "Save tree_id for use with cst_modify_tree and cst_save_tree",
                "Tree persists in memory until server restart or explicit removal",
            ],
        }
