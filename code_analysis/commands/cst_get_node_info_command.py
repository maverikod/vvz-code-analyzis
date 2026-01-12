"""
MCP command: cst_get_node_info

Get detailed information about a node in CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_metadata import get_node_children, get_node_metadata, get_node_parent

logger = logging.getLogger(__name__)


class CSTGetNodeInfoCommand(BaseMCPCommand):
    """Get detailed information about a node."""

    name = "cst_get_node_info"
    version = "1.0.0"
    descr = "Get detailed information about a node in CST tree (metadata, children, parent)"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tree_id": {"type": "string", "description": "Tree ID from cst_load_file"},
                "node_id": {"type": "string", "description": "Node ID"},
                "include_code": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to include code snippet",
                },
                "include_children": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to include full children information",
                },
                "include_parent": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to include parent node information",
                },
                "max_children": {
                    "type": "integer",
                    "description": "Maximum number of children to return (if include_children=True)",
                },
            },
            "required": ["tree_id", "node_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        node_id: str,
        include_code: bool = False,
        include_children: bool = False,
        include_parent: bool = False,
        max_children: Optional[int] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            # Get node metadata
            metadata = get_node_metadata(tree_id, node_id, include_code=include_code)
            if not metadata:
                return ErrorResult(
                    message=f"Node not found: {node_id}",
                    code="NODE_NOT_FOUND",
                    details={"tree_id": tree_id, "node_id": node_id},
                )

            result: Dict[str, Any] = {
                "success": True,
                "tree_id": tree_id,
                "node": metadata.to_dict(),
            }

            # Get children if requested
            if include_children:
                children = get_node_children(tree_id, node_id, include_code=include_code)
                if max_children is not None:
                    children = children[:max_children]
                result["children"] = [child.to_dict() for child in children]
                result["children_count"] = len(children)

            # Get parent if requested
            if include_parent:
                parent = get_node_parent(tree_id, node_id)
                if parent:
                    result["parent"] = parent.to_dict()

            return SuccessResult(data=result)

        except Exception as e:
            logger.exception("cst_get_node_info failed: %s", e)
            return ErrorResult(message=f"cst_get_node_info failed: {e}", code="CST_GET_NODE_ERROR")

    @classmethod
    def metadata(cls: type["CSTGetNodeInfoCommand"]) -> Dict[str, Any]:
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
                "The cst_get_node_info command retrieves detailed information about a specific node "
                "in a CST tree. It can return node metadata, children, parent, and code snippet.\n\n"
                "Operation flow:\n"
                "1. Validates tree_id exists\n"
                "2. Validates node_id exists in tree\n"
                "3. Retrieves node metadata\n"
                "4. Optionally retrieves children (with limit)\n"
                "5. Optionally retrieves parent\n"
                "6. Returns combined information\n\n"
                "Information Available:\n"
                "- Node metadata: type, kind, name, qualname, position, children_count\n"
                "- Code snippet: full source code of the node (if include_code=True)\n"
                "- Children: list of child nodes with metadata (if include_children=True)\n"
                "- Parent: parent node metadata (if include_parent=True)\n\n"
                "Use cases:\n"
                "- Get full information about a node before modification\n"
                "- Analyze node structure and relationships\n"
                "- Inspect code before making changes\n"
                "- Understand node context (parent, children)\n\n"
                "Important notes:\n"
                "- Tree must be loaded first with cst_load_file\n"
                "- Node must exist in tree (use cst_find_node to find nodes)\n"
                "- Children and parent are optional (reduce response size if not needed)\n"
                "- max_children limits number of children returned\n"
            ),
            "parameters": {
                "tree_id": {
                    "description": "Tree ID from cst_load_file command",
                    "type": "string",
                    "required": True,
                },
                "node_id": {
                    "description": "Node ID (from cst_load_file or cst_find_node results)",
                    "type": "string",
                    "required": True,
                },
                "include_code": {
                    "description": "Whether to include code snippet. Default is False.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "include_children": {
                    "description": (
                        "Whether to include full children information. "
                        "Default is False. Use max_children to limit results."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "include_parent": {
                    "description": "Whether to include parent node information. Default is False.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "max_children": {
                    "description": (
                        "Maximum number of children to return (if include_children=True). "
                        "Useful for nodes with many children."
                    ),
                    "type": "integer",
                    "required": False,
                    "examples": [10, 50, 100],
                },
            },
            "return_value": {
                "success": {
                    "description": "Node information retrieved successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "Tree ID",
                        "node": "Node metadata dictionary",
                        "children": "List of child node metadata (if include_children=True)",
                        "children_count": "Number of children returned (if include_children=True)",
                        "parent": "Parent node metadata (if include_parent=True)",
                    },
                    "example": {
                        "success": True,
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node": {
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
                        },
                        "children": [
                            {
                                "node_id": "stmt:If:12:4-18:0",
                                "type": "If",
                                "kind": "stmt",
                                "start_line": 12,
                                "start_col": 4,
                                "end_line": 18,
                                "end_col": 0,
                            }
                        ],
                        "children_count": 1,
                        "parent": None,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., NODE_NOT_FOUND, CST_GET_NODE_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "Get basic node information",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node_id": "function:main:FunctionDef:10:0-25:0",
                    },
                    "explanation": (
                        "Gets basic metadata for the node (type, name, position, etc.). "
                        "No code, children, or parent information included."
                    ),
                },
                {
                    "description": "Get node with code snippet",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node_id": "function:main:FunctionDef:10:0-25:0",
                        "include_code": True,
                    },
                    "explanation": (
                        "Gets node metadata and full source code. "
                        "Useful for inspecting code before modification."
                    ),
                },
                {
                    "description": "Get node with children",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node_id": "class:MyClass:ClassDef:10:0-100:0",
                        "include_children": True,
                    },
                    "explanation": (
                        "Gets node metadata and all children. "
                        "Useful for analyzing structure of classes or functions."
                    ),
                },
                {
                    "description": "Get node with limited children",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node_id": "class:MyClass:ClassDef:10:0-100:0",
                        "include_children": True,
                        "max_children": 10,
                    },
                    "explanation": (
                        "Gets node metadata and first 10 children. "
                        "Useful for large classes with many methods."
                    ),
                },
                {
                    "description": "Get node with parent",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node_id": "method:my_method:FunctionDef:20:0-30:0",
                        "include_parent": True,
                    },
                    "explanation": (
                        "Gets node metadata and parent node. "
                        "Useful for understanding context (e.g., which class contains a method)."
                    ),
                },
                {
                    "description": "Get full node information",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node_id": "function:main:FunctionDef:10:0-25:0",
                        "include_code": True,
                        "include_children": True,
                        "include_parent": True,
                    },
                    "explanation": (
                        "Gets complete information: metadata, code, children, and parent. "
                        "Useful for comprehensive analysis before modification."
                    ),
                },
            ],
            "error_cases": {
                "NODE_NOT_FOUND": {
                    "description": "Node does not exist in tree",
                    "message": "Node not found: {node_id}",
                    "solution": (
                        "Verify node_id is correct. "
                        "Use cst_load_file to get node_ids or cst_find_node to find nodes."
                    ),
                },
                "CST_GET_NODE_ERROR": {
                    "description": "Error during node information retrieval",
                    "examples": [
                        {
                            "case": "Tree not found",
                            "message": "cst_get_node_info failed: Tree not found: {tree_id}",
                            "solution": (
                                "Tree was not loaded or was removed from memory. "
                                "Use cst_load_file to load file into tree first."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Use include_code=True only when code is needed (reduces response size)",
                "Use include_children=True only when children information is needed",
                "Use max_children to limit response size for nodes with many children",
                "Tree must be loaded first with cst_load_file",
                "Use cst_find_node to find nodes before getting their information",
                "Node_id can be obtained from cst_load_file or cst_find_node results",
            ],
        }
