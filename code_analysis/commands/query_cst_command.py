"""
MCP command: query_cst

Find LibCST nodes by CSTQuery selector.

This command is designed for "logical block" refactor workflows:
- discover target nodes with `query_cst`
- patch modules with `compose_cst_module` using `node_id` (or `cst_query`) selectors

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.exceptions import QueryParseError
from ..cst_query import query_source

logger = logging.getLogger(__name__)


class QueryCSTCommand(BaseMCPCommand):
    name = "query_cst"
    version = "1.0.0"
    descr = "Query python source using CSTQuery selectors (LibCST)"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (relative to project root)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSTQuery selector string",
                },
                "include_code": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include code snippets for each match (can be large)",
                },
                "max_results": {
                    "type": "integer",
                    "default": 200,
                    "description": "Maximum number of matches to return",
                },
            },
            "required": ["project_id", "file_path", "selector"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        selector: str,
        include_code: bool = False,
        max_results: int = 200,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._resolve_project_root(project_id)
            target = root_path / file_path
            target = target.resolve()

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

            source = target.read_text(encoding="utf-8")
            matches = query_source(source, selector, include_code=include_code)
            truncated = False
            if max_results >= 0 and len(matches) > max_results:
                matches = matches[:max_results]
                truncated = True

            data = {
                "success": True,
                "file_path": str(target),
                "selector": selector,
                "truncated": truncated,
                "matches": [
                    {
                        "node_id": m.node_id,
                        "kind": m.kind,
                        "type": m.node_type,
                        "name": m.name,
                        "qualname": m.qualname,
                        "start_line": m.start_line,
                        "start_col": m.start_col,
                        "end_line": m.end_line,
                        "end_col": m.end_col,
                        "code": m.code,
                    }
                    for m in matches
                ],
            }
            return SuccessResult(data=data)
        except QueryParseError as e:
            return ErrorResult(
                message=f"Invalid selector: {e}",
                code="CST_QUERY_PARSE_ERROR",
                details={"selector": selector},
            )
        except Exception as e:
            logger.exception("query_cst failed: %s", e)
            return ErrorResult(message=f"query_cst failed: {e}", code="CST_QUERY_ERROR")

    @classmethod
    def metadata(cls: type["QueryCSTCommand"]) -> Dict[str, Any]:
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
                "Typical Workflow:\n"
                "1. Use query_cst to find target nodes\n"
                "2. Get node_id from matches\n"
                "3. Use compose_cst_module with selector kind='node_id' or kind='cst_query'\n"
                "4. Preview diff and compile result\n"
                "5. Apply changes if satisfied\n\n"
                "Important notes:\n"
                "- Selector syntax follows CSTQuery rules (see docs/CST_QUERY.md)\n"
                "- node_id is span-based and stable enough for patch workflows\n"
                "- Results can be truncated if max_results limit is reached\n"
                "- include_code=True can make response large for many matches\n"
                "- Use max_results to limit output size\n"
                "- Line numbers are 1-based\n"
                "- Column numbers are 0-based"
            ),
            "parameters": {
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
                        "Examples:\n"
                        '- class[name="MyClass"] - Find class by name\n'
                        '- method[qualname="MyClass.my_method"] - Find method by qualified name\n'
                        '- smallstmt[type="Return"] - Find all return statements\n'
                        '- function[name="f"] smallstmt[type="Return"]:first - First return in function f\n'
                        "See docs/CST_QUERY.md for full syntax documentation."
                    ),
                    "type": "string",
                    "required": True,
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
            },
            "usage_examples": [
                {
                    "description": "Find class by exact name",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'class[name="MyClass"]',
                    },
                    "explanation": (
                        "Finds all classes named exactly 'MyClass' in main.py. "
                        "Returns node_id that can be used with compose_cst_module."
                    ),
                },
                {
                    "description": "Find class by name prefix",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models.py",
                        "selector": 'class[name^="Base"]',
                    },
                    "explanation": (
                        "Finds all classes whose names start with 'Base' (e.g., BaseModel, BaseView). "
                        "Uses prefix match operator (^=)."
                    ),
                },
                {
                    "description": "Find class by name suffix",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/handlers.py",
                        "selector": 'class[name$="Handler"]',
                    },
                    "explanation": (
                        "Finds all classes whose names end with 'Handler' (e.g., RequestHandler, EventHandler). "
                        "Uses suffix match operator ($=)."
                    ),
                },
                {
                    "description": "Find class by name substring",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/services.py",
                        "selector": 'class[name~="Service"]',
                    },
                    "explanation": (
                        "Finds all classes whose names contain 'Service' (e.g., UserService, PaymentService). "
                        "Uses substring match operator (~=)."
                    ),
                },
                {
                    "description": "Find all return statements",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/utils.py",
                        "selector": 'smallstmt[type="Return"]',
                    },
                    "explanation": (
                        "Finds all return statements in utils.py. "
                        "Useful for analyzing control flow and finding early returns."
                    ),
                },
                {
                    "description": "Find all return statements with code",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/utils.py",
                        "selector": 'smallstmt[type="Return"]',
                        "include_code": True,
                    },
                    "explanation": (
                        "Finds all return statements and includes their code snippets. "
                        "Useful for analyzing what values are being returned."
                    ),
                },
                {
                    "description": "Find first return in specific function",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'function[name="process_data"] smallstmt[type="Return"]:first',
                        "include_code": True,
                    },
                    "explanation": (
                        "Finds the first return statement in process_data function. "
                        "Uses descendant combinator (whitespace) and :first pseudo. "
                        "Includes code snippet in response."
                    ),
                },
                {
                    "description": "Find last return in function",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'function[name="process_data"] smallstmt[type="Return"]:last',
                    },
                    "explanation": (
                        "Finds the last return statement in process_data function. "
                        "Uses :last pseudo selector."
                    ),
                },
                {
                    "description": "Find nth return statement (0-based)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'function[name="process_data"] smallstmt[type="Return"]:nth(1)',
                    },
                    "explanation": (
                        "Finds the second return statement (index 1, 0-based) in process_data function. "
                        "Uses :nth(N) pseudo selector."
                    ),
                },
                {
                    "description": "Find method by qualified name",
                    "command": {
                        "root_dir": ".",
                        "file_path": "code_analysis/core/backup_manager.py",
                        "selector": 'method[qualname="BackupManager.restore_file"]',
                        "include_code": True,
                    },
                    "explanation": (
                        "Finds restore_file method in BackupManager class using qualified name. "
                        "Qualified name format: ClassName.method_name. "
                        "Includes code snippet in response."
                    ),
                },
                {
                    "description": "Find all methods in a class",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models.py",
                        "selector": 'class[name="UserModel"] method',
                    },
                    "explanation": (
                        "Finds all methods inside UserModel class. "
                        "Uses descendant combinator (whitespace) to find methods at any depth."
                    ),
                },
                {
                    "description": "Find direct child methods only",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models.py",
                        "selector": 'class[name="UserModel"] > method',
                    },
                    "explanation": (
                        "Finds only direct child methods of UserModel class (not nested methods). "
                        "Uses child combinator (>) to find only direct children."
                    ),
                },
                {
                    "description": "Find all functions",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/utils.py",
                        "selector": "function",
                    },
                    "explanation": (
                        "Finds all top-level functions (not methods) in utils.py. "
                        "Returns all function definitions at module level."
                    ),
                },
                {
                    "description": "Find functions by name prefix",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/utils.py",
                        "selector": 'function[name^="get_"]',
                    },
                    "explanation": (
                        "Finds all functions whose names start with 'get_' (e.g., get_user, get_data). "
                        "Useful for finding getter functions."
                    ),
                },
                {
                    "description": "Find functions by name pattern",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/utils.py",
                        "selector": 'function[name~="test"]',
                    },
                    "explanation": (
                        "Finds all functions whose names contain 'test' (e.g., test_user, run_tests). "
                        "Uses substring match operator (~=)."
                    ),
                },
                {
                    "description": "Find all if statements",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'stmt[type="If"]',
                    },
                    "explanation": (
                        "Finds all if statements in main.py. "
                        "Uses type attribute to match LibCST node type 'If'."
                    ),
                },
                {
                    "description": "Find all for loops",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'stmt[type="For"]',
                    },
                    "explanation": (
                        "Finds all for loops in main.py. "
                        "Uses type attribute to match LibCST node type 'For'."
                    ),
                },
                {
                    "description": "Find all try statements",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'stmt[type="Try"]',
                    },
                    "explanation": (
                        "Finds all try-except blocks in main.py. "
                        "Useful for analyzing error handling patterns."
                    ),
                },
                {
                    "description": "Find all with statements",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'stmt[type="With"]',
                    },
                    "explanation": (
                        "Finds all with statements (context managers) in main.py. "
                        "Useful for analyzing resource management."
                    ),
                },
                {
                    "description": "Find all import statements",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": "import",
                    },
                    "explanation": (
                        "Finds all import statements (both 'import' and 'from ... import'). "
                        "Uses 'import' kind alias."
                    ),
                },
                {
                    "description": "Find all assignments",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'smallstmt[type="Assign"]',
                    },
                    "explanation": (
                        "Finds all assignment statements in main.py. "
                        "Uses smallstmt kind and Assign type."
                    ),
                },
                {
                    "description": "Find all function calls",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'node[type="Call"]',
                    },
                    "explanation": (
                        "Finds all function call expressions in main.py. "
                        "Uses 'node' kind to match any node type, filters by Call type."
                    ),
                },
                {
                    "description": "Find nodes by line range",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'node[start_line>=10][end_line<=20]',
                    },
                    "explanation": (
                        "Finds all nodes that start at or after line 10 and end at or before line 20. "
                        "Note: Line number predicates use string comparison, so '10' < '2' lexicographically. "
                        "For numeric ranges, consider using multiple queries or filtering results."
                    ),
                },
                {
                    "description": "Find all statements (any type)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": "stmt",
                    },
                    "explanation": (
                        "Finds all statement nodes (if, for, while, try, with, etc.) in main.py. "
                        "Uses 'stmt' kind alias."
                    ),
                },
                {
                    "description": "Find all small statements",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": "smallstmt",
                    },
                    "explanation": (
                        "Finds all small statement nodes (return, break, continue, pass, assign, etc.) in main.py. "
                        "Uses 'smallstmt' kind alias."
                    ),
                },
                {
                    "description": "Find any node type (wildcard)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": "*",
                    },
                    "explanation": (
                        "Finds all nodes in main.py. "
                        "Uses wildcard (*) to match any node type. "
                        "Warning: This can return a very large number of results."
                    ),
                },
                {
                    "description": "Complex query: return in if inside function",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'function[name="process"] stmt[type="If"] smallstmt[type="Return"]',
                    },
                    "explanation": (
                        "Finds return statements inside if statements inside process function. "
                        "Uses multiple descendant combinators to navigate the tree structure."
                    ),
                },
                {
                    "description": "Complex query: method calls in specific class",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'class[name="DataProcessor"] node[type="Call"]',
                    },
                    "explanation": (
                        "Finds all function calls inside DataProcessor class. "
                        "Uses descendant combinator to find calls at any depth."
                    ),
                },
                {
                    "description": "Find nodes excluding specific type",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "selector": 'stmt[type!="Pass"]',
                    },
                    "explanation": (
                        "Finds all statements except Pass statements. "
                        "Uses not equal operator (!=) to exclude specific type."
                    ),
                },
                {
                    "description": "Find methods not matching name pattern",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models.py",
                        "selector": 'method[name!="__init__"]',
                    },
                    "explanation": (
                        "Finds all methods except __init__. "
                        "Uses not equal operator (!=) to exclude specific method."
                    ),
                },
            ],
            "error_cases": {
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
                        "- Proper predicate syntax: [attr OP value]\n"
                        "- Valid operators: =, !=, ~=, ^=, $=\n"
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
            },
            "return_value": {
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
                        "CST_QUERY_PARSE_ERROR, CST_QUERY_ERROR)"
                    ),
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "best_practices": [
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
            ],
        }
