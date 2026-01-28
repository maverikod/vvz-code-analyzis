"""
MCP command: cst_convert_and_save

Convert source code to CST, save CST and AST to database, optionally save to file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.ast_utils import parse_with_comments
from ..core.cst_tree.tree_builder import create_tree_from_code

logger = logging.getLogger(__name__)


class CSTConvertAndSaveCommand(BaseMCPCommand):
    """Convert source code to CST, save CST and AST to database."""

    name = "cst_convert_and_save"
    version = "1.0.0"
    descr = "Convert source code to CST, save CST and AST to database, optionally save to file"
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
                    "description": "Target Python file path (relative to project root). Required for saving to database.",
                },
                "source_code": {
                    "type": "string",
                    "description": "Source code to convert to CST and save. Required.",
                },
                "save_to_file": {
                    "type": "boolean",
                    "description": "Whether to save code to file on disk. Default is True.",
                    "default": True,
                },
                "root_dir": {
                    "type": "string",
                    "description": "Server root directory (optional, for database access). If not provided, will be resolved from config.",
                },
            },
            "required": ["project_id", "source_code", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        source_code: str,
        file_path: str,
        save_to_file: bool = True,
        root_dir: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        """
        Convert source code to CST, save CST and AST to database.

        Process:
        1. Validate project exists
        2. Resolve absolute file path
        3. If save_to_file=True: save code to file on disk
        4. Parse source code to AST
        5. Create CST tree from source code
        6. Calculate hashes (AST and CST)
        7. Get or create file_id in database
        8. Save AST tree to database (ast_trees table)
        9. Save CST tree to database (cst_trees table)
        10. Return tree_id, file_id, ast_tree_id, and cst_tree_id

        Args:
            project_id: Project ID
            source_code: Source code to convert
            file_path: File path (relative to project root)
            save_to_file: Whether to save code to file on disk (default: True)
            root_dir: Optional server root directory

        Returns:
            SuccessResult with tree_id, file_id, ast_tree_id, cst_tree_id, and metadata
        """
        try:
            # Validate source code is not empty
            if not source_code.strip():
                return ErrorResult(
                    message="Source code must not be empty",
                    code="EMPTY_CODE",
                    details={},
                )


            # Resolve server root_dir for database access
            if not root_dir:
                from ..core.storage_paths import (
                    load_raw_config,
                    resolve_storage_paths,
                )

                config_path = self._resolve_config_path()
                config_data = load_raw_config(config_path)
                storage = resolve_storage_paths(
                    config_data=config_data, config_path=config_path
                )
                root_dir = str(storage.config_dir.parent) if hasattr(storage, 'config_dir') else "/"

            # Open database
            database = self._open_database(root_dir, auto_analyze=False)
            try:
                # Get project
                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project {project_id} not found",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )

                project_root = Path(project.root_path)

                # Resolve absolute path
                if not project.watch_dir_id:
                    return ErrorResult(
                        message=f"Project {project_id} is not linked to a watch directory",
                        code="PROJECT_NOT_LINKED",
                        details={"project_id": project_id},
                    )

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
                        details={"project_id": project_id, "watch_dir_id": project.watch_dir_id},
                    )

                watch_dir_path = watch_dir_paths[0].get("absolute_path")
                if not watch_dir_path:
                    return ErrorResult(
                        message=f"Watch directory path is NULL for watch_dir_id {project.watch_dir_id}",
                        code="WATCH_DIR_NULL",
                        details={"project_id": project_id, "watch_dir_id": project.watch_dir_id},
                    )

                abs_path = Path(watch_dir_path) / project.name / file_path
                abs_path = abs_path.resolve()

                if abs_path.suffix != ".py":
                    return ErrorResult(
                        message="Target file must be a .py file",
                        code="INVALID_FILE",
                        details={"file_path": str(abs_path)},
                    )

                # Save code to file if requested
                if save_to_file:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(source_code, encoding="utf-8")
                    logger.info(f"Saved code to file: {abs_path}")

                # Parse AST from source code
                try:
                    tree = parse_with_comments(source_code, filename=str(abs_path))
                except SyntaxError as e:
                    return ErrorResult(
                        message=f"Syntax error in source code: {e}",
                        code="SYNTAX_ERROR",
                        details={"error": str(e), "line": e.lineno if e.lineno else None},
                    )
                except Exception as e:
                    logger.exception("Error parsing AST: %s", e)
                    return ErrorResult(
                        message=f"Failed to parse AST: {e}",
                        code="AST_PARSE_ERROR",
                        details={"error": str(e)},
                    )

                # Create CST tree from source code
                cst_file_path = str(abs_path) if abs_path else "<string>"
                cst_tree = create_tree_from_code(
                    file_path=cst_file_path,
                    source_code=source_code,
                )

                # Calculate hashes
                ast_json = json.dumps(ast.dump(tree))
                ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()
                cst_hash = hashlib.sha256(source_code.encode()).hexdigest()
                file_mtime = time.time()

                # Get or create file_id
                from ..core.path_normalization import normalize_path_simple

                normalized_path = normalize_path_simple(str(abs_path))
                # Find file by path and project_id
                file_rows = database.select(
                    "files",
                    where={"path": normalized_path, "project_id": project_id},
                )
                if file_rows:
                    file_id = file_rows[0].get("id")
                else:
                    # Add file to database
                    # Get or create dataset_id
                    dataset_id = BaseMCPCommand._get_or_create_dataset(
                        database, project_id, str(project_root)
                    )

                    # Calculate file metadata
                    lines = len(source_code.splitlines())
                    has_docstring = bool(ast.get_docstring(tree))

                    # Create File object
                    from ..core.database_client.objects.file import File

                    file_obj = File(
                        project_id=project_id,
                        dataset_id=dataset_id,
                        path=normalized_path,
                        lines=lines,
                        last_modified=file_mtime,
                        has_docstring=has_docstring,
                    )

                    # Create file in database
                    created_file = database.create_file(file_obj)
                    file_id = created_file.id
                    logger.info(f"Added file to database: file_id={file_id}")

                # Save AST tree to database
                try:
                    # Parse AST JSON to dict for save_ast
                    ast_data = json.loads(ast_json)
                    ast_saved = database.save_ast(file_id, ast_data)
                    if not ast_saved:
                        return ErrorResult(
                            message="Failed to save AST",
                            code="AST_SAVE_ERROR",
                            details={},
                        )
                    # Get AST tree ID
                    ast_rows = database.select(
                        "ast_trees",
                        where={"file_id": file_id},
                        order_by=["updated_at DESC"],
                        limit=1,
                    )
                    ast_tree_id = ast_rows[0].get("id") if ast_rows else None
                    logger.debug(f"AST saved with id={ast_tree_id} for file_id={file_id}")
                except Exception as e:
                    logger.error(f"Error saving AST: {e}", exc_info=True)
                    return ErrorResult(
                        message=f"Failed to save AST: {e}",
                        code="AST_SAVE_ERROR",
                        details={"error": str(e)},
                    )

                # Save CST tree to database
                try:
                    cst_saved = database.save_cst(file_id, source_code)
                    if not cst_saved:
                        return ErrorResult(
                            message="Failed to save CST",
                            code="CST_SAVE_ERROR",
                            details={},
                        )
                    # Get CST tree ID
                    cst_rows = database.select(
                        "cst_trees",
                        where={"file_id": file_id},
                        order_by=["updated_at DESC"],
                        limit=1,
                    )
                    cst_tree_id = cst_rows[0].get("id") if cst_rows else None
                    logger.debug(f"CST saved with id={cst_tree_id} for file_id={file_id}")
                except Exception as e:
                    logger.error(f"Error saving CST: {e}", exc_info=True)
                    return ErrorResult(
                        message=f"Failed to save CST: {e}",
                        code="CST_SAVE_ERROR",
                        details={"error": str(e)},
                    )

                # Convert metadata to dictionaries
                nodes = [meta.to_dict() for meta in cst_tree.metadata_map.values()]

                data = {
                    "success": True,
                    "tree_id": cst_tree.tree_id,
                    "file_id": file_id,
                    "file_path": str(abs_path),
                    "ast_saved": True,
                    "cst_saved": True,
                    "ast_tree_id": ast_tree_id,
                    "cst_tree_id": cst_tree_id,
                    "nodes": nodes,
                    "total_nodes": len(nodes),
                }

                return SuccessResult(data=data)

            finally:
                database.disconnect()

        except Exception as e:
            logger.exception("cst_convert_and_save failed: %s", e)
            return ErrorResult(
                message=f"cst_convert_and_save failed: {e}", code="CST_CONVERT_ERROR"
            )

    @classmethod
    def metadata(cls: type["CSTConvertAndSaveCommand"]) -> Dict[str, Any]:
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
                "The cst_convert_and_save command converts source code to CST tree, saves both CST and AST "
                "to database, and optionally saves code to file on disk.\n\n"
                "Operation flow:\n"
                "1. Validates source code is not empty\n"
                "2. Gets project from database using project_id\n"
                "3. Validates project is linked to watch directory\n"
                "4. Resolves absolute file path: watch_dir_path / project_name / file_path\n"
                "5. If save_to_file=True: saves code to file on disk\n"
                "6. Parses source code to AST using parse_with_comments\n"
                "7. Creates CST tree from source code using create_tree_from_code\n"
                "8. Calculates hashes (AST JSON hash and CST source code hash)\n"
                "9. Gets or creates file_id in database\n"
                "10. Saves AST tree to database (ast_trees table with ast_json)\n"
                "11. Saves CST tree to database (cst_trees table with cst_code)\n"
                "12. Returns tree_id, file_id, ast_tree_id, cst_tree_id, and node metadata\n\n"
                "Database Storage:\n"
                "- AST trees: Stored in ast_trees table as JSON (ast_json column)\n"
                "  * Format: JSON string from ast.dump(tree)\n"
                "  * Hash: SHA256 of ast_json\n"
                "  * Used for: Code analysis, querying, dependency tracking\n\n"
                "- CST trees: Stored in cst_trees table as source code (cst_code column)\n"
                "  * Format: Original Python source code string\n"
                "  * Hash: SHA256 of source code\n"
                "  * Used for: Code editing, refactoring, file restoration\n\n"
                "Both AST and CST are saved for each file, allowing:\n"
                "- Fast analysis using AST (lightweight, structured)\n"
                "- Code editing using CST (preserves formatting, comments)\n"
                "- File restoration from CST (full source code available)\n\n"
                "Use cases:\n"
                "- Convert code string to CST tree and save to database\n"
                "- Import code from external sources\n"
                "- Create files programmatically with full database integration\n"
                "- Ensure both AST and CST are available for analysis and editing\n\n"
                "Important notes:\n"
                "- Both AST and CST are always saved to database (if file_id exists)\n"
                "- File is created on disk only if save_to_file=True\n"
                "- File must be added to database before AST/CST can be saved\n"
                "- CST tree is stored in memory and can be modified immediately\n"
                "- Use returned tree_id with cst_modify_tree to modify code\n"
                "- AST and CST are synchronized (same source code, same file_mtime)"
            ),
            "parameters": {
                "project_id": {
                    "description": "Project ID (UUID4). Project must be linked to a watch directory.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": "Target Python file path (relative to project root). Required for saving to database. Absolute path is formed as: watch_dir_path / project_name / file_path",
                    "type": "string",
                    "required": True,
                },
                "source_code": {
                    "description": "Source code to convert to CST and save. Must be valid Python syntax. Required.",
                    "type": "string",
                    "required": True,
                    "examples": [
                        '"""Module description."""\n\ndef main():\n    pass',
                        "import sys\n\nclass MyClass:\n    def method(self):\n        return True",
                    ],
                },
                "save_to_file": {
                    "description": "Whether to save code to file on disk. Default is True. If False, code is only saved to database.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "root_dir": {
                    "description": "Server root directory (optional, for database access). If not provided, will be resolved from config.",
                    "type": "string",
                    "required": False,
                },
            },
            "return_value": {
                "success": {
                    "description": "Code converted and saved successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "CST tree ID for use with other CST commands (cst_modify_tree, cst_save_tree)",
                        "file_id": "File ID in database",
                        "file_path": "Absolute path to file",
                        "ast_saved": "Always True (AST is always saved if file_id exists)",
                        "cst_saved": "Always True (CST is always saved if file_id exists)",
                        "ast_tree_id": "AST tree ID in database (ast_trees table)",
                        "cst_tree_id": "CST tree ID in database (cst_trees table)",
                        "nodes": "List of node metadata dictionaries",
                        "total_nodes": "Total number of nodes in CST tree",
                    },
                    "example": {
                        "success": True,
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "file_id": 123,
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "ast_saved": True,
                        "cst_saved": True,
                        "ast_tree_id": 456,
                        "cst_tree_id": 789,
                        "nodes": [
                            {
                                "node_id": "node::Module:1:0-10:0",
                                "type": "Module",
                                "kind": "node",
                                "start_line": 1,
                                "start_col": 0,
                                "end_line": 10,
                                "end_col": 0,
                            }
                        ],
                        "total_nodes": 15,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., EMPTY_CODE, SYNTAX_ERROR, AST_SAVE_ERROR, CST_SAVE_ERROR, CST_CONVERT_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "Convert code and save to database and file",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "source_code": '"""CLI application."""\n\ndef main():\n    print("Hello, World!")',
                        "save_to_file": True,
                    },
                    "explanation": (
                        "Converts source code to CST tree, saves both AST and CST to database, "
                        "and saves code to file on disk. Returns tree_id for further modifications. "
                        "Absolute path is formed as: watch_dir_path / project_name / src/main.py."
                    ),
                },
                {
                    "description": "Convert code and save only to database (no file)",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/utils.py",
                        "source_code": "def helper():\n    return True",
                        "save_to_file": False,
                    },
                    "explanation": (
                        "Converts source code to CST tree and saves both AST and CST to database, "
                        "but does not create file on disk. Useful for importing code from external sources "
                        "or creating database records without files."
                    ),
                },
            ],
            "error_cases": {
                "EMPTY_CODE": {
                    "description": "Source code is empty",
                    "message": "Source code must not be empty",
                    "solution": "Provide non-empty source code",
                },
                "SYNTAX_ERROR": {
                    "description": "Source code has syntax errors",
                    "message": "Syntax error in source code: {error}",
                    "solution": "Fix syntax errors in source code. Ensure code is valid Python.",
                },
                "AST_SAVE_ERROR": {
                    "description": "Failed to save AST to database",
                    "message": "Failed to save AST: {error}",
                    "solution": "Check database connection and permissions. Ensure file_id exists in database.",
                },
                "CST_SAVE_ERROR": {
                    "description": "Failed to save CST to database",
                    "message": "Failed to save CST: {error}",
                    "solution": "Check database connection and permissions. Ensure file_id exists in database.",
                },
                "CST_CONVERT_ERROR": {
                    "description": "Error during conversion",
                    "examples": [
                        {
                            "case": "Project not found",
                            "message": "cst_convert_and_save failed: Project {project_id} not found",
                            "solution": "Verify project_id is correct and project exists in database",
                        },
                        {
                            "case": "File path resolution failed",
                            "message": "cst_convert_and_save failed: Watch directory path not found",
                            "solution": "Ensure project is linked to a watch directory",
                        },
                    ],
                },
            },
            "best_practices": [
                "Always provide project_id - it is required and used to form absolute path",
                "Ensure project is linked to watch directory before using this command",
                "Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')",
                "Provide valid Python source code (will be validated during AST parsing)",
                "Save tree_id immediately for use with cst_modify_tree",
                "Both AST and CST are saved automatically - no need to call save separately",
                "Use save_to_file=False if you only want database records without files",
                "File must be added to database before AST/CST can be saved",
                "AST and CST are synchronized (same source code, same file_mtime)",
            ],
        }
