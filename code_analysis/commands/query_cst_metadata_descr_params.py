"""
query_cst metadata: detailed_description and parameters.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict


def get_detailed_description() -> str:
    """Return the detailed_description text for query_cst metadata."""
    return (
        "The query_cst command queries Python source code using CSTQuery selectors "
        "to locate specific LibCST nodes. It provides a jQuery/XPath-like selector "
        "language for finding nodes while preserving formatting and comments.\n\n"
        "Operation flow:\n"
        "1. Validates root_dir exists and is a directory\n"
        "2. Resolves file_path (absolute or relative to root_dir)\n"
        "3. Validates file is a .py file\n"
        "4. Validates file exists\n"
        "5. Reads file source code\n"
        "6. Parses source using LibCST\n"
        "7. Applies CSTQuery selector to find matching nodes\n"
        "8. Generates node IDs for each match\n"
        "9. Optionally includes code snippets\n"
        "10. Limits results to max_results if specified\n"
        "11. Returns list of matches with metadata\n\n"
        "CSTQuery Selector Syntax:\n"
        "- Selectors are sequences of steps connected by combinators\n"
        "- Descendant combinator: whitespace (A B finds B inside A)\n"
        "- Child combinator: > (A > B finds B as direct child of A)\n"
        "- Each step: TYPE or * with optional predicates and pseudos\n"
        '- Predicates: [attr OP value] (e.g., [name="MyClass"])\n'
        "- Pseudos: :first, :last, :nth(N)\n\n"
        "Supported TYPE Aliases:\n"
        "- module, class, function, method, stmt, smallstmt, import, node\n"
        "- LibCST node class names: If, For, Try, With, Return, Assign, Call, etc.\n\n"
        "Predicate Operators:\n"
        "- = exact equality\n"
        "- != not equal\n"
        "- ~= substring match\n"
        "- ^= prefix match\n"
        "- $= suffix match\n\n"
        "Supported Attributes:\n"
        "- type: LibCST node type\n"
        "- kind: Node kind (stmt, smallstmt, class, function, method, etc.)\n"
        "- name: Node name (for named nodes)\n"
        "- qualname: Qualified name (for methods: ClassName.method)\n"
        "- start_line, end_line: Line numbers\n\n"
        "Node Information:\n"
        "- node_id: Stable-enough identifier (span-based) for compose_cst_module\n"
        "- kind: Node kind classification\n"
        "- type: LibCST node type\n"
        "- name: Node name (if applicable)\n"
        "- qualname: Qualified name (if applicable)\n"
        "- start_line, start_col: Starting position\n"
        "- end_line, end_col: Ending position\n"
        "- code: Code snippet (if include_code=True)\n\n"
        "Use cases:\n"
        "- Find specific nodes by type or name\n"
        "- Locate statements, expressions, or declarations\n"
        "- Discover code patterns\n"
        "- Find nodes for refactoring operations\n"
        "- Analyze code structure\n"
        "- Prepare for compose_cst_module operations\n\n"
        "Typical Workflow (query only):\n"
        "1. Use query_cst to find target nodes\n"
        "2. Get node_id from matches\n"
        "3. Use compose_cst_module with selector kind='node_id' or kind='cst_query'\n"
        "4. Preview diff and compile result\n"
        "5. Apply changes if satisfied\n\n"
        "Replace mode (find + replace in one call):\n"
        "Pass replace_with (string) or code_lines (array of lines). "
        "Optionally match_index (0-based, which match to replace) or replace_all (replace every match). "
        "File is backed up, then updated; database is refreshed. "
        "Response is compact: replaced count, file_path, backup_uuid.\n\n"
        "Important notes:\n"
        "- Selector syntax follows CSTQuery rules (see docs/CST_QUERY.md)\n"
        "- node_id is span-based and stable enough for patch workflows\n"
        "- Results can be truncated if max_results limit is reached\n"
        "- include_code=True can make response large for many matches\n"
        "- Use max_results to limit output size\n"
        "- Line numbers are 1-based\n"
        "- Column numbers are 0-based"
    )


def get_parameters() -> Dict[str, Any]:
    """Return the parameters dict for query_cst metadata."""
    return {
        "root_dir": {
            "description": (
                "Project root directory path. "
                "**RECOMMENDED: Use absolute path for reliability.** "
                "Relative paths are resolved from current working directory, "
                "which may cause issues if working directory changes. "
                "Used to resolve relative file_path."
            ),
            "type": "string",
            "required": True,
            "examples": [
                "/home/user/projects/my_project",  # ✅ RECOMMENDED: Absolute path
                ".",  # ⚠️ Relative path (resolved from CWD)
                "./code_analysis",  # ⚠️ Relative path (resolved from CWD)
            ],
        },
        "file_path": {
            "description": (
                "Target Python file path. "
                "**Can be absolute or relative to root_dir.** "
                "If relative, it is resolved relative to root_dir. "
                "If absolute, it must be within root_dir (or will be normalized). "
                "Must be a .py file."
            ),
            "type": "string",
            "required": True,
            "examples": [
                "code_analysis/core/backup_manager.py",
                "/home/user/projects/my_project/src/main.py",
                "./src/utils.py",
            ],
        },
        "selector": {
            "description": (
                "CSTQuery selector string. Uses jQuery/XPath-like syntax to find nodes. "
                "Required for query-only mode. For replace mode, either selector or both "
                "start_line and end_line are required. "
                "Examples:\n"
                '- class[name="MyClass"] - Find class by name\n'
                '- method[qualname="MyClass.my_method"] - Find method by qualified name\n'
                '- smallstmt[type="Return"] - Find all return statements\n'
                '- function[name="f"] smallstmt[type="Return"]:first - First return in function f\n'
                "See docs/CST_QUERY.md for full syntax documentation."
            ),
            "type": "string",
            "required": False,
            "examples": [
                'class[name="MyClass"]',
                'method[qualname="DataProcessor.process"]',
                'smallstmt[type="Return"]',
                'function[name="process_data"] smallstmt[type="Return"]:first',
            ],
        },
        "include_code": {
            "description": (
                "If True, includes code snippets for each match. "
                "Can make response large for many matches. Default is False."
            ),
            "type": "boolean",
            "required": False,
            "default": False,
            "examples": [False, True],
        },
        "max_results": {
            "description": (
                "Maximum number of matches to return. "
                "If more matches found, results are truncated. "
                "Default is 200. Use -1 for unlimited (not recommended)."
            ),
            "type": "integer",
            "required": False,
            "default": 200,
            "examples": [50, 200, 500],
        },
        "replace_with": {
            "description": (
                "If set, replace the matched node(s) with this code (single string). "
                "Use code_lines for multi-line. One call = find + replace; file is backed up and saved."
            ),
            "type": "string",
            "required": False,
            "examples": ["return None", "pass"],
        },
        "code_lines": {
            "description": (
                "If set, replace the matched node(s) with these lines (joined by newline). "
                "Prefer over replace_with for multi-line code."
            ),
            "type": "array",
            "items": {"type": "string"},
            "required": False,
        },
        "match_index": {
            "description": (
                "When replacing: which match to replace (0-based). Default 0. Ignored if replace_all is true."
            ),
            "type": "integer",
            "required": False,
            "default": 0,
            "examples": [0, 1],
        },
        "replace_all": {
            "description": (
                "When replacing: if true, replace all matches with the same new code. match_index ignored."
            ),
            "type": "boolean",
            "required": False,
            "default": False,
            "examples": [False, True],
        },
        "replacements": {
            "description": (
                "When set: replace multiple matches with different code per match. "
                "List of {match_index, replace_with} or {match_index, code_lines}. "
                "Ignored if replace_with/code_lines (single-code path) is used. "
                "Not supported with range-only replace (start_line/end_line)."
            ),
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "match_index": {"type": "integer"},
                    "replace_with": {"type": "string"},
                    "code_lines": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["match_index"],
            },
            "required": False,
        },
        "start_line": {
            "description": (
                "1-based start line for range-based replace. "
                "Use with end_line and replace_with/code_lines to replace the statement(s) covering that range. "
                "When both start_line and end_line are set, selector is optional."
            ),
            "type": "integer",
            "required": False,
        },
        "end_line": {
            "description": (
                "1-based end line for range-based replace. Must be >= start_line. "
                "When both start_line and end_line are set, replace that line range."
            ),
            "type": "integer",
            "required": False,
        },
        "preview": {
            "description": (
                "If true, run replace in memory and return diff and modified_source without writing. "
                "No backup, no file change."
            ),
            "type": "boolean",
            "required": False,
            "default": False,
        },
        "dry_run": {
            "description": "Alias for preview. If true, same as preview=true.",
            "type": "boolean",
            "required": False,
            "default": False,
        },
    }
