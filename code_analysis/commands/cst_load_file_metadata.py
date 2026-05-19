"""
Metadata for cst_load_file command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_cst_load_file_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for cst_load_file (name, description, params, etc.)."""
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
            "1. Gets project from database using project_id\n"
            "2. Validates project is linked to watch directory\n"
            "3. Gets watch directory path from database\n"
            "4. Forms absolute path: watch_dir_path / project_name / file_path\n"
            "5. Validates file is a .py file\n"
            "6. Validates file exists\n"
            "7. Reads file source code\n"
            "8. Parses source using LibCST\n"
            "9. Builds node index and metadata\n"
            "10. Stores tree in memory with tree_id\n"
            "11. Returns tree_id and node metadata (or declarative overview when return_format=declarative)\n\n"
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
            "Return format:\n"
            "- return_format=full (default): nodes list. return_format=declarative: overview with signatures, docstrings, node_ids, and hidden bodies.\n"
            "- return_format=skeleton remains as a backward-compatible alias to declarative during migration.\n"
            "- selector: optional XPath or list of node_ids; response includes selected_nodes with code.\n\n"
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
            "- Filters reduce returned metadata, but full tree is still stored\n\n"
            "When the file had syntax errors on load:\n"
            "- The server comments out the error lines and adds a placeholder 'pass'\n"
            "- The response includes syntax_errors_fixed: true, commented_lines: [{ line, error, parent_node }], and optionally temp_file\n"
            "- Each commented_lines entry has parent_node (dict with node_id) for the block where the error was found; use it to locate the parent (e.g. function/class)"
        ),
        "parameters": {
            "project_id": {
                "description": "Project ID (UUID4). Project must be linked to a watch directory.",
                "type": "string",
                "required": True,
            },
            "file_path": {
                "description": "Target Python file path (relative to project root). Absolute path is formed as: watch_dir_path / project_name / file_path",
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
            "return_format": {
                "description": "full (default), declarative, or skeleton alias. Declarative returns overview with signatures, docstrings, node_ids, and hidden bodies.",
                "type": "string",
                "required": False,
                "default": "full",
            },
            "selector": {
                "description": (
                    "Optional. XPath string, list of node_ids, or object "
                    '{"query": "<xpath>"} / {"node_ids": ["<uuid>", ...]}; '
                    "response includes selected_nodes with code."
                ),
                "type": "string",
                "required": False,
            },
        },
        "return_value": {
            "success": {
                "description": "File loaded successfully",
                "data": {
                    "success": "Always True on success",
                    "tree_id": "Tree ID for use with other CST commands",
                    "file_path": "Path to loaded file",
                    "nodes": "List of node metadata dictionaries (when return_format=full)",
                    "total_nodes": "Total number of nodes returned (when return_format=full)",
                    "declarative": "Declarative overview text (when return_format=declarative or skeleton alias)",
                    "outline_nodes": "Compact visible structure nodes with node_id, depth, and signature",
                    "selected_nodes": "Optional. When selector set: matching nodes with code.",
                    "syntax_errors_fixed": "Optional. True when file had syntax errors on load; error lines were commented out and a placeholder pass was added.",
                    "commented_lines": "Optional. When syntax_errors_fixed is true: list of { line (1-based), error (message), parent_node (dict with node_id, or null) } for each commented-out error line. parent_node identifies the block (e.g. function/class) where the error was found.",
                    "temp_file": "Optional. When syntax_errors_fixed is true: path to the .tmp file used for the fixed content (for debugging).",
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
                    "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    "file_path": "src/main.py",
                },
                "explanation": (
                    "Loads entire file into CST tree. Returns all nodes with full metadata. "
                    "Absolute path is formed as: watch_dir_path / project_name / src/main.py. "
                    "Use this when you need to work with all nodes in the file."
                ),
            },
            {
                "description": "Load only functions and classes",
                "command": {
                    "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
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
                    "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
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
                    "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    "file_path": "src/utils.py",
                    "include_children": False,
                },
                "explanation": (
                    "Loads file but excludes children_ids from metadata. "
                    "Reduces response size when children information is not needed."
                ),
            },
            {
                "description": "Load declarative overview",
                "command": {
                    "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    "file_path": "src/main.py",
                    "return_format": "declarative",
                },
                "explanation": (
                    "Returns tree_id and declarative overview: signatures, docstrings, node_ids, hidden bodies, "
                    "and compact outline_nodes. Use this as the first model-facing view before requesting full code."
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
            "Always provide project_id - it is required and used to form absolute path",
            "Ensure project is linked to watch directory before using this command",
            "Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')",
            "Use return_format=declarative to get a high-level overview and reduce context size",
            "Use selector (XPath or node_ids) to include selected node content in same call",
            "Use node_types filter to reduce metadata size when only specific types are needed",
            "Use max_depth to limit analysis scope",
            "Set include_children=False if children information is not needed",
            "Save tree_id for use with cst_modify_tree and cst_save_tree",
            "Tree persists in memory until server restart or explicit removal",
        ],
    }
