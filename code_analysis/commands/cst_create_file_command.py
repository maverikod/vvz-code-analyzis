"""
MCP command: cst_create_file

Create a new Python file with docstring and return tree_id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_builder import create_tree_from_code
from ..core.cst_tree.tree_saver import save_tree_to_file

logger = logging.getLogger(__name__)


class CSTCreateFileCommand(BaseMCPCommand):
    """Create a new Python file with docstring."""

    name = "cst_create_file"
    version = "1.0.0"
    descr = "Create a new Python file with docstring and return tree_id"
    category = "cst"
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
                    "description": "Project ID (UUID4). Required.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target Python file path (relative to project root). File must not exist.",
                },
                "docstring": {
                    "type": "string",
                    "description": (
                        "File-level docstring (required). Will be automatically formatted as triple-quoted string "
                        "if not already formatted. Must not be empty."
                    ),
                },
            },
            "required": ["project_id", "file_path", "docstring"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        docstring: str,
        **kwargs,
    ) -> SuccessResult:
        """
        Create a new Python file with docstring.

        Process:
        1. Validate project exists
        2. Resolve absolute file path
        3. Check file doesn't exist
        4. Format docstring as triple-quoted string
        5. Create CST tree from docstring code
        6. Save tree to file (creates file on disk and in database)
        7. Return tree_id

        Args:
            project_id: Project ID
            file_path: File path relative to project root
            docstring: File-level docstring

        Returns:
            SuccessResult with tree_id and file_path
        """
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                # Get project to resolve path
                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project {project_id} not found",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )

                if not project.watch_dir_id:
                    return ErrorResult(
                        message=f"Project {project_id} is not linked to a watch directory",
                        code="PROJECT_NOT_LINKED",
                        details={"project_id": project_id},
                    )

                if not project.name:
                    return ErrorResult(
                        message=f"Project {project_id} does not have a name",
                        code="PROJECT_NO_NAME",
                        details={"project_id": project_id},
                    )

                # Get watch_dir_path from database
                watch_dir_path_result = database.execute(
                    "SELECT absolute_path FROM watch_dir_paths WHERE watch_dir_id = ?",
                    (project.watch_dir_id,),
                )
                if isinstance(watch_dir_path_result, list):
                    watch_dir_paths = watch_dir_path_result
                else:
                    watch_dir_paths = watch_dir_path_result.get("data", [])

                if not watch_dir_paths:
                    return ErrorResult(
                        message=f"Watch directory path not found for watch_dir_id {project.watch_dir_id}",
                        code="WATCH_DIR_NOT_FOUND",
                        details={
                            "project_id": project_id,
                            "watch_dir_id": project.watch_dir_id,
                        },
                    )

                watch_dir_path = watch_dir_paths[0].get("absolute_path")
                if not watch_dir_path:
                    return ErrorResult(
                        message=f"Watch directory path is NULL for watch_dir_id {project.watch_dir_id}",
                        code="WATCH_DIR_NULL",
                        details={
                            "project_id": project_id,
                            "watch_dir_id": project.watch_dir_id,
                        },
                    )

                # Form absolute path: watch_dir_path / project_name / relative_file_path
                target = Path(watch_dir_path) / project.name / file_path
                target = target.resolve()

                if target.suffix != ".py":
                    return ErrorResult(
                        message="Target file must be a .py file",
                        code="INVALID_FILE",
                        details={"file_path": str(target)},
                    )

                # Check file doesn't exist
                if target.exists():
                    return ErrorResult(
                        message=f"File already exists: {target}",
                        code="FILE_EXISTS",
                        details={"file_path": str(target)},
                    )

                project_root = Path(project.root_path)

                # Format docstring as triple-quoted string
                docstring_value = docstring.strip()
                if not (
                    docstring_value.startswith('"""')
                    or docstring_value.startswith("'''")
                ):
                    docstring_value = f'"""{docstring_value}"""'

                # Create source code with docstring
                source_code = docstring_value

                # Create CST tree from code
                tree = create_tree_from_code(
                    file_path=str(target),
                    source_code=source_code,
                )

                # Save tree to file (creates file on disk and in database)
                result = save_tree_to_file(
                    tree_id=tree.tree_id,
                    file_path=str(target),
                    root_dir=project_root,
                    project_id=project_id,
                    database=database,
                    validate=True,
                    backup=False,  # No backup needed for new file
                    commit_message=None,
                )

                if not result.get("success"):
                    return ErrorResult(
                        message=result.get("error", "Failed to save tree"),
                        code="CST_SAVE_ERROR",
                        details=result,
                    )

                # Convert metadata to dictionaries
                nodes = [meta.to_dict() for meta in tree.metadata_map.values()]

                data = {
                    "success": True,
                    "tree_id": tree.tree_id,
                    "file_path": str(target),
                    "nodes": nodes,
                    "total_nodes": len(nodes),
                }

                return SuccessResult(data=data)

            finally:
                database.disconnect()

        except Exception as e:
            logger.exception("cst_create_file failed: %s", e)
            return ErrorResult(
                message=f"cst_create_file failed: {e}", code="CST_CREATE_ERROR"
            )

    @classmethod
    def metadata(cls: type["CSTCreateFileCommand"]) -> Dict[str, Any]:
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
                "The cst_create_file command creates a new Python file with a docstring and returns a tree_id. "
                "This command solves the problem of creating files from scratch, which was previously impossible "
                "without an existing file to use as a template.\n\n"
                "Operation flow:\n"
                "1. Gets project from database using project_id\n"
                "2. Validates project is linked to watch directory\n"
                "3. Gets watch directory path from database\n"
                "4. Forms absolute path: watch_dir_path / project_name / file_path\n"
                "5. Validates file is a .py file\n"
                "6. Checks file doesn't already exist\n"
                "7. Formats docstring as triple-quoted string (if not already formatted)\n"
                "8. Creates source code with only the docstring\n"
                "9. Creates CST tree from source code using create_tree_from_code\n"
                "10. Saves tree to file (creates file on disk and in database)\n"
                "11. Returns tree_id and node metadata\n\n"
                "File Creation:\n"
                "- File is created on disk with only the docstring\n"
                "- File is added to database with full metadata\n"
                "- CST tree is stored in memory with tree_id\n"
                "- File can be immediately modified using cst_modify_tree\n\n"
                "Docstring Formatting:\n"
                "- Docstring is automatically formatted as triple-quoted string\n"
                "- If docstring already has triple quotes, they are preserved\n"
                "- Docstring becomes the only content in the file\n"
                '- Example: \'CLI application\' becomes \'"""CLI application."""\'\n\n'
                "Node Metadata:\n"
                "- Returns node metadata for all nodes in the created file\n"
                "- For a file with only docstring, typically returns:\n"
                "  * Module node (root)\n"
                "  * SimpleStatementLine node (docstring statement)\n"
                "  * Expr node (docstring expression)\n"
                "  * SimpleString node (docstring value)\n\n"
                "Use cases:\n"
                "- Create new Python files from scratch\n"
                "- Initialize files with proper docstring structure\n"
                "- Prepare files for modification via cst_modify_tree\n"
                "- Create files programmatically without templates\n\n"
                "Important notes:\n"
                "- File must not exist (command will fail if file exists)\n"
                "- Docstring is required and must not be empty\n"
                "- File is created with only docstring (no other code)\n"
                "- Tree is stored in memory and can be modified immediately\n"
                "- Use returned tree_id with cst_modify_tree to add code\n"
                "- File is automatically added to database\n"
                "- File path is relative to project root"
            ),
            "parameters": {
                "project_id": {
                    "description": "Project ID (UUID4). Project must be linked to a watch directory.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": "Target Python file path (relative to project root). Absolute path is formed as: watch_dir_path / project_name / file_path. File must not exist.",
                    "type": "string",
                    "required": True,
                },
                "docstring": {
                    "description": "File-level docstring (required). Will be automatically formatted as triple-quoted string if not already formatted. Must not be empty.",
                    "type": "string",
                    "required": True,
                    "examples": [
                        "CLI application for working with data.",
                        '"""CLI application for working with data."""',
                        "Module description.\n\nAuthor: John Doe\nemail: john@example.com",
                    ],
                },
                "root_dir": {
                    "description": "Server root directory (optional, for database access). If not provided, will be resolved from config.",
                    "type": "string",
                    "required": False,
                },
            },
            "return_value": {
                "success": {
                    "description": "File created successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "Tree ID for use with other CST commands (cst_modify_tree, cst_save_tree)",
                        "file_path": "Absolute path to created file",
                        "nodes": "List of node metadata dictionaries",
                        "total_nodes": "Total number of nodes in the created file",
                    },
                    "example": {
                        "success": True,
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "nodes": [
                            {
                                "node_id": "node::Module:1:0-1:0",
                                "type": "Module",
                                "kind": "node",
                                "start_line": 1,
                                "start_col": 0,
                                "end_line": 1,
                                "end_col": 0,
                                "children_count": 1,
                                "children_ids": ["stmt::SimpleStatementLine:1:0-1:35"],
                            },
                            {
                                "node_id": "stmt::SimpleStatementLine:1:0-1:35",
                                "type": "SimpleStatementLine",
                                "kind": "stmt",
                                "start_line": 1,
                                "start_col": 0,
                                "end_line": 1,
                                "end_col": 35,
                                "children_count": 1,
                            },
                        ],
                        "total_nodes": 4,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., FILE_EXISTS, INVALID_FILE, PROJECT_NOT_FOUND, CST_CREATE_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "Create file with simple docstring",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "docstring": "CLI application for working with data.",
                    },
                    "explanation": (
                        "Creates a new file src/main.py with only a docstring. "
                        'Docstring is automatically formatted as \'"""CLI application for working with data."""\'. '
                        "Returns tree_id that can be used with cst_modify_tree to add code. "
                        "Absolute path is formed as: watch_dir_path / project_name / src/main.py."
                    ),
                },
                {
                    "description": "Create file with pre-formatted docstring",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/utils.py",
                        "docstring": '"""Utility functions for data processing."""',
                    },
                    "explanation": (
                        "Creates a new file with a docstring that already has triple quotes. "
                        "Triple quotes are preserved as-is. "
                        "File is created and ready for modification."
                    ),
                },
                {
                    "description": "Create file with multi-line docstring",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/models.py",
                        "docstring": "Data models for the application.\n\nAuthor: John Doe\nemail: john@example.com",
                    },
                    "explanation": (
                        "Creates a new file with a multi-line docstring. "
                        "Docstring is automatically formatted with triple quotes. "
                        "Newlines are preserved in the docstring."
                    ),
                },
                {
                    "description": "Create file and immediately modify it",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "docstring": "CLI application.",
                    },
                    "explanation": (
                        "Creates a new file and returns tree_id. "
                        "Use the returned tree_id with cst_modify_tree to add functions, classes, or other code. "
                        "Example: Use parent_node_id='node::Module:1:0-1:0' to insert code at module level."
                    ),
                },
            ],
            "error_cases": {
                "FILE_EXISTS": {
                    "description": "File already exists",
                    "message": "File already exists: {file_path}",
                    "solution": "Delete existing file first or use a different file_path",
                },
                "INVALID_FILE": {
                    "description": "File is not a Python file",
                    "message": "Target file must be a .py file",
                    "solution": "Ensure file_path ends with .py extension",
                },
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "message": "Project {project_id} not found",
                    "solution": "Verify project_id is correct and project exists in database",
                },
                "CST_CREATE_ERROR": {
                    "description": "Error during file creation",
                    "examples": [
                        {
                            "case": "Docstring is empty",
                            "message": "cst_create_file failed: Docstring must not be empty",
                            "solution": "Provide a non-empty docstring for the file",
                        },
                        {
                            "case": "Database error",
                            "message": "cst_create_file failed: Failed to save file to database",
                            "solution": (
                                "Database operation failed. "
                                "Check database connection and permissions. "
                                "File may have been created on disk but not in database."
                            ),
                        },
                        {
                            "case": "File system error",
                            "message": "cst_create_file failed: Failed to create file",
                            "solution": (
                                "File system error. "
                                "Check disk space, file permissions, and directory existence. "
                                "Ensure parent directory exists and is writable."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Always provide project_id - it is required and used to form absolute path",
                "Ensure project is linked to watch directory before using this command",
                "Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')",
                "Provide meaningful docstring that describes the file's purpose",
                "Save tree_id immediately for use with cst_modify_tree",
                "Use cst_modify_tree to add code after file creation",
                "File is created with only docstring - add code using cst_modify_tree",
                "Ensure file doesn't exist before calling this command",
                "File is automatically added to database - no need to call add_file separately",
                "Use returned node metadata to find parent_node_id for insert operations",
            ],
        }
