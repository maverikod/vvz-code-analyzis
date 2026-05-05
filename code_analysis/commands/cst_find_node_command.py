"""
MCP command: cst_find_node

Find nodes in CST tree using simple or XPath-like queries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""



from __future__ import annotations



import logging


import time


from typing import Any, Dict, Optional



from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult



from .base_mcp_command import BaseMCPCommand


from ..core.cst_tree.tree_finder import find_nodes



logger = logging.getLogger(__name__)
# @node-id: 9e87b68e-d0c8-4206-88dd-0399429f9c80
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
            "4. If include_code=True, enriches each match with its source code\n"
            "5. Returns node metadata for matching nodes\n\n"
            "Search Types:\n"
            "1. Simple search (search_type='simple'):\n"
            "   - Filter by node_type (e.g., 'FunctionDef', 'ClassDef')\n"
            "   - Filter by name (exact match)\n"
            "   - Filter by qualname (exact match)\n"
            "   - Filter by line range (start_line, end_line)\n"
            "   - Multiple filters can be combined (AND logic)\n"
            "2. XPath-like search (search_type='xpath'):\n"
            "   - Uses CSTQuery selector syntax\n"
            "   - Combinators: space (descendant), > (direct child), // (recursive from root)\n"
            "   - Predicates: [attr OP val] or [@attr OP val] — @ prefix is optional\n"
            "     String ops: =, !=, ~= (contains), ^= (starts-with), $= (ends-with)\n"
            "     Numeric ops: >, <, >=, <= on start_line / end_line / children_count\n"
            "   - Pseudos: :first, :last, :nth(N), :not(selector)\n"
            "   - Type wildcard: Def:* matches FunctionDef, ClassDef, etc.\n"
            "   - Attributes: name, qualname, type, kind, start_line, end_line, children_count, module\n"
            "   - Examples:\n"
            "     //FunctionDef[@name='foo']            — recursive search with @ syntax\n"
            "     function[start_line>=50]              — numeric comparison\n"
            "     function[@name^='_']:not([name^='__']) — private but not dunder\n"
            "     class > method:first                  — first direct-child method of each class\n\n"
            "Key flags:\n"
            "- include_code=True: returns source code of each match inline, eliminating "
            "  a separate cst_get_node_info round-trip. Optimal for search+edit workflows.\n"
            "- require_one=True: fails if 0 or >1 matches; returns node_id at top level "
            "  for direct use with cst_modify_tree.\n\n"
            "Advantages:\n"
            "- Search is performed on server (no need to transfer tree)\n"
            "- Fast search on full tree structure\n"
            "- Supports complex queries with CSTQuery\n"
            "- include_code eliminates extra cst_get_node_info call\n"
            "- Returns only matching nodes (efficient)\n\n"
            "Optimal 2-call edit workflow:\n"
            "  1. cst_find_node(query=..., include_code=True) — node_id + current code\n"
            "  2. cst_modify_tree(replace_many: [{node_id, code_lines}]) — done\n"
            "  (vs 3-call: find — get_node_info — modify)\n\n"
            "Important notes:\n"
            "- Tree must be loaded first with cst_load_file\n"
            "- XPath search requires query parameter\n"
            "- Simple search can use any combination of filters\n"
            "- Use node_id from results with cst_modify_tree or cst_get_node_info"
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
                    "CSTQuery selector string (for xpath search). "
                    "Combinators: space (descendant), > (child), // (recursive from root). "
                    "Predicates: [attr OP val] or [@attr OP val] — @ is optional. "
                    "String ops: =, !=, ~= (contains), ^= (starts-with), $= (ends-with). "
                    "Numeric ops: >, <, >=, <= on start_line / end_line / children_count. "
                    "Pseudos: :first, :last, :nth(N), :not(selector). "
                    "Type wildcard: Def:* matches FunctionDef, ClassDef, etc. "
                    "Attributes: name, qualname, type, kind, start_line, end_line, children_count, module."
                ),
                "type": "string",
                "required": False,
                "examples": [
                    "//FunctionDef[@name='foo']",
                    "function[start_line>=50]",
                    "function[@name^='_']:not([name^='__'])",
                    "class > method:first",
                    "Def:*[name='run']",
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
            },
            "end_line": {
                "description": "End line filter for simple search (nodes ending at or before this line)",
                "type": "integer",
                "required": False,
            },
            "require_one": {
                "description": (
                    "If true, require exactly one match. Returns NoMatch error if 0 results, "
                    "NonUniqueMatch error if >1. On success also sets top-level node_id field "
                    "for direct use with cst_modify_tree. Default: false."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "include_code": {
                "description": (
                    "If true, include the source code of each matched node in the response. "
                    "Populates the 'code' field in each match dict. "
                    "Eliminates the need for a separate cst_get_node_info call when you need "
                    "to inspect current code before editing. "
                    "Use in combination with replace_many for optimal 2-call edit flow. "
                    "Default: false."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
        },
        "return_value": {
            "success": {
                "description": "Search completed successfully",
                "data": {
                    "success": "Always True on success",
                    "tree_id": "Tree ID that was searched",
                    "search_type": "Search type that was used",
                    "matches": (
                        "List of node metadata dicts. Each dict contains: node_id, type, kind, "
                        "name, qualname, start_line, start_col, end_line, end_col, children_count, "
                        "children_ids, parent_id. If include_code=True, also contains 'code' with "
                        "the source code of the node."
                    ),
                    "total_matches": "Total number of matches found",
                    "node_id": "(only when require_one=True) node_id of the single match for direct use",
                    "node": "(only when require_one=True) full metadata dict of the single match",
                },
                "example": {
                    "success": True,
                    "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "search_type": "xpath",
                    "total_matches": 1,
                    "matches": [
                        {
                            "node_id": "abc123-...",
                            "type": "FunctionDef",
                            "kind": "function",
                            "name": "add",
                            "qualname": "add",
                            "start_line": 1,
                            "start_col": 0,
                            "end_line": 3,
                            "end_col": 16,
                            "children_count": 8,
                            "code": "def add(a, b):\n    return a + b",
                        }
                    ],
                },
            },
            "error": {
                "description": "Search failed or constraint violated",
                "codes": {
                    "INVALID_SEARCH": "Invalid or missing search parameters",
                    "CST_FIND_ERROR": "Runtime error during search (tree not found, bad selector)",
                    "NoMatch": "require_one=True but 0 nodes matched",
                    "NonUniqueMatch": "require_one=True but >1 nodes matched (includes candidates list)",
                },
            },
        },
        "usage_examples": [
            {
                "description": "Optimal edit flow: find with code, then replace_many",
                "command": {
                    "tree_id": "a1b2c3d4-...",
                    "query": "FunctionDef[name='add']",
                    "include_code": True,
                },
                "explanation": (
                    "Returns node_id AND current code in one call. "
                    "Pass node_id directly to cst_modify_tree replace_many. "
                    "Saves one cst_get_node_info round-trip (~60% token reduction)."
                ),
            },
            {
                "description": "require_one: find exactly one node, get node_id directly",
                "command": {
                    "tree_id": "a1b2c3d4-...",
                    "query": "FunctionDef[name='process']",
                    "require_one": True,
                    "include_code": True,
                },
                "explanation": (
                    "Fails with error if 0 or >1 matches. "
                    "On success: response.node_id is ready for cst_modify_tree."
                ),
            },
            {
                "description": "XPath with // and @: find function anywhere in tree",
                "command": {
                    "tree_id": "a1b2c3d4-...",
                    "query": "//FunctionDef[@name='foo']",
                    "include_code": True,
                },
                "explanation": "// searches recursively from root; @ before attr name is optional.",
            },
            {
                "description": "Numeric predicate: functions starting at line 50+",
                "command": {
                    "tree_id": "a1b2c3d4-...",
                    "query": "function[start_line>=50]",
                },
                "explanation": "Numeric ops >, <, >=, <= compare start_line / end_line / children_count.",
            },
            {
                "description": ":not pseudo: private but not dunder functions",
                "command": {
                    "tree_id": "a1b2c3d4-...",
                    "query": "function[@name^='_']:not([name^='__'])",
                },
                "explanation": ":not(selector) excludes nodes matching the inner selector.",
            },
            {
                "description": "Simple: find by type and name combined",
                "command": {
                    "tree_id": "a1b2c3d4-...",
                    "search_type": "simple",
                    "node_type": "FunctionDef",
                    "name": "process",
                },
                "explanation": "Finds functions named 'process' (AND logic).",
            },
        ],
        "error_cases": {
            "INVALID_SEARCH": {
                "description": "Invalid search parameters",
                "solution": (
                    "For xpath: query parameter is required. "
                    "For simple: provide at least one filter. "
                    "search_type must be 'simple' or 'xpath'."
                ),
            },
            "CST_FIND_ERROR": {
                "description": "Runtime error during search",
                "examples": [
                    {
                        "case": "Tree not found",
                        "solution": "Use cst_load_file first to load the file.",
                    },
                    {
                        "case": "Invalid CSTQuery syntax",
                        "solution": "Check selector syntax: combinators (space/>///), predicates ([attr OP val]), pseudos (:first/:last/:nth/:not).",
                    },
                ],
            },
            "NoMatch": {
                "description": "require_one=True but 0 nodes matched",
                "solution": "Broaden query or check tree_id / file loaded.",
            },
            "NonUniqueMatch": {
                "description": "require_one=True but >1 nodes matched",
                "solution": "Narrow query (add name/type predicates) or use without require_one.",
            },
        },
        "best_practices": [
            "Use include_code=True to get current code inline — avoids extra cst_get_node_info call",
            "Use require_one=True when you expect exactly one match to get node_id at top level",
            "Combine include_code+require_one for safest single-target edit: find then replace_many",
            "XPath: use // for recursive search, @ is optional before attr names",
            "XPath: use >=/<= for numeric comparisons on start_line/end_line/children_count",
            "XPath: use :not(selector) to exclude nodes from results",
            "Use XPath search for structural queries (FunctionDef[name='x'])",
            "Use simple search for broad type scans (all FunctionDef nodes)",
            "Tree must be loaded first with cst_load_file",
            "node_id from results is stable within the session (use with cst_modify_tree)",
        ],
    }