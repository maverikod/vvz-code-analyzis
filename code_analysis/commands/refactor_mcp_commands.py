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
                    "description": "Split configuration (JSON object or string)",
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
                )
                if backup_uuid:
                    logger.info(f"Backup created before split: {backup_uuid}")

                cmd = InternalRefactorCommand(proj_id)
                result = await cmd.split_class(str(root_path), file_path, config)
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
                    "description": "Extraction configuration (JSON object or string)",
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
                backup_uuid = backup_manager.create_backup(file_path_obj)
                if backup_uuid:
                    logger.info(f"Backup created before extraction: {backup_uuid}")

                cmd = InternalRefactorCommand(proj_id)
                result = await cmd.extract_superclass(str(root_path), file_path, config)
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
                    "description": "File-to-package split configuration (JSON object or string)",
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
            )
            if backup_uuid:
                logger.info(
                    f"Backup created before split_file_to_package: {backup_uuid}"
                )

            cmd = InternalRefactorCommand(proj_id)
            result = await cmd.split_file_to_package(str(root_path), file_path, config)
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
