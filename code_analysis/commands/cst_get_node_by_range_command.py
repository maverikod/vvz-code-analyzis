"""
MCP command: cst_get_node_by_range

Get node ID for a specific line range in CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_range_finder import find_node_by_range, find_nodes_by_range

logger = logging.getLogger(__name__)


class CSTGetNodeByRangeCommand(BaseMCPCommand):
    """Get node ID for a specific line range."""

    name = "cst_get_node_by_range"
    version = "1.0.0"
    descr = "Get node ID for a specific line range in CST tree"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tree_id": {
                    "type": "string",
                    "description": "Tree ID from cst_load_file",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-based, inclusive)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-based, inclusive)",
                },
                "prefer_exact": {
                    "type": "boolean",
                    "default": True,
                    "description": "If True, prefer node that exactly matches the range. If False, return smallest node containing the range.",
                },
                "all_intersecting": {
                    "type": "boolean",
                    "default": False,
                    "description": "If True, return all nodes that intersect with the range. If False, return single best node.",
                },
            },
            "required": ["tree_id", "start_line", "end_line"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        start_line: int,
        end_line: int,
        prefer_exact: bool = True,
        all_intersecting: bool = False,
        **kwargs,
    ) -> SuccessResult:
        try:
            if all_intersecting:
                # Return all nodes that intersect with the range
                nodes = find_nodes_by_range(tree_id, start_line, end_line)
                result: Dict[str, Any] = {
                    "success": True,
                    "tree_id": tree_id,
                    "start_line": start_line,
                    "end_line": end_line,
                    "nodes": [node.to_dict() for node in nodes],
                    "total_nodes": len(nodes),
                }
            else:
                # Return single best node covering the range
                node = find_node_by_range(
                    tree_id, start_line, end_line, prefer_exact=prefer_exact
                )
                if not node:
                    return ErrorResult(
                        message=f"No node found covering range {start_line}-{end_line}",
                        code="NODE_NOT_FOUND",
                        details={
                            "tree_id": tree_id,
                            "start_line": start_line,
                            "end_line": end_line,
                        },
                    )

                result = {
                    "success": True,
                    "tree_id": tree_id,
                    "start_line": start_line,
                    "end_line": end_line,
                    "node": node.to_dict(),
                    "exact_match": (
                        node.start_line == start_line and node.end_line == end_line
                    ),
                }

            return SuccessResult(data=result)

        except ValueError as e:
            return ErrorResult(
                message=f"Invalid range: {e}",
                code="INVALID_RANGE",
                details={
                    "tree_id": tree_id,
                    "start_line": start_line,
                    "end_line": end_line,
                },
            )
        except Exception as e:
            logger.exception("cst_get_node_by_range failed: %s", e)
            return ErrorResult(
                message=f"cst_get_node_by_range failed: {e}",
                code="CST_GET_NODE_BY_RANGE_ERROR",
            )

    @classmethod
    def metadata(cls: type["CSTGetNodeByRangeCommand"]) -> Dict[str, Any]:
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
                "The cst_get_node_by_range command finds a node that covers a specific line range. "
                "This is useful when you know the line numbers but need the node_id for modification operations.\n\n"
                "Operation flow:\n"
                "1. Validates tree_id exists\n"
                "2. Validates line range (start_line <= end_line)\n"
                "3. Finds node(s) covering the range\n"
                "4. Returns node metadata with node_id\n\n"
                "Search Modes:\n"
                "1. Single node (all_intersecting=False, default):\n"
                "   - Finds the best node covering the range\n"
                "   - If prefer_exact=True: prefers node that exactly matches the range\n"
                "   - If prefer_exact=False: returns smallest node that contains the range\n"
                "2. All intersecting nodes (all_intersecting=True):\n"
                "   - Returns all nodes that intersect with the range\n"
                "   - Useful for finding multiple nodes in a range\n\n"
                "Use cases:\n"
                " - Get node_id for a specific line range before modification\n"
                " - Find the node covering lines 136-143 for replacement\n"
                " - Discover code structure by line numbers\n"
                " - Get exact node_id when you know line numbers from error messages\n\n"
                "Important notes:\n"
                " - Tree must be loaded first with cst_load_file\n"
                " - Line numbers are 1-based (first line is 1)\n"
                " - Returns node that contains the range, not necessarily exact match\n"
                " - Use node_id from result with cst_modify_tree"
            ),
            "parameters": {
                "tree_id": {
                    "description": "Tree ID from cst_load_file command",
                    "type": "string",
                    "required": True,
                },
                "start_line": {
                    "description": "Start line (1-based, inclusive)",
                    "type": "integer",
                    "required": True,
                    "examples": [10, 136, 200],
                },
                "end_line": {
                    "description": "End line (1-based, inclusive)",
                    "type": "integer",
                    "required": True,
                    "examples": [20, 143, 250],
                },
                "prefer_exact": {
                    "description": (
                        "If True, prefer node that exactly matches the range. "
                        "If False, return smallest node containing the range. Default: True"
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "all_intersecting": {
                    "description": (
                        "If True, return all nodes that intersect with the range. "
                        "If False, return single best node. Default: False"
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "return_value": {
                "success": {
                    "description": "Node found successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "Tree ID that was searched",
                        "start_line": "Start line that was searched",
                        "end_line": "End line that was searched",
                        "node": "Node metadata dictionary (when all_intersecting=False)",
                        "nodes": "List of node metadata dictionaries (when all_intersecting=True)",
                        "exact_match": "Whether node exactly matches the range (when all_intersecting=False)",
                        "total_nodes": "Total number of nodes found (when all_intersecting=True)",
                    },
                    "example": {
                        "success": True,
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "start_line": 136,
                        "end_line": 143,
                        "node": {
                            "node_id": "stmt:main:SimpleStatementLine:136:8-143:33",
                            "type": "SimpleStatementLine",
                            "kind": "stmt",
                            "start_line": 136,
                            "end_line": 143,
                            "name": None,
                            "qualname": "main",
                        },
                        "exact_match": True,
                    },
                },
                "error": {
                    "description": "Node not found or error occurred",
                    "code": "Error code (e.g., NODE_NOT_FOUND, INVALID_RANGE, CST_GET_NODE_BY_RANGE_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "Get node for specific line range",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "start_line": 136,
                        "end_line": 143,
                    },
                    "explanation": (
                        "Finds the node covering lines 136-143. "
                        "Returns the best matching node (exact match preferred). "
                        "Use the node_id from result for cst_modify_tree operations."
                    ),
                },
                {
                    "description": "Get smallest node containing range",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "start_line": 136,
                        "end_line": 143,
                        "prefer_exact": False,
                    },
                    "explanation": (
                        "Finds the smallest node that contains the range 136-143. "
                        "Useful when exact match doesn't exist but you want the most specific node."
                    ),
                },
                {
                    "description": "Get all nodes intersecting with range",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "start_line": 136,
                        "end_line": 143,
                        "all_intersecting": True,
                    },
                    "explanation": (
                        "Returns all nodes that intersect with the range 136-143. "
                        "Useful for discovering all code elements in a line range."
                    ),
                },
            ],
            "error_cases": {
                "NODE_NOT_FOUND": {
                    "description": "No node found covering the range",
                    "message": "No node found covering range {start_line}-{end_line}",
                    "solution": (
                        "Check that the line range is valid for the file. "
                        "Use cst_load_file to see available nodes and their line ranges."
                    ),
                },
                "INVALID_RANGE": {
                    "description": "Invalid line range",
                    "message": "Invalid range: start_line > end_line",
                    "solution": "Ensure start_line <= end_line. Line numbers are 1-based.",
                },
                "CST_GET_NODE_BY_RANGE_ERROR": {
                    "description": "Error during search",
                    "examples": [
                        {
                            "case": "Tree not found",
                            "message": "cst_get_node_by_range failed: Tree not found: {tree_id}",
                            "solution": (
                                "Tree was not loaded or was removed from memory. "
                                "Use cst_load_file to load file into tree first."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Use this command when you know line numbers but need node_id",
                "Tree must be loaded first with cst_load_file",
                "prefer_exact=True is usually what you want (default)",
                "Use all_intersecting=True to discover all nodes in a range",
                "Line numbers are 1-based (first line is 1)",
                "Use node_id from result with cst_modify_tree for modifications",
            ],
        }
