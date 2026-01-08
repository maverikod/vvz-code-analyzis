"""
MCP commands for code refactoring operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import json
import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .refactor import RefactorCommand as InternalRefactorCommand
from ..core.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class SplitClassMCPCommand(BaseMCPCommand):
    """Split a class into multiple smaller classes."""

    name = "split_class"
    version = "1.0.0"
    descr = "Split a class into multiple smaller classes"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
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
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path", "config"],
            "additionalProperties": False,
        }

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
        root_dir: str,
        file_path: str,
        config: Any,
        dry_run: bool = False,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            # Parse config if it's a string
            if isinstance(config, str):
                config = json.loads(config)

            if dry_run:
                # Preview mode - return preview without making changes
                from ..core.refactorer_pkg.splitter import ClassSplitter

                file_path_obj = self._validate_file_path(file_path, root_path)

                splitter = ClassSplitter(file_path_obj)
                success, error_msg, preview = splitter.preview_split(config)
                db.close()

                if success:
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
                if backup_uuid:
                    logger.info(f"Backup created before split: {backup_uuid}")

                cmd = InternalRefactorCommand(proj_id)
                result = await cmd.split_class(str(root_path), file_path, config)

                # Update database after successful split
                if result.get("success"):
                    try:
                        # Get relative path for update_file_data
                        try:
                            rel_path = str(file_path_obj.relative_to(root_path))
                        except ValueError:
                            # File is outside root, use absolute path
                            rel_path = str(file_path_obj)
                        
                        update_result = db.update_file_data(
                            file_path=rel_path,
                            project_id=proj_id,
                            root_dir=root_path,
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

                db.close()

                if result.get("success"):
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
            return self._handle_error(e, "SPLIT_CLASS_ERROR", "split_class")


class ExtractSuperclassMCPCommand(BaseMCPCommand):
    """Extract common functionality into base class."""

    name = "extract_superclass"
    version = "1.0.0"
    descr = "Extract common functionality into base class"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (absolute or relative to project root)",
                },
                "config": {
                    "type": "object",
                    "description": (
                        "Extraction configuration object. Structure: {\n"
                        "  'base_class': str (required) - Name of new base class to create,\n"
                        "  'child_classes': list[str] (required) - List of child class names to extract from,\n"
                        "  'abstract_methods': list[str] (optional) - Methods to make abstract in base class,\n"
                        "  'extract_from': dict (required) - Mapping of child class names to their configs.\n"
                        "    Each child config has:\n"
                        "      'properties': list[str] - Properties to extract to base class,\n"
                        "      'methods': list[str] - Methods to extract to base class.\n"
                        "  Example: {\n"
                        "    'base_class': 'Animal',\n"
                        "    'child_classes': ['Dog', 'Cat'],\n"
                        "    'abstract_methods': ['make_sound'],\n"
                        "    'extract_from': {\n"
                        "      'Dog': {'properties': ['name', 'legs'], 'methods': ['move', 'eat']},\n"
                        "      'Cat': {'properties': ['name', 'legs'], 'methods': ['move', 'eat']}\n"
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
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path", "config"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["ExtractSuperclassMCPCommand"]) -> Dict[str, Any]:
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
                "The extract_superclass command extracts common functionality from multiple classes "
                "into a new base class. Child classes inherit from the base class and keep their unique methods.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Resolves file_path (absolute or relative to root_dir)\n"
                "3. Parses config (JSON object or string)\n"
                "4. Validates all child classes exist in file\n"
                "5. Checks for multiple inheritance conflicts\n"
                "6. If dry_run=true: generates preview without making changes\n"
                "7. If dry_run=false:\n"
                "   - Creates backup of original file\n"
                "   - Creates new base class with extracted members\n"
                "   - Updates child classes to inherit from base class\n"
                "   - Makes specified methods abstract if abstract_methods provided\n"
                "   - Validates Python syntax of result\n"
                "   - Formats code with black\n"
                "   - Returns backup UUID for restoration if needed\n\n"
                "Configuration Requirements:\n"
                "- base_class: Name of new base class to create\n"
                "- child_classes: List of child class names (must exist in file)\n"
                "- extract_from: Dictionary mapping each child class to its extraction config\n"
                "  Each child config specifies:\n"
                "  - properties: List of property names to extract\n"
                "  - methods: List of method names to extract\n"
                "- abstract_methods: Optional list of methods to make abstract in base class\n"
                "  (requires 'from abc import ABC, abstractmethod')\n\n"
                "Result:\n"
                "- New base class is created with extracted properties and methods\n"
                "- Child classes inherit from base class\n"
                "- Abstract methods (if specified) are marked with @abstractmethod\n"
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
                        "Path to Python file containing the classes. "
                        "Can be absolute or relative to root_dir. "
                        "File must exist and contain valid Python code with the specified classes."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "src/models/animals.py",
                        "app/core/services.py",
                        "/absolute/path/to/file.py",
                    ],
                },
                "config": {
                    "description": (
                        "Extraction configuration object or JSON string. Must contain:\n"
                        "- base_class (string, required): Name of new base class\n"
                        "- child_classes (list[str], required): List of child class names\n"
                        "- extract_from (dict, required): Mapping of child class names to configs\n"
                        "  Each child config has:\n"
                        "  - properties (list[str]): Properties to extract\n"
                        "  - methods (list[str]): Methods to extract\n"
                        "- abstract_methods (list[str], optional): Methods to make abstract\n"
                        "\n"
                        "All child classes must exist in the file.\n"
                        "Use list_cst_blocks command to discover class structure first."
                    ),
                    "type": "object",
                    "required": True,
                    "examples": [
                        {
                            "base_class": "Animal",
                            "child_classes": ["Dog", "Cat"],
                            "abstract_methods": ["make_sound"],
                            "extract_from": {
                                "Dog": {
                                    "properties": ["name", "species", "legs"],
                                    "methods": ["move", "eat"],
                                },
                                "Cat": {
                                    "properties": ["name", "species", "legs"],
                                    "methods": ["move", "eat"],
                                },
                            },
                        },
                        {
                            "base_class": "BaseCommand",
                            "child_classes": ["GitCommand", "DockerCommand"],
                            "extract_from": {
                                "GitCommand": {
                                    "properties": ["logger", "config"],
                                    "methods": ["_validate_params", "_log_result"],
                                },
                                "DockerCommand": {
                                    "properties": ["logger", "config"],
                                    "methods": ["_validate_params", "_log_result"],
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
                    "description": "Preview extraction before applying (recommended first step)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models/animals.py",
                        "config": {
                            "base_class": "Animal",
                            "child_classes": ["Dog", "Cat"],
                            "abstract_methods": ["make_sound"],
                            "extract_from": {
                                "Dog": {
                                    "properties": ["name", "legs"],
                                    "methods": ["move", "eat"],
                                },
                                "Cat": {
                                    "properties": ["name", "legs"],
                                    "methods": ["move", "eat"],
                                },
                            },
                        },
                        "dry_run": True,
                    },
                    "explanation": (
                        "Validates configuration and returns preview code without making changes. "
                        "Review the preview to ensure extraction is correct before applying."
                    ),
                },
                {
                    "description": "Extract common functionality into base class",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models/animals.py",
                        "config": {
                            "base_class": "Animal",
                            "child_classes": ["Dog", "Cat"],
                            "abstract_methods": ["make_sound"],
                            "extract_from": {
                                "Dog": {
                                    "properties": ["name", "legs"],
                                    "methods": ["move", "eat"],
                                },
                                "Cat": {
                                    "properties": ["name", "legs"],
                                    "methods": ["move", "eat"],
                                },
                            },
                        },
                        "dry_run": False,
                    },
                    "explanation": (
                        "Performs actual extraction. Creates backup automatically. "
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
                "EXTRACT_SUPERCLASS_PREVIEW_ERROR": {
                    "description": (
                        "Configuration validation failed. Common causes:\n"
                        "- Child class not found in file\n"
                        "- Multiple inheritance conflicts (child already has base class)\n"
                        "- Invalid property or method names\n"
                        "- Base class name conflicts with existing class"
                    ),
                    "example": (
                        "Error: Child class 'NonExistentClass' not found\n"
                        "Error: Multiple inheritance conflict: Dog already inherits from Pet"
                    ),
                    "solution": (
                        "Use list_cst_blocks command to discover all classes and their structure. "
                        "Ensure all child classes exist. Check for existing inheritance relationships."
                    ),
                },
                "EXTRACT_SUPERCLASS_ERROR": {
                    "description": "Extraction operation failed during execution",
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
                            "Shows how the file will look after extraction."
                        ),
                    },
                    "example": {
                        "success": True,
                        "message": "Superclass extraction successful",
                        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., EXTRACT_SUPERCLASS_PREVIEW_ERROR, EXTRACT_SUPERCLASS_ERROR)",
                    "message": "Human-readable error message with validation details",
                    "details": "Additional error information",
                },
            },
            "best_practices": [
                "Always use dry_run=true first to preview changes",
                "Use list_cst_blocks command to discover class structure before creating config",
                "Ensure common methods/properties have identical signatures across child classes",
                "Use abstract_methods for methods that differ in implementation",
                "Test extraction result with dry_run before applying",
                "Save backup_uuid for easy restoration if needed",
            ],
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        config: Any,
        dry_run: bool = False,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            # Parse config if it's a string
            if isinstance(config, str):
                config = json.loads(config)

            if dry_run:
                # Preview mode - return preview without making changes
                from ..core.refactorer import SuperclassExtractor

                file_path_obj = self._validate_file_path(file_path, root_path)

                extractor = SuperclassExtractor(file_path_obj)
                success, error_msg, preview = extractor.preview_extraction(config)
                db.close()

                if success:
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
                    code="EXTRACT_SUPERCLASS_PREVIEW_ERROR",
                )
            else:
                # Execute mode - perform actual extraction
                # Create backup before modification
                file_path_obj = self._validate_file_path(file_path, root_path)
                backup_manager = BackupManager(root_path)
                backup_uuid = backup_manager.create_backup(
                    file_path_obj,
                    command="extract_superclass",
                    comment="",  # Comment can be added later if needed
                )
                if backup_uuid:
                    logger.info(f"Backup created before extraction: {backup_uuid}")

                cmd = InternalRefactorCommand(proj_id)
                result = await cmd.extract_superclass(str(root_path), file_path, config)

                # Update database after successful extraction
                if result.get("success"):
                    try:
                        # Get relative path for update_file_data
                        file_path_obj = Path(file_path)
                        try:
                            rel_path = str(file_path_obj.relative_to(root_path))
                        except ValueError:
                            # File is outside root, use absolute path
                            rel_path = str(file_path_obj)
                        
                        update_result = db.update_file_data(
                            file_path=rel_path,
                            project_id=proj_id,
                            root_dir=root_path,
                        )
                        if update_result.get("success"):
                            logger.info(
                                f"Database updated after extract_superclass: "
                                f"AST={update_result.get('ast_updated')}, "
                                f"CST={update_result.get('cst_updated')}, "
                                f"entities={update_result.get('entities_updated')}"
                            )
                        else:
                            logger.warning(
                                f"Failed to update database after extract_superclass: "
                                f"{update_result.get('error')}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error updating database after extract_superclass: {e}",
                            exc_info=True,
                        )
                        # Don't fail the operation, just log the error
                
                db.close()

                if result.get("success"):
                    result_data = result.copy()
                    if backup_uuid:
                        result_data["backup_uuid"] = backup_uuid
                    return SuccessResult(data=result_data)
                return ErrorResult(
                    message=result.get("message", "extract_superclass failed"),
                    code="EXTRACT_SUPERCLASS_ERROR",
                    details=result,
                )
        except Exception as e:
            return self._handle_error(
                e, "EXTRACT_SUPERCLASS_ERROR", "extract_superclass"
            )


class SplitFileToPackageMCPCommand(BaseMCPCommand):
    """Split a file into a package with multiple modules."""

    name = "split_file_to_package"
    version = "1.0.0"
    descr = "Split a file into a package with multiple modules"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (absolute or relative to project root)",
                },
                "config": {
                    "type": "object",
                    "description": (
                        "File-to-package split configuration object. Structure: {\n"
                        "  'modules': dict (required) - Dictionary mapping module names to their configs.\n"
                        "    Each module config has:\n"
                        "      'classes': list[str] - List of class names to include in this module,\n"
                        "      'functions': list[str] - List of function names to include in this module.\n"
                        "  Example: {\n"
                        "    'modules': {\n"
                        "      'ftp_executor': {\n"
                        "        'classes': ['FTPExecutor'],\n"
                        "        'functions': ['create_ftp_connection']\n"
                        "      },\n"
                        "      'docker_executor': {\n"
                        "        'classes': ['DockerExecutor'],\n"
                        "        'functions': []\n"
                        "      }\n"
                        "    }\n"
                        "  }\n"
                        "  Result: Creates package directory with __init__.py and module files.\n"
                        "}"
                    ),
                    "additionalProperties": True,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path", "config"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["SplitFileToPackageMCPCommand"]) -> Dict[str, Any]:
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
                "The split_file_to_package command splits a large Python file into a package "
                "with multiple modules. The original file is replaced by a package directory "
                "containing __init__.py and module files.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Resolves file_path (absolute or relative to root_dir)\n"
                "3. Parses config (JSON object or string)\n"
                "4. Validates file can be parsed as Python AST\n"
                "5. Creates package directory (file_stem/)\n"
                "6. Creates __init__.py in package directory\n"
                "7. For each module in config:\n"
                "   - Creates module_name.py file\n"
                "   - Extracts specified classes and functions from original file\n"
                "   - Preserves imports, docstrings, and formatting\n"
                "8. Creates backup of original file\n"
                "9. Returns backup UUID and list of created modules\n\n"
                "Configuration Requirements:\n"
                "- modules: Dictionary mapping module names to their configurations\n"
                "  Each module must specify:\n"
                "  - classes: List of class names to include (must exist in file)\n"
                "  - functions: List of function names to include (must exist in file)\n"
                "- Module names become Python module files (module_name.py)\n"
                "- Package directory is created as file_stem/ (e.g., task_queue/ for task_queue.py)\n\n"
                "Result:\n"
                "- Original file is replaced by package directory\n"
                "- Package contains __init__.py and module files\n"
                "- Each module contains its assigned classes and functions\n"
                "- Imports are preserved in each module\n"
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
                        "Path to Python file to split into package. "
                        "Can be absolute or relative to root_dir. "
                        "File must exist and contain valid Python code. "
                        "Package directory will be created as file_stem/ in the same directory."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "src/models/task_queue.py",
                        "app/core/large_module.py",
                        "/absolute/path/to/file.py",
                    ],
                },
                "config": {
                    "description": (
                        "Split configuration object or JSON string. Must contain:\n"
                        "- modules (dict, required): Mapping of module names to configs\n"
                        "  Each module config has:\n"
                        "  - classes (list[str]): Class names to include\n"
                        "  - functions (list[str]): Function names to include\n"
                        "\n"
                        "All classes and functions must exist in the file.\n"
                        "Use list_cst_blocks command to discover file structure first."
                    ),
                    "type": "object",
                    "required": True,
                    "examples": [
                        {
                            "modules": {
                                "ftp_executor": {
                                    "classes": ["FTPExecutor"],
                                    "functions": ["create_ftp_connection"],
                                },
                                "docker_executor": {
                                    "classes": ["DockerExecutor"],
                                    "functions": [],
                                },
                                "k8s_executor": {
                                    "classes": ["K8sExecutor"],
                                    "functions": ["setup_k8s_client"],
                                },
                            },
                        },
                        {
                            "modules": {
                                "models": {
                                    "classes": ["User", "Product", "Order"],
                                    "functions": [],
                                },
                                "utils": {
                                    "classes": [],
                                    "functions": ["validate_email", "format_date"],
                                },
                            },
                        },
                    ],
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
                    "description": "Split large file into package by functionality",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/core/task_queue.py",
                        "config": {
                            "modules": {
                                "ftp_executor": {
                                    "classes": ["FTPExecutor"],
                                    "functions": ["create_ftp_connection"],
                                },
                                "docker_executor": {
                                    "classes": ["DockerExecutor"],
                                    "functions": [],
                                },
                            },
                        },
                    },
                    "explanation": (
                        "Splits task_queue.py into task_queue/ package with "
                        "ftp_executor.py and docker_executor.py modules. "
                        "Creates backup automatically."
                    ),
                },
                {
                    "description": "Split file by entity type (models vs utils)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/models.py",
                        "config": {
                            "modules": {
                                "models": {
                                    "classes": ["User", "Product", "Order"],
                                    "functions": [],
                                },
                                "utils": {
                                    "classes": [],
                                    "functions": ["validate_email", "format_date"],
                                },
                            },
                        },
                    },
                    "explanation": (
                        "Splits models.py into models/ package with "
                        "models.py (classes) and utils.py (functions) modules."
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
                "SPLIT_FILE_TO_PACKAGE_ERROR": {
                    "description": (
                        "Split operation failed. Common causes:\n"
                        "- Failed to parse file AST (syntax errors)\n"
                        "- Class or function not found in file\n"
                        "- No modules specified in config\n"
                        "- Package directory creation failed (permissions)"
                    ),
                    "example": (
                        "Error: Failed to parse file AST\n"
                        "Error: Class 'NonExistentClass' not found\n"
                        "Error: No modules specified in config"
                    ),
                    "solution": (
                        "Use list_cst_blocks command to discover all classes and functions. "
                        "Ensure file has valid Python syntax. "
                        "Check that all specified classes/functions exist in the file."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "True if operation succeeded",
                        "message": "Human-readable success message with package path",
                        "backup_uuid": (
                            "UUID of created backup. "
                            "Use this with restore_backup_file command to restore original file."
                        ),
                        "package_path": "Path to created package directory",
                        "modules": "List of created module names",
                    },
                    "example": {
                        "success": True,
                        "message": "File split into package at /path/task_queue with modules: ftp_executor, docker_executor",
                        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000",
                        "package_path": "/path/task_queue",
                        "modules": ["ftp_executor", "docker_executor"],
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., SPLIT_FILE_TO_PACKAGE_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information",
                },
            },
            "best_practices": [
                "Use list_cst_blocks command to discover file structure before creating config",
                "Group related classes and functions together in modules",
                "Ensure all classes and functions are distributed across modules",
                "Keep module names descriptive and follow Python naming conventions",
                "Test imports after split to ensure package structure is correct",
                "Save backup_uuid for easy restoration if needed",
            ],
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        config: Any,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            if isinstance(config, str):
                config = json.loads(config)

            # Create backup before modification
            file_path_obj = self._validate_file_path(file_path, root_path)
            backup_manager = BackupManager(root_path)

            # Extract created modules from config for related files
            related_files = []
            if isinstance(config, dict):
                modules = config.get("modules", {})
                related_files = list(modules.keys())

            backup_uuid = backup_manager.create_backup(
                file_path_obj,
                command="split_file_to_package",
                related_files=related_files,
                comment="",  # Comment can be added later if needed
            )
            if backup_uuid:
                logger.info(
                    f"Backup created before split_file_to_package: {backup_uuid}"
                )

            cmd = InternalRefactorCommand(proj_id)
            result = await cmd.split_file_to_package(str(root_path), file_path, config)

            # Update database for all created files after successful split
            if result.get("success"):
                try:
                    # Get file directory and name to determine package path
                    file_path_obj_resolved = file_path_obj.resolve()
                    file_dir = file_path_obj_resolved.parent
                    file_stem = file_path_obj_resolved.stem
                    package_dir = file_dir / file_stem

                    # Update database for __init__.py
                    init_file = package_dir / "__init__.py"
                    if init_file.exists():
                        try:
                            rel_init_path = str(init_file.relative_to(root_path))
                            update_result = db.update_file_data(
                                file_path=rel_init_path,
                                project_id=proj_id,
                                root_dir=root_path,
                            )
                            if update_result.get("success"):
                                logger.info(
                                    f"Database updated for {rel_init_path} after split"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to update database for {init_file}: {e}"
                            )

                    # Update database for each created module
                    if isinstance(config, dict):
                        modules = config.get("modules", {})
                        for module_name in modules.keys():
                            module_path = package_dir / f"{module_name}.py"
                            if module_path.exists():
                                try:
                                    rel_module_path = str(
                                        module_path.relative_to(root_path)
                                    )
                                    update_result = db.update_file_data(
                                        file_path=rel_module_path,
                                        project_id=proj_id,
                                        root_dir=root_path,
                                    )
                                    if update_result.get("success"):
                                        logger.info(
                                            f"Database updated for {rel_module_path} after split"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to update database for {module_path}: {e}"
                                    )
                except Exception as e:
                    logger.error(
                        f"Error updating database after split_file_to_package: {e}",
                        exc_info=True,
                    )
                    # Don't fail the operation, just log the error

            db.close()

            if result.get("success"):
                result_data = result.copy()
                if backup_uuid:
                    result_data["backup_uuid"] = backup_uuid
                return SuccessResult(data=result_data)
            return ErrorResult(
                message=result.get("message", "split_file_to_package failed"),
                code="SPLIT_FILE_TO_PACKAGE_ERROR",
                details=result,
            )
        except Exception as e:
            return self._handle_error(
                e, "SPLIT_FILE_TO_PACKAGE_ERROR", "split_file_to_package"
            )
