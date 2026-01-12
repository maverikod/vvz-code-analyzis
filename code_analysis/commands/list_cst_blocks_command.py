"""
MCP command: list_cst_blocks

Lists logical blocks (functions/classes/methods) with stable ids and exact line ranges.
Designed to be paired with compose_cst_module.

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
from ..core.cst_module import list_cst_blocks

logger = logging.getLogger(__name__)


class ListCSTBlocksCommand(BaseMCPCommand):
    name = "list_cst_blocks"
    version = "1.0.0"
    descr = "List replaceable CST logical blocks (functions/classes/methods) with ids and ranges"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID (UUID4). If provided, root_dir will be resolved from database. Either project_id or root_dir must be provided.",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory. Required if project_id is not provided.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (relative to project root)",
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        file_path: str,
        project_id: Optional[str] = None,
        root_dir: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._resolve_project_root(project_id=project_id, root_dir=root_dir)
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
            blocks = list_cst_blocks(source)
            data = {
                "success": True,
                "file_path": str(target),
                "blocks": [
                    {
                        "id": b.block_id,
                        "kind": b.kind,
                        "qualname": b.qualname,
                        "start_line": b.start_line,
                        "end_line": b.end_line,
                    }
                    for b in blocks
                ],
            }
            return SuccessResult(data=data)
        except Exception as e:
            logger.exception("list_cst_blocks failed: %s", e)
            return ErrorResult(
                message=f"list_cst_blocks failed: {e}", code="CST_LIST_ERROR"
            )

    @classmethod
    def metadata(cls: type["ListCSTBlocksCommand"]) -> Dict[str, Any]:
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
                "The list_cst_blocks command lists logical blocks (functions, classes, methods) "
                "in a Python file with stable IDs and exact line ranges. These blocks can be "
                "used with compose_cst_module for safe refactoring operations.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Resolves file_path (absolute or relative to root_dir)\n"
                "3. Validates file is a .py file\n"
                "4. Validates file exists\n"
                "5. Reads file source code\n"
                "6. Parses source using LibCST\n"
                "7. Extracts logical blocks (functions, classes, methods)\n"
                "8. Generates stable block IDs for each block\n"
                "9. Returns list of blocks with metadata\n\n"
                "Logical Blocks:\n"
                "- Top-level functions: Functions defined at module level\n"
                "- Top-level classes: Classes defined at module level\n"
                "- Class methods: Methods defined inside classes (qualified name: ClassName.method)\n"
                "- Blocks are identified by their logical structure, not just syntax\n\n"
                "Block ID Format:\n"
                "- Format: `kind:qualname:start_line-end_line`\n"
                "- Example: `function:process_data:10-25`\n"
                "- Example: `class:MyClass:30-100`\n"
                "- Example: `method:MyClass.process:45-60`\n"
                "- Stable enough for edit workflows (if code moves, refresh via list_cst_blocks)\n\n"
                "Block Information:\n"
                "- id: Stable block identifier (use with compose_cst_module)\n"
                "- kind: Block type (function, class, method)\n"
                "- qualname: Qualified name (function name, class name, or ClassName.method)\n"
                "- start_line: Starting line number (1-based)\n"
                "- end_line: Ending line number (1-based, inclusive)\n\n"
                "Use cases:\n"
                "- Discover code structure before refactoring\n"
                "- Get stable IDs for compose_cst_module operations\n"
                "- Find functions, classes, and methods in a file\n"
                "- Understand file organization\n"
                "- Prepare for safe code modifications\n\n"
                "Typical Workflow:\n"
                "1. Run list_cst_blocks to discover blocks\n"
                "2. Pick block_id from results\n"
                "3. Use compose_cst_module with selector kind='block_id'\n"
                "4. Preview diff and compile result\n"
                "5. Apply changes if satisfied\n\n"
                "Important notes:\n"
                "- Only lists logical blocks (functions, classes, methods)\n"
                "- Block IDs are stable but refresh if code structure changes\n"
                "- Line numbers are 1-based and inclusive\n"
                "- Methods are listed with qualified names (ClassName.method)\n"
                "- Nested functions/classes inside methods are not listed separately\n"
                "- Use query_cst for more granular node discovery"
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
            },
            "usage_examples": [
                {
                    "description": "List blocks in a Python file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Lists all logical blocks (functions, classes, methods) in main.py "
                        "with stable IDs and line ranges."
                    ),
                },
                {
                    "description": "Discover file structure before refactoring",
                    "command": {
                        "root_dir": ".",
                        "file_path": "code_analysis/core/backup_manager.py",
                    },
                    "explanation": (
                        "Lists blocks to understand file structure before using compose_cst_module."
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
                "CST_LIST_ERROR": {
                    "description": "Error during block listing",
                    "examples": [
                        {
                            "case": "Syntax error in source file",
                            "message": "list_cst_blocks failed: SyntaxError",
                            "solution": (
                                "Fix syntax errors in the file. "
                                "LibCST requires valid Python syntax to parse."
                            ),
                        },
                        {
                            "case": "File encoding error",
                            "message": "list_cst_blocks failed: UnicodeDecodeError",
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
                    "description": "Blocks listed successfully",
                    "data": {
                        "success": "Always True on success",
                        "file_path": "Path to analyzed file",
                        "blocks": (
                            "List of block dictionaries. Each contains:\n"
                            "- id: Stable block identifier (use with compose_cst_module)\n"
                            "- kind: Block type (function, class, method)\n"
                            "- qualname: Qualified name\n"
                            "- start_line: Starting line number (1-based)\n"
                            "- end_line: Ending line number (1-based, inclusive)"
                        ),
                    },
                    "example": {
                        "success": True,
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "blocks": [
                            {
                                "id": "function:process_data:10-25",
                                "kind": "function",
                                "qualname": "process_data",
                                "start_line": 10,
                                "end_line": 25,
                            },
                            {
                                "id": "class:DataProcessor:30-100",
                                "kind": "class",
                                "qualname": "DataProcessor",
                                "start_line": 30,
                                "end_line": 100,
                            },
                            {
                                "id": "method:DataProcessor.process:45-60",
                                "kind": "method",
                                "qualname": "DataProcessor.process",
                                "start_line": 45,
                                "end_line": 60,
                            },
                        ],
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., INVALID_FILE, FILE_NOT_FOUND, CST_LIST_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "best_practices": [
                "Use list_cst_blocks before compose_cst_module to discover blocks",
                "Save block IDs for use in compose_cst_module operations",
                "Refresh block list if file structure changes significantly",
                "Use block IDs with compose_cst_module selector kind='block_id'",
                "Check start_line and end_line to understand block boundaries",
                "Use qualname to identify specific methods (ClassName.method)",
                "Combine with query_cst for more granular node discovery",
                "Use this as first step in refactoring workflow",
            ],
        }
