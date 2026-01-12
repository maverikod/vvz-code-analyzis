"""
MCP command: cst_find_node

Find nodes in CST tree using simple or XPath-like queries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_finder import find_nodes

logger = logging.getLogger(__name__)


class CSTFindNodeCommand(BaseMCPCommand):
    """Find nodes in CST tree."""

    name = "cst_find_node"
    version = "1.0.0"
    descr = "Find nodes in CST tree using simple or XPath-like queries"
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
                "search_type": {
                    "type": "string",
                    "enum": ["simple", "xpath"],
                    "default": "xpath",
                    "description": "Search type: 'simple' or 'xpath'",
                },
                "query": {
                    "type": "string",
                    "description": "CSTQuery selector string (for xpath search)",
                },
                "node_type": {
                    "type": "string",
                    "description": "Node type filter (for simple search, e.g., 'FunctionDef', 'ClassDef')",
                },
                "name": {
                    "type": "string",
                    "description": "Node name filter (for simple search)",
                },
                "qualname": {
                    "type": "string",
                    "description": "Qualified name filter (for simple search)",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line filter (for simple search)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line filter (for simple search)",
                },
            },
            "required": ["tree_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        search_type: str = "xpath",
        query: Optional[str] = None,
        node_type: Optional[str] = None,
        name: Optional[str] = None,
        qualname: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            # Find nodes
            matches = find_nodes(
                tree_id=tree_id,
                query=query,
                search_type=search_type,
                node_type=node_type,
                name=name,
                qualname=qualname,
                start_line=start_line,
                end_line=end_line,
            )

            # Convert to dictionaries
            nodes = [meta.to_dict() for meta in matches]

            data = {
                "success": True,
                "tree_id": tree_id,
                "search_type": search_type,
                "matches": nodes,
                "total_matches": len(nodes),
            }

            return SuccessResult(data=data)

        except ValueError as e:
            return ErrorResult(
                message=f"Invalid search parameters: {e}",
                code="INVALID_SEARCH",
                details={"tree_id": tree_id, "search_type": search_type},
            )
        except Exception as e:
            logger.exception("cst_find_node failed: %s", e)
            return ErrorResult(message=f"cst_find_node failed: {e}", code="CST_FIND_ERROR")

    @classmethod
    def metadata(cls: type["CSTFindNodeCommand"]) -> Dict[str, Any]:
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
                "The cst_find_node command finds nodes in a CST tree using two search modes: "
                "simple search (by type, name, position) or XPath-like search (using CSTQuery selectors). "
                "Search is performed on the server using the tree stored in memory, so no need to "
                "transfer the entire tree to the client.\n\n"
                "Operation flow:\n"
                "1. Validates tree_id exists\n"
                "2. Validates search parameters based on search_type\n"
                "3. Performs search on tree stored in memory\n"
                "4. Returns node metadata for matching nodes\n\n"
                "Search Types:\n"
                "1. Simple search (search_type='simple'):\n"
                "   - Filter by node_type (e.g., 'FunctionDef', 'ClassDef')\n"
                "   - Filter by name (exact match)\n"
                "   - Filter by qualname (exact match)\n"
                "   - Filter by line range (start_line, end_line)\n"
                "   - Multiple filters can be combined (AND logic)\n"
                "2. XPath-like search (search_type='xpath'):\n"
                "   - Uses CSTQuery selector syntax\n"
                "   - Supports all CSTQuery features (combinators, predicates, pseudos)\n"
                "   - Examples: class[name=\"MyClass\"], function[name=\"f\"] smallstmt[type=\"Return\"]:first\n"
                "   - See query_cst command metadata for full CSTQuery syntax\n\n"
                "Advantages:\n"
                "- Search is performed on server (no need to transfer tree)\n"
                "- Fast search on full tree structure\n"
                "- Supports complex queries with CSTQuery\n"
                "- Returns only matching nodes (efficient)\n\n"
                "Use cases:\n"
                "- Find specific nodes for modification\n"
                "- Analyze code patterns\n"
                "- Locate nodes by type or name\n"
                "- Complex queries with CSTQuery selectors\n\n"
                "Important notes:\n"
                "- Tree must be loaded first with cst_load_file\n"
                "- XPath search requires query parameter\n"
                "- Simple search can use any combination of filters\n"
                "- Returns node metadata (not full nodes)\n"
                "- Use node_id from results with cst_modify_tree"
            ),
            "parameters": {
                "tree_id": {
                    "description": "Tree ID from cst_load_file command",
                    "type": "string",
                    "required": True,
                },
                "search_type": {
                    "description": (
                        "Search type: 'simple' for basic filters or 'xpath' for CSTQuery selectors. "
                        "Default is 'xpath'."
                    ),
                    "type": "string",
                    "enum": ["simple", "xpath"],
                    "required": False,
                    "default": "xpath",
                },
                "query": {
                    "description": (
                        "CSTQuery selector string (required for xpath search). "
                        "See query_cst command metadata for full syntax and examples."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        'class[name="MyClass"]',
                        'function[name="process"] smallstmt[type="Return"]:first',
                        'smallstmt[type="Return"]',
                    ],
                },
                "node_type": {
                    "description": "Node type filter for simple search (e.g., 'FunctionDef', 'ClassDef', 'If')",
                    "type": "string",
                    "required": False,
                    "examples": ["FunctionDef", "ClassDef", "If", "For", "Try"],
                },
                "name": {
                    "description": "Node name filter for simple search (exact match)",
                    "type": "string",
                    "required": False,
                    "examples": ["main", "process_data", "MyClass"],
                },
                "qualname": {
                    "description": "Qualified name filter for simple search (exact match)",
                    "type": "string",
                    "required": False,
                    "examples": ["MyClass.my_method", "module.function"],
                },
                "start_line": {
                    "description": "Start line filter for simple search (nodes starting at or after this line)",
                    "type": "integer",
                    "required": False,
                    "examples": [10, 20, 50],
                },
                "end_line": {
                    "description": "End line filter for simple search (nodes ending at or before this line)",
                    "type": "integer",
                    "required": False,
                    "examples": [100, 200, 500],
                },
            },
            "return_value": {
                "success": {
                    "description": "Search completed successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "Tree ID that was searched",
                        "search_type": "Search type that was used",
                        "matches": "List of node metadata dictionaries for matching nodes",
                        "total_matches": "Total number of matches found",
                    },
                    "example": {
                        "success": True,
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "xpath",
                        "matches": [
                            {
                                "node_id": "class:MyClass:ClassDef:10:0-50:0",
                                "type": "ClassDef",
                                "kind": "class",
                                "name": "MyClass",
                                "qualname": "MyClass",
                                "start_line": 10,
                                "start_col": 0,
                                "end_line": 50,
                                "end_col": 0,
                                "children_count": 5,
                            }
                        ],
                        "total_matches": 1,
                    },
                },
                "error": {
                    "description": "Search failed",
                    "code": "Error code (e.g., INVALID_SEARCH, CST_FIND_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "XPath search: find class by name",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "xpath",
                        "query": 'class[name="MyClass"]',
                    },
                    "explanation": (
                        "Finds all classes named 'MyClass' using CSTQuery selector. "
                        "Uses XPath-like search with predicate matching."
                    ),
                },
                {
                    "description": "XPath search: find all return statements",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "xpath",
                        "query": 'smallstmt[type="Return"]',
                    },
                    "explanation": (
                        "Finds all return statements in the tree. "
                        "Uses XPath search with type predicate."
                    ),
                },
                {
                    "description": "XPath search: find first return in function",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "xpath",
                        "query": 'function[name="process_data"] smallstmt[type="Return"]:first',
                    },
                    "explanation": (
                        "Finds the first return statement in process_data function. "
                        "Uses descendant combinator and :first pseudo selector."
                    ),
                },
                {
                    "description": "Simple search: find by node type",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "simple",
                        "node_type": "FunctionDef",
                    },
                    "explanation": (
                        "Finds all functions in the tree using simple search. "
                        "Faster than XPath for simple type-based queries."
                    ),
                },
                {
                    "description": "Simple search: find by name",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "simple",
                        "name": "main",
                    },
                    "explanation": (
                        "Finds all nodes named 'main' using simple search. "
                        "Exact match on node name."
                    ),
                },
                {
                    "description": "Simple search: find by qualified name",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "simple",
                        "qualname": "MyClass.my_method",
                    },
                    "explanation": (
                        "Finds method 'my_method' in class 'MyClass' using qualified name. "
                        "Useful for finding specific methods in classes."
                    ),
                },
                {
                    "description": "Simple search: find by line range",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "simple",
                        "start_line": 10,
                        "end_line": 50,
                    },
                    "explanation": (
                        "Finds all nodes that start at or after line 10 and end at or before line 50. "
                        "Useful for finding nodes in a specific line range."
                    ),
                },
                {
                    "description": "Simple search: combine filters",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "search_type": "simple",
                        "node_type": "FunctionDef",
                        "name": "process",
                    },
                    "explanation": (
                        "Finds functions named 'process' using combined filters. "
                        "All filters must match (AND logic)."
                    ),
                },
            ],
            "error_cases": {
                "INVALID_SEARCH": {
                    "description": "Invalid search parameters",
                    "message": "Invalid search parameters: {error details}",
                    "solution": (
                        "Check search parameters:\n"
                        "- For xpath search: query parameter is required\n"
                        "- For simple search: at least one filter should be provided\n"
                        "- search_type must be 'simple' or 'xpath'\n"
                        "See command metadata for parameter requirements."
                    ),
                },
                "CST_FIND_ERROR": {
                    "description": "Error during search",
                    "examples": [
                        {
                            "case": "Tree not found",
                            "message": "cst_find_node failed: Tree not found: {tree_id}",
                            "solution": (
                                "Tree was not loaded or was removed from memory. "
                                "Use cst_load_file to load file into tree first."
                            ),
                        },
                        {
                            "case": "Invalid CSTQuery syntax",
                            "message": "cst_find_node failed: Invalid selector",
                            "solution": (
                                "Check CSTQuery selector syntax. "
                                "See query_cst command metadata for syntax reference."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Use XPath search for complex queries with CSTQuery selectors",
                "Use simple search for basic type/name/position filters (faster)",
                "Tree must be loaded first with cst_load_file",
                "Save node_id from results for use with cst_modify_tree",
                "XPath search supports all CSTQuery features (see query_cst examples)",
                "Simple search filters can be combined (AND logic)",
                "Search is performed on server (efficient, no tree transfer)",
            ],
        }
