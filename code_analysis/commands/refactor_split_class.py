"""
MCP command: split_class — split a class into multiple smaller classes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import json
import logging
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .refactor import RefactorCommand as InternalRefactorCommand
from ..core.backup_manager import BackupManager
from ..core.git_integration import commit_after_write

logger = logging.getLogger(__name__)


class SplitClassMCPCommand(BaseMCPCommand):
    """Split a class into multiple smaller classes."""

    name = "split_class"
    version = "1.0.0"
    descr = "Split a class into multiple smaller classes"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the schema for class-member distribution and dry-run preview."""
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (absolute or relative to project root)",
                },
                "config": {
                    "type": "object",
                    "description": (
                        "Split configuration object. Structure: {\n"
                        "  'src_class': str (required) - Name of source class to split,\n"
                        "  'dst_classes': dict (required) - Dictionary mapping new class names to their configs.\n"
                        "    Each destination class config has:\n"
                        "      'props': list[str] - Properties (attributes) to move to this class,\n"
                        "      'methods': list[str] - Methods to move to this class.\n"
                        "  IMPORTANT: ALL properties and methods from src_class must be distributed\n"
                        "  across dst_classes. Special methods (__init__, __new__, __del__) stay in src_class.\n"
                        "  Example: {\n"
                        "    'src_class': 'UserManager',\n"
                        "    'dst_classes': {\n"
                        "      'UserAuth': {'props': ['username', 'password'], 'methods': ['authenticate']},\n"
                        "      'UserPermissions': {'props': ['role'], 'methods': ['authorize']}\n"
                        "    }\n"
                        "  }\n"
                        "}"
                    ),
                    "additionalProperties": True,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, preview changes without applying them",
                    "default": False,
                },
            },
            "required": ["project_id", "file_path", "config"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate params and reject unknown project_id before queuing."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @classmethod
    def metadata(cls: type["SplitClassMCPCommand"]) -> Dict[str, Any]:
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
                "The split_class command splits a large class into multiple smaller classes "
                "while maintaining functionality. The original class becomes a facade that "
                "delegates to the new classes.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Resolves file_path (absolute or relative to root_dir)\n"
                "3. Parses config (JSON object or string)\n"
                "4. Validates that ALL properties and methods from src_class are distributed\n"
                "5. If dry_run=true: generates preview without making changes\n"
                "6. If dry_run=false:\n"
                "   - Creates backup of original file\n"
                "   - Splits class according to config\n"
                "   - Validates Python syntax of result\n"
                "   - Validates completeness (all members present)\n"
                "   - Formats code with black\n"
                "   - Returns backup UUID for restoration if needed\n\n"
                "Configuration Requirements:\n"
                "- src_class: Name of the class to split (must exist in file)\n"
                "- dst_classes: Dictionary mapping new class names to their configurations\n"
                "  Each destination class must specify:\n"
                "  - props: List of property names (instance attributes from __init__)\n"
                "  - methods: List of method names to move to this class\n"
                "- CRITICAL: ALL properties and ALL methods (except __init__, __new__, __del__) "
                "must be distributed across dst_classes\n"
                "- Special methods (__init__, __new__, __del__) remain in the original class\n\n"
                "Result:\n"
                "- Original class becomes a facade with instances of new classes\n"
                "- Methods in original class delegate to corresponding new class instances\n"
                "- New classes are created with their assigned properties and methods\n"
                "- Original formatting, comments, and docstrings are preserved"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Must contain data/code_analysis.db file. "
                        "Can be absolute or relative to current working directory. "
                        "The directory must exist and be accessible."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project",
                        "/var/lib/code_analysis/projects/project1",
                        "./my_project",
                    ],
                },
                "file_path": {
                    "description": (
                        "Path to Python file containing the class to split. "
                        "Can be absolute or relative to root_dir. "
                        "File must exist and contain valid Python code with the specified class."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "src/models/user_manager.py",
                        "app/core/task_queue.py",
                        "/absolute/path/to/file.py",
                    ],
                },
                "config": {
                    "description": (
                        "Split configuration object or JSON string. Must contain:\n"
                        "- src_class (string, required): Name of class to split\n"
                        "- dst_classes (dict, required): Mapping of new class names to configs\n"
                        "  Each config has:\n"
                        "  - props (list[str]): Properties to move\n"
                        "  - methods (list[str]): Methods to move\n"
                        "\n"
                        "ALL properties and methods from src_class must be distributed.\n"
                        "Use list_cst_blocks command to discover class structure first."
                    ),
                    "type": "object",
                    "required": True,
                    "examples": [
                        {
                            "src_class": "UserManager",
                            "dst_classes": {
                                "UserAuth": {
                                    "props": ["username", "email", "password"],
                                    "methods": ["authenticate", "login"],
                                },
                                "UserPermissions": {
                                    "props": ["role", "permissions"],
                                    "methods": ["authorize", "check_permission"],
                                },
                            },
                        },
                        {
                            "src_class": "TaskQueue",
                            "dst_classes": {
                                "FTPExecutor": {
                                    "props": [],
                                    "methods": [
                                        "_execute_ftp_upload_task",
                                        "_execute_ftp_download_task",
                                        "_create_ftp_connection",
                                    ],
                                },
                                "DockerExecutor": {
                                    "props": [],
                                    "methods": [
                                        "_execute_docker_build_task",
                                        "_execute_docker_pull_task",
                                    ],
                                },
                            },
                        },
                    ],
                },
                "dry_run": {
                    "description": (
                        "If true, generates preview of changes without modifying files. "
                        "Use this to validate configuration before applying changes. "
                        "Returns preview code in response data."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir. "
                        "Use this to explicitly specify project when multiple projects "
                        "share the same root directory structure."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview split before applying (recommended first step)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models/user_manager.py",
                        "config": {
                            "src_class": "UserManager",
                            "dst_classes": {
                                "UserAuth": {
                                    "props": ["username", "password"],
                                    "methods": ["authenticate"],
                                },
                                "UserEmail": {
                                    "props": ["email"],
                                    "methods": ["send_email"],
                                },
                            },
                        },
                        "dry_run": True,
                    },
                    "explanation": (
                        "Validates configuration and returns preview code without making changes. "
                        "Review the preview to ensure split is correct before applying."
                    ),
                },
                {
                    "description": "Split class into multiple classes",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models/user_manager.py",
                        "config": {
                            "src_class": "UserManager",
                            "dst_classes": {
                                "UserAuth": {
                                    "props": ["username", "password"],
                                    "methods": ["authenticate"],
                                },
                                "UserEmail": {
                                    "props": ["email"],
                                    "methods": ["send_email"],
                                },
                            },
                        },
                        "dry_run": False,
                    },
                    "explanation": (
                        "Performs actual split. Creates backup automatically. "
                        "Returns backup_uuid for restoration if needed."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database for given root_dir",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Run update_indexes or ensure project is registered in database",
                },
                "FILE_NOT_FOUND": {
                    "description": "File path doesn't exist or is not accessible",
                    "example": "file_path='nonexistent.py'",
                    "solution": "Provide valid file path relative to root_dir or absolute path",
                },
                "SPLIT_CLASS_PREVIEW_ERROR": {
                    "description": (
                        "Configuration validation failed. Common causes:\n"
                        "- Missing properties in config (not all properties distributed)\n"
                        "- Missing methods in config (not all methods distributed)\n"
                        "- Extra properties/methods in config (not in source class)\n"
                        "- Source class not found in file"
                    ),
                    "example": (
                        "Error: Missing properties in split config: {'logger', 'config'}\n"
                        "Missing methods in split config: {'run_server', 'create_app'}"
                    ),
                    "solution": (
                        "Use list_cst_blocks command to discover all properties and methods. "
                        "Ensure ALL properties and methods (except __init__, __new__, __del__) "
                        "are distributed across dst_classes in config."
                    ),
                },
                "SPLIT_CLASS_ERROR": {
                    "description": "Split operation failed during execution",
                    "example": "Syntax error in generated code, validation failed",
                    "solution": (
                        "Check error message for details. Backup was created - use restore_backup_file "
                        "if needed. Review configuration and try again with dry_run=true first."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "True if operation succeeded",
                        "message": "Human-readable success message",
                        "backup_uuid": (
                            "UUID of created backup (if dry_run=false). "
                            "Use this with restore_backup_file command to restore original file."
                        ),
                        "preview": (
                            "Preview code (only if dry_run=true). "
                            "Shows how the file will look after split."
                        ),
                    },
                    "example": {
                        "success": True,
                        "message": "Class split successfully",
                        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., SPLIT_CLASS_PREVIEW_ERROR, SPLIT_CLASS_ERROR)",
                    "message": "Human-readable error message with validation details",
                    "details": "Additional error information",
                },
            },
            "best_practices": [
                "Always use dry_run=true first to preview changes",
                "Use list_cst_blocks command to discover class structure before creating config",
                "Ensure ALL properties and methods are distributed (validation is strict)",
                "Keep related functionality together in destination classes",
                "Test split result with dry_run before applying",
                "Save backup_uuid for easy restoration if needed",
            ],
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        config: Any,
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult:
        """Preview or apply a class split with backup and progress updates."""
        from ..core.progress_tracker import get_progress_tracker_from_context

        progress_tracker = get_progress_tracker_from_context(
            kwargs.get("context") or {}
        )
        try:
            if progress_tracker:
                progress_tracker.set_status("running")
                progress_tracker.set_description(
                    "split_class: resolving project root..."
                )
                progress_tracker.set_progress(0)

            root_path = self._resolve_project_root(project_id)

            if progress_tracker:
                progress_tracker.set_description("split_class: opening database...")
                progress_tracker.set_progress(0)

            db = self._open_database()
            proj_id = project_id

            if progress_tracker:
                progress_tracker.set_description("split_class: validating config...")
                progress_tracker.set_progress(0)

            # Parse config if it's a string
            if isinstance(config, str):
                config = json.loads(config)

            if dry_run:
                # Preview mode - return preview without making changes
                from ..core.refactorer_pkg.splitter import ClassSplitter

                file_path_obj = self._validate_file_path(file_path, root_path)

                splitter = ClassSplitter(file_path_obj)
                success, error_msg, preview = splitter.preview_split(config)
                db.disconnect()

                if success:
                    if progress_tracker:
                        progress_tracker.set_progress(100)
                        progress_tracker.set_description("Preview completed")
                        progress_tracker.set_status("completed")
                    return SuccessResult(
                        data={
                            "success": True,
                            "message": "Preview generated successfully",
                            "preview": preview,
                            "dry_run": True,
                        }
                    )
                return ErrorResult(
                    message=error_msg or "Preview failed",
                    code="SPLIT_CLASS_PREVIEW_ERROR",
                )
            else:
                # Execute mode - perform actual split
                # Create backup before modification
                if progress_tracker:
                    progress_tracker.set_description("Creating backup...")
                    progress_tracker.set_progress(5)
                file_path_obj = self._validate_file_path(file_path, root_path)
                backup_manager = BackupManager(root_path)

                # Extract destination classes from config for related files
                related_files = []
                if isinstance(config, dict):
                    dst_classes = config.get("dst_classes", {})
                    related_files = list(dst_classes.keys())

                backup_uuid = backup_manager.create_backup(
                    file_path_obj,
                    command="split_class",
                    related_files=related_files,
                    comment="",  # Comment can be added later if needed
                )
                if not backup_uuid:
                    return ErrorResult(
                        message=(
                            "Backup to old_code (versions) is mandatory before write; "
                            "create_backup failed. Aborting split_class."
                        ),
                        code="BACKUP_REQUIRED",
                        details={"file_path": str(file_path_obj)},
                    )
                logger.info(f"Backup created before split: {backup_uuid}")
                if progress_tracker:
                    progress_tracker.set_description("Splitting class...")
                    progress_tracker.set_progress(25)

                config_data = BaseMCPCommand._get_raw_config()
                git_ok, git_err = commit_after_write(
                    root_path,
                    [file_path_obj],
                    "split_class",
                    commit_message_override=f"Before split_class: {file_path}",
                    config_data=config_data,
                )
                if not git_ok and git_err:
                    logger.warning("Git commit before split_class: %s", git_err)

                cmd = InternalRefactorCommand(proj_id, database=db, root_dir=root_path)
                result = await cmd.split_class(str(root_path), file_path, config)
                if progress_tracker:
                    progress_tracker.set_progress(70)

                # Update database after successful split
                if result.get("success"):
                    if progress_tracker:
                        progress_tracker.set_description("Updating database...")
                        progress_tracker.set_progress(80)
                    try:
                        update_result = db.index_file(
                            file_path=str(file_path_obj),
                            project_id=proj_id,
                        )
                        if update_result.get("success"):
                            logger.info(
                                f"Database updated after split_class: "
                                f"AST={update_result.get('ast_updated')}, "
                                f"CST={update_result.get('cst_updated')}, "
                                f"entities={update_result.get('entities_updated')}"
                            )
                        else:
                            logger.warning(
                                f"Failed to update database after split_class: "
                                f"{update_result.get('error')}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error updating database after split_class: {e}",
                            exc_info=True,
                        )
                        # Don't fail the operation, just log the error

                db.disconnect()

                if result.get("success"):
                    if progress_tracker:
                        progress_tracker.set_progress(100)
                        progress_tracker.set_description("Split completed")
                        progress_tracker.set_status("completed")
                    git_ok, git_err = commit_after_write(
                        root_path,
                        [file_path_obj],
                        "split_class",
                        commit_message_override=f"split_class: {file_path}",
                        config_data=config_data,
                    )
                    if not git_ok and git_err:
                        logger.warning("Git commit after split_class: %s", git_err)
                    result_data = result.copy()
                    if backup_uuid:
                        result_data["backup_uuid"] = backup_uuid
                    return SuccessResult(data=result_data)
                return ErrorResult(
                    message=result.get("message", "split_class failed"),
                    code="SPLIT_CLASS_ERROR",
                    details=result,
                )
        except Exception as e:
            if progress_tracker:
                progress_tracker.set_status("failed")
                progress_tracker.set_description(str(e)[:512])
            return self._handle_error(e, "SPLIT_CLASS_ERROR", "split_class")
