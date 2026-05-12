"""
Metadata for list_cst_blocks MCP command (AI / help / docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_list_cst_blocks_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return rich command metadata for list_cst_blocks."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "The list_cst_blocks command lists logical blocks (functions, classes, methods) "
            "in a Python file with stable IDs and exact line ranges. Block IDs match the "
            "CST module patcher (`kind:qualname:start_line-end_line`) and can be used with "
            "selectors in cst_apply_buffer / compose-style flows, or cross-checked with "
            "query_cst and cst_load_file for finer CST nodes.\n\n"
            "Operation flow:\n"
            "1. Opens database and resolves project_id\n"
            "2. Resolves file_path to an absolute path under the project root (same rules as "
            "other project-scoped file commands)\n"
            "3. Validates suffix is .py (case-insensitive)\n"
            "4. Validates the file exists on disk\n"
            "5. Acquires a file lock, reads UTF-8 source\n"
            "6. Parses with LibCST via core.cst_module.list_cst_blocks\n"
            "7. Returns blocks with id, block_id, kind, qualname, start_line, end_line plus "
            "total_blocks\n\n"
            "Logical blocks:\n"
            "- Top-level functions (module body)\n"
            "- Top-level classes\n"
            "- Direct methods on class bodies (qualified name ClassName.method)\n"
            "- Nested functions inside methods are not expanded as separate rows\n\n"
            "Block ID format:\n"
            "- `function:name:start-end`, `class:Name:start-end`, `method:Class.method:start-end`\n"
            "- Refresh the list after large edits so line ranges stay accurate\n\n"
            "Use cases:\n"
            "- Map file structure before refactors or patches\n"
            "- Obtain stable block_id strings for block_id selectors\n"
            "- Compare with query_cst for UUID-based node workflows\n\n"
            "Important notes:\n"
            "- Line numbers are 1-based and inclusive\n"
            "- Invalid Python syntax yields CST_PARSE_ERROR (LibCST parser), not a partial list\n"
            "- This command does not load a CST session tree_id; use cst_load_file when you need "
            "in-memory trees and node_id UUIDs"
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID4 (from list_projects / create_project). Required to resolve "
                    "file_path relative to the project root."
                ),
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "file_path": {
                "description": (
                    "Project-relative path to a .py file. Wildcards are not allowed. "
                    "Resolved through the same path pipeline as cst_load_file / universal_file_*."
                ),
                "type": "string",
                "required": True,
                "examples": [
                    "code_analysis/core/backup_manager.py",
                    "src/main.py",
                ],
            },
        },
        "return_value": {
            "success": {
                "description": "Blocks listed successfully.",
                "data": {
                    "success": "Always True on success.",
                    "file_path": "Absolute path to the analyzed file.",
                    "total_blocks": "Integer count of returned blocks.",
                    "blocks": (
                        "Array of objects, each with:\n"
                        "- id: Stable block id (same as block_id)\n"
                        "- block_id: Same string; use with block_id / range-style selectors\n"
                        "- kind: function | class | method\n"
                        "- qualname: Simple name or ClassName.method\n"
                        "- start_line, end_line: 1-based inclusive line span"
                    ),
                },
                "example": {
                    "success": True,
                    "file_path": "/home/user/projects/my_project/src/main.py",
                    "total_blocks": 3,
                    "blocks": [
                        {
                            "id": "function:process_data:10-25",
                            "block_id": "function:process_data:10-25",
                            "kind": "function",
                            "qualname": "process_data",
                            "start_line": 10,
                            "end_line": 25,
                        },
                        {
                            "id": "class:DataProcessor:30-100",
                            "block_id": "class:DataProcessor:30-100",
                            "kind": "class",
                            "qualname": "DataProcessor",
                            "start_line": 30,
                            "end_line": 100,
                        },
                        {
                            "id": "method:DataProcessor.process:45-60",
                            "block_id": "method:DataProcessor.process:45-60",
                            "kind": "method",
                            "qualname": "DataProcessor.process",
                            "start_line": 45,
                            "end_line": 60,
                        },
                    ],
                },
            },
            "error": {
                "description": "Command failed after validation or during parse/read.",
                "code": (
                    "Machine-readable code: INVALID_FILE, FILE_NOT_FOUND, CST_PARSE_ERROR, "
                    "CST_LIST_ERROR, or validation errors from the schema."
                ),
                "message": "Human-readable message.",
                "details": "Optional dict with file_path, error text, or field hints.",
            },
        },
        "usage_examples": [
            {
                "description": "List blocks in a module under a registered project",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "code_analysis/core/backup_manager.py",
                },
                "explanation": (
                    "Returns every top-level function/class and class methods with stable ids "
                    "for planning edits or matching compose_cst / cst_apply_buffer selectors."
                ),
            },
            {
                "description": "Discover structure before a buffer-based patch",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "src/main.py",
                },
                "explanation": (
                    "Use the returned block_id values to align selector kinds (function, class, "
                    "method, block_id) with the CST patch pipeline."
                ),
            },
        ],
        "error_cases": {
            "INVALID_FILE": {
                "description": "Path is not a .py file (wrong suffix).",
                "message": "list_cst_blocks only supports .py files",
                "solution": "Pass a Python source path relative to the project root.",
            },
            "FILE_NOT_FOUND": {
                "description": "Resolved path does not exist or is not accessible.",
                "message": "File not found",
                "solution": (
                    "Verify file_path with list_project_files; ensure project_id matches the "
                    "project root you expect."
                ),
            },
            "CST_PARSE_ERROR": {
                "description": "LibCST could not parse the file (syntax error).",
                "message": "Syntax error in Python source: …",
                "solution": (
                    "Fix syntax (or use replace_file_lines / cst_load_file recovery flows). "
                    "list_cst_blocks requires parseable Python."
                ),
            },
            "CST_LIST_ERROR": {
                "description": "Unexpected failure while reading or listing blocks.",
                "message": "list_cst_blocks failed: …",
                "solution": (
                    "Inspect server logs; check permissions, encoding (UTF-8 expected), and "
                    "disk health."
                ),
            },
            "VALIDATION_ERROR": {
                "description": "Missing or invalid RPC parameters.",
                "message": "Schema validation failed (e.g. missing project_id).",
                "solution": "Use help(list_cst_blocks) / OpenAPI schema and resend a valid payload.",
            },
        },
        "best_practices": [
            "Call list_cst_blocks before planning cst_apply_buffer or compose_cst operations "
            "that target whole functions/classes.",
            "Prefer project_id + relative file_path over ad-hoc absolute paths outside the project.",
            "Re-run list_cst_blocks after large edits so line ranges and ids stay aligned with disk.",
            "Pair with query_cst when you need UUID node_id values instead of logical block ids.",
            "Use qualname to disambiguate methods (ClassName.method).",
            "Do not assume nested inner functions appear as separate blocks—they are omitted by design.",
            "Keep files UTF-8; non-UTF8 may surface as CST_LIST_ERROR during read.",
        ],
    }
