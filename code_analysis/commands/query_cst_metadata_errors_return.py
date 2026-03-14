"""
query_cst metadata: error_cases, return_value, best_practices.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List


def get_error_cases() -> Dict[str, Any]:
    """Return the error_cases dict for query_cst metadata."""
    return {
        "INVALID_FILE": {
            "description": "File is not a Python file",
            "message": "Target file must be a .py file",
            "solution": "Ensure file_path points to a .py file",
        },
        "FILE_NOT_FOUND": {
            "description": "File does not exist",
            "message": "Target file does not exist",
            "solution": "Verify file_path is correct and file exists",
        },
        "CST_QUERY_PARSE_ERROR": {
            "description": "Invalid selector syntax",
            "message": "Invalid selector: {error details}",
            "solution": (
                "Check selector syntax. Ensure:\n"
                '- Predicate requires operator and value: use [name="x"] not [name] (bare [attr] is invalid)\n'
                "- Proper predicate syntax: [attr OP value] with OP one of =, !=, ~=, ^=, $=\n"
                "- Valid pseudos: :first, :last, :nth(N)\n"
                "- Proper combinator usage: whitespace or >\n"
                "See docs/CST_QUERY.md for syntax reference."
            ),
        },
        "CST_QUERY_ERROR": {
            "description": "Error during query execution",
            "examples": [
                {
                    "case": "Syntax error in source file",
                    "message": "query_cst failed: SyntaxError",
                    "solution": (
                        "Fix syntax errors in the file. "
                        "LibCST requires valid Python syntax to parse."
                    ),
                },
                {
                    "case": "File encoding error",
                    "message": "query_cst failed: UnicodeDecodeError",
                    "solution": (
                        "Ensure file is UTF-8 encoded. "
                        "Check file encoding and convert if needed."
                    ),
                },
            ],
        },
        "CST_QUERY_NO_MATCH": {
            "description": "Selector matched no nodes (replace mode only)",
            "message": "No matches found for selector; nothing to replace",
            "solution": "Verify selector matches at least one node in the file",
        },
        "CST_QUERY_MATCH_INDEX": {
            "description": "match_index out of range (replace mode only)",
            "message": "match_index {n} out of range (selector matched {m} node(s))",
            "solution": "Use match_index between 0 and (match_count - 1), or use replace_all",
        },
        "CST_REPLACE_ERROR": {
            "description": "Replace failed (e.g. unsupported node kind or parse error)",
            "message": "From CSTModulePatchError",
            "solution": "Ensure new code is valid Python; replace supports stmt/smallstmt/function/class/method",
        },
        "CST_QUERY_REPLACEMENTS_DUPLICATE_INDEX": {
            "description": "Duplicate match_index in replacements list",
            "message": "Duplicate match_index {n} in replacements",
            "solution": "Use each match_index at most once in replacements",
        },
        "CST_QUERY_REPLACEMENTS_MISSING_CODE": {
            "description": "Replacements entry has neither replace_with nor code_lines",
            "message": "replacements entry must have replace_with or code_lines",
            "solution": "Provide replace_with (string) or code_lines (array of strings)",
        },
        "CST_QUERY_REPLACEMENTS_BOTH_CODE": {
            "description": "Replacements entry has both replace_with and code_lines",
            "message": "replacements entry must have either replace_with or code_lines, not both",
            "solution": "Use only one of replace_with or code_lines per entry",
        },
    }


def get_return_value() -> Dict[str, Any]:
    """Return the return_value dict for query_cst metadata."""
    return {
        "success": {
            "description": "Query executed successfully",
            "data": {
                "success": "Always True on success",
                "file_path": "Path to queried file",
                "selector": "Selector string that was used",
                "truncated": "True if results were truncated due to max_results",
                "matches": (
                    "List of match dictionaries. Each contains:\n"
                    "- node_id: Stable identifier for compose_cst_module\n"
                    "- kind: Node kind (stmt, smallstmt, class, function, method, etc.)\n"
                    "- type: LibCST node type (If, Return, ClassDef, FunctionDef, etc.)\n"
                    "- name: Node name (if applicable)\n"
                    "- qualname: Qualified name (if applicable)\n"
                    "- start_line, start_col: Starting position (1-based line, 0-based col)\n"
                    "- end_line, end_col: Ending position (1-based line, 0-based col)\n"
                    "- code: Code snippet (if include_code=True)"
                ),
                "replace_response": (
                    "When replace_with or code_lines is used, success data contains:\n"
                    "- replaced: Number of nodes replaced\n"
                    "- removed: Number of nodes removed (empty new_code)\n"
                    "- file_path: Path to modified file\n"
                    "- backup_uuid: Backup identifier (if backup was created)"
                ),
            },
            "example": {
                "success": True,
                "file_path": "/home/user/projects/my_project/src/main.py",
                "selector": 'class[name="DataProcessor"]',
                "truncated": False,
                "matches": [
                    {
                        "node_id": "class:DataProcessor:30-100",
                        "kind": "class",
                        "type": "ClassDef",
                        "name": "DataProcessor",
                        "qualname": "DataProcessor",
                        "start_line": 30,
                        "start_col": 0,
                        "end_line": 100,
                        "end_col": 0,
                        "code": "class DataProcessor:\n    ...",
                    }
                ],
            },
            "example_multiple": {
                "success": True,
                "file_path": "/home/user/projects/my_project/src/utils.py",
                "selector": 'smallstmt[type="Return"]',
                "truncated": False,
                "matches": [
                    {
                        "node_id": "smallstmt:Return:15-15",
                        "kind": "smallstmt",
                        "type": "Return",
                        "name": None,
                        "qualname": None,
                        "start_line": 15,
                        "start_col": 4,
                        "end_line": 15,
                        "end_col": 12,
                    },
                    {
                        "node_id": "smallstmt:Return:25-25",
                        "kind": "smallstmt",
                        "type": "Return",
                        "name": None,
                        "qualname": None,
                        "start_line": 25,
                        "start_col": 4,
                        "end_line": 25,
                        "end_col": 12,
                    },
                ],
            },
        },
        "error": {
            "description": "Command failed",
            "code": (
                "Error code (e.g., INVALID_FILE, FILE_NOT_FOUND, "
                "CST_QUERY_PARSE_ERROR, CST_QUERY_ERROR, CST_QUERY_NO_MATCH, "
                "CST_QUERY_MATCH_INDEX, CST_REPLACE_ERROR)"
            ),
            "message": "Human-readable error message",
            "details": "Additional error information (if available)",
        },
    }


def get_best_practices() -> List[str]:
    """Return the best_practices list for query_cst metadata."""
    return [
        "For find+replace in one call: pass replace_with or code_lines (and optionally match_index or replace_all)",
        "Use query_cst to find specific nodes before compose_cst_module",
        "Save node_id from matches for use in compose_cst_module",
        "Use include_code=True only when needed (can be large)",
        "Set max_results to limit output size for broad queries",
        "Check truncated field to see if results were limited",
        "Use specific selectors to find exact nodes",
        "Combine selectors with combinators for complex queries",
        "Use pseudos (:first, :last, :nth) to select specific matches",
        "See docs/CST_QUERY.md for selector syntax reference",
        "Use node_id with compose_cst_module selector kind='node_id'",
        "Or use selector directly with compose_cst_module kind='cst_query'",
    ]
