"""
MCP command: cst_reload_tree

Reload CST tree from file, updating existing tree in memory.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_builder import get_tree, reload_tree_from_file

logger = logging.getLogger(__name__)


class CSTReloadTreeCommand(BaseMCPCommand):
    """Reload CST tree from file, updating existing tree in memory."""

    name = "cst_reload_tree"
    version = "1.0.0"
    descr = "Reload CST tree from file, updating existing tree in memory (keeps same tree_id)"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tree_id": {"type": "string", "description": "Tree ID to reload"},
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
            "required": ["tree_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        node_types: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        include_children: bool = True,
        **kwargs,
    ) -> SuccessResult:
        try:
            # Check if tree exists
            tree = get_tree(tree_id)
            if not tree:
                return ErrorResult(
                    message=f"Tree not found: {tree_id}",
                    code="TREE_NOT_FOUND",
                    details={"tree_id": tree_id},
                )

            # Reload tree from file
            updated_tree = reload_tree_from_file(
                tree_id=tree_id,
                node_types=node_types,
                max_depth=max_depth,
                include_children=include_children,
            )

            if not updated_tree:
                return ErrorResult(
                    message=f"Failed to reload tree: {tree_id}",
                    code="RELOAD_FAILED",
                    details={"tree_id": tree_id},
                )

            # Convert metadata to dictionaries
            nodes = [meta.to_dict() for meta in updated_tree.metadata_map.values()]

            data = {
                "success": True,
                "tree_id": updated_tree.tree_id,
                "file_path": updated_tree.file_path,
                "nodes": nodes,
                "total_nodes": len(nodes),
                "reloaded": True,
            }

            return SuccessResult(data=data)

        except FileNotFoundError as e:
            return ErrorResult(
                message=f"File not found: {e}",
                code="FILE_NOT_FOUND",
                details={"tree_id": tree_id},
            )
        except ValueError as e:
            return ErrorResult(
                message=f"Invalid file: {e}",
                code="INVALID_FILE",
                details={"tree_id": tree_id},
            )
        except Exception as e:
            logger.exception("cst_reload_tree failed: %s", e)
            return ErrorResult(
                message=f"cst_reload_tree failed: {e}", code="CST_RELOAD_ERROR"
            )

    @classmethod
    def metadata(cls: type["CSTReloadTreeCommand"]) -> Dict[str, Any]:
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
                "The cst_reload_tree command reloads a CST tree from its file on disk, "
                "updating the existing tree in memory. The tree_id remains the same, so all "
                "references to the tree remain valid. This is useful after saving a tree to "
                "file or when the file has been modified externally.\n\n"
                "Operation flow:\n"
                "1. Validates tree_id exists in memory\n"
                "2. Reads file from disk (using file_path stored in tree)\n"
                "3. Parses source using LibCST\n"
                "4. Updates tree module in place\n"
                "5. Rebuilds node index and metadata\n"
                "6. Returns updated tree_id and node metadata\n\n"
                "Key differences from cst_load_file:\n"
                "- Keeps the same tree_id (no new tree is created)\n"
                "- Updates existing tree in memory\n"
                "- All references to tree_id remain valid\n"
                "- Useful for synchronizing tree with file after save\n\n"
                "Use cases:\n"
                "- Reload tree after cst_save_tree to sync with file\n"
                "- Update tree after external file modifications\n"
                "- Refresh tree metadata after file changes\n"
                "- Maintain tree_id across file reloads\n\n"
                "Important notes:\n"
                "- Tree_id remains the same after reload\n"
                "- All node_ids may change if file structure changed\n"
                "- Tree is updated in place, not replaced\n"
                "- File must exist and be valid Python code"
            ),
            "parameters": {
                "tree_id": {
                    "description": "Tree ID to reload (must exist in memory)",
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
                    "description": "Tree reloaded successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "Same tree_id (unchanged)",
                        "file_path": "Path to reloaded file",
                        "nodes": "List of updated node metadata dictionaries",
                        "total_nodes": "Total number of nodes returned",
                        "reloaded": "Always True",
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
                                "children_ids": [
                                    "stmt:If:12:4-20:0",
                                    "smallstmt:Return:22:4-22:12",
                                ],
                            }
                        ],
                        "total_nodes": 42,
                        "reloaded": True,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., TREE_NOT_FOUND, FILE_NOT_FOUND, CST_RELOAD_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "Reload tree after save",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    },
                    "explanation": (
                        "Reloads tree from file after saving. Tree_id remains the same, "
                        "so you can continue using it with other commands. Useful after "
                        "cst_save_tree to sync tree with saved file."
                    ),
                },
                {
                    "description": "Reload with filters",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node_types": ["FunctionDef", "ClassDef"],
                    },
                    "explanation": (
                        "Reloads tree but returns metadata only for functions and classes. "
                        "Full tree is still updated, but metadata is filtered."
                    ),
                },
            ],
            "error_cases": {
                "TREE_NOT_FOUND": {
                    "description": "Tree does not exist in memory",
                    "message": "Tree not found: {tree_id}",
                    "solution": "Use cst_load_file to load file into tree first",
                },
                "FILE_NOT_FOUND": {
                    "description": "File does not exist on disk",
                    "message": "File not found: {file_path}",
                    "solution": "Verify file exists at the path stored in tree",
                },
                "CST_RELOAD_ERROR": {
                    "description": "Error during tree reload",
                    "examples": [
                        {
                            "case": "Syntax error in file",
                            "message": "cst_reload_tree failed: SyntaxError",
                            "solution": (
                                "Fix syntax errors in the file. "
                                "LibCST requires valid Python syntax to parse."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Use after cst_save_tree to sync tree with saved file",
                "Use when file has been modified externally",
                "Tree_id remains the same, so all references remain valid",
                "All node_ids may change if file structure changed",
                "Use filters to reduce metadata size when only specific types are needed",
            ],
        }
