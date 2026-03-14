"""
MCP command: extract_superclass — extract common functionality into base class.

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


class ExtractSuperclassMCPCommand(BaseMCPCommand):
    """Extract common functionality into base class."""

    name = "extract_superclass"
    version = "1.0.0"
    descr = "Extract common functionality into base class"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                **cls._get_base_schema_properties(),
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
            },
            "required": ["project_id", "file_path", "config"],
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
        project_id: str,
        file_path: str,
        config: Any,
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult:
        from ..core.progress_tracker import get_progress_tracker_from_context

        progress_tracker = get_progress_tracker_from_context(
            kwargs.get("context") or {}
        )
        try:
            root_path = self._resolve_project_root(project_id)
            db = self._open_database()
            proj_id = project_id

            if progress_tracker:
                progress_tracker.set_status("running")
                progress_tracker.set_description("Validating project and config...")
                progress_tracker.set_progress(0)

            # Parse config if it's a string
            if isinstance(config, str):
                config = json.loads(config)

            if dry_run:
                # Preview mode - return preview without making changes
                from ..core.refactorer_pkg.extractor import SuperclassExtractor

                file_path_obj = self._validate_file_path(file_path, root_path)

                extractor = SuperclassExtractor(file_path_obj)
                success, error_msg, preview = extractor.preview_extraction(config)
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
                    code="EXTRACT_SUPERCLASS_PREVIEW_ERROR",
                )
            else:
                # Execute mode - perform actual extraction
                if progress_tracker:
                    progress_tracker.set_description("Creating backup...")
                    progress_tracker.set_progress(5)
                # Create backup before modification
                file_path_obj = self._validate_file_path(file_path, root_path)
                backup_manager = BackupManager(root_path)
                backup_uuid = backup_manager.create_backup(
                    file_path_obj,
                    command="extract_superclass",
                    comment="",  # Comment can be added later if needed
                )
                if not backup_uuid:
                    return ErrorResult(
                        message=(
                            "Backup to old_code (versions) is mandatory before write; "
                            "create_backup failed. Aborting extract_superclass."
                        ),
                        code="BACKUP_REQUIRED",
                        details={"file_path": str(file_path_obj)},
                    )
                logger.info(f"Backup created before extraction: {backup_uuid}")
                if progress_tracker:
                    progress_tracker.set_description("Extracting superclass...")
                    progress_tracker.set_progress(25)

                config_data = BaseMCPCommand._get_raw_config()
                git_ok, git_err = commit_after_write(
                    root_path,
                    [file_path_obj],
                    "extract_superclass",
                    commit_message_override=f"Before extract_superclass: {file_path}",
                    config_data=config_data,
                )
                if not git_ok and git_err:
                    logger.warning("Git commit before extract_superclass: %s", git_err)

                cmd = InternalRefactorCommand(proj_id, database=db, root_dir=root_path)
                result = await cmd.extract_superclass(str(root_path), file_path, config)
                if progress_tracker:
                    progress_tracker.set_progress(70)

                # Update database after successful extraction
                if result.get("success"):
                    if progress_tracker:
                        progress_tracker.set_description("Updating database...")
                        progress_tracker.set_progress(80)
                    try:
                        file_path_obj = Path(file_path)
                        path_for_index = (
                            file_path_obj
                            if file_path_obj.is_absolute()
                            else (root_path / file_path_obj)
                        )
                        update_result = db.index_file(
                            file_path=str(path_for_index.resolve()),
                            project_id=proj_id,
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

                db.disconnect()

                if result.get("success"):
                    if progress_tracker:
                        progress_tracker.set_progress(100)
                        progress_tracker.set_description("Extraction completed")
                        progress_tracker.set_status("completed")
                    path_for_commit = (
                        file_path_obj
                        if file_path_obj.is_absolute()
                        else root_path / file_path
                    )
                    git_ok, git_err = commit_after_write(
                        root_path,
                        [path_for_commit],
                        "extract_superclass",
                        commit_message_override=f"extract_superclass: {file_path}",
                        config_data=config_data,
                    )
                    if not git_ok and git_err:
                        logger.warning(
                            "Git commit after extract_superclass: %s", git_err
                        )
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
            if progress_tracker:
                progress_tracker.set_status("failed")
                progress_tracker.set_description(str(e)[:512])
            return self._handle_error(
                e, "EXTRACT_SUPERCLASS_ERROR", "extract_superclass"
            )
