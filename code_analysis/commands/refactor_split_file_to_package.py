"""
MCP command: split_file_to_package — split a file into a package with multiple modules.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .refactor import RefactorCommand as InternalRefactorCommand
from ..core.backup_manager import BackupManager
from ..core.git_integration import commit_after_write

logger = logging.getLogger(__name__)

# Debug timing log (NDJSON); path matches debug session log path
_DEBUG_TIMING_LOG_PATH = (
    "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-cbd1d4.log"
)


def _timing_log(
    phase: str, elapsed_ms: float, data: Optional[Dict[str, Any]] = None
) -> None:
    """Append one NDJSON timing line to debug log for bottleneck analysis."""
    # #region agent log
    try:
        payload = {
            "sessionId": "cbd1d4",
            "timestamp": int(time.time() * 1000),
            "location": "refactor_split_file_to_package.py",
            "message": f"timing:{phase}",
            "data": {
                "phase": phase,
                "elapsed_ms": round(elapsed_ms, 2),
                **(data or {}),
            },
            "hypothesisId": "timing",
        }
        with open(_DEBUG_TIMING_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


class SplitFileToPackageMCPCommand(BaseMCPCommand):
    """Split a file into a package with multiple modules."""

    name = "split_file_to_package"
    version = "1.0.0"
    descr = "Split a file into a package with multiple modules"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
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
        project_id: str,
        file_path: str,
        config: Any,
        **kwargs,
    ) -> SuccessResult:
        from ..core.progress_tracker import get_progress_tracker_from_context

        t0 = time.monotonic()
        progress_tracker = get_progress_tracker_from_context(
            kwargs.get("context") or {}
        )
        try:
            if progress_tracker:
                progress_tracker.set_status("running")
                progress_tracker.set_description("Resolving project root...")
                progress_tracker.set_progress(0)
            _timing_log("entry", (time.monotonic() - t0) * 1000, {"progress_pct": 0})

            root_path = self._resolve_project_root(project_id)
            if progress_tracker:
                progress_tracker.set_description("Opening database...")
                progress_tracker.set_progress(5)
            _timing_log(
                "after_resolve_project_root",
                (time.monotonic() - t0) * 1000,
                {"progress_pct": 5},
            )

            db = self._open_database()
            proj_id = project_id

            if progress_tracker:
                progress_tracker.set_description("Validating config...")
                progress_tracker.set_progress(8)
            if isinstance(config, str):
                config = json.loads(config)
            _timing_log(
                "after_open_database",
                (time.monotonic() - t0) * 1000,
                {"progress_pct": 8},
            )

            if progress_tracker:
                progress_tracker.set_description("Validating file path...")
                progress_tracker.set_progress(10)
            # Create backup before modification
            file_path_obj = self._validate_file_path(file_path, root_path)
            _timing_log(
                "after_validate_config",
                (time.monotonic() - t0) * 1000,
                {"progress_pct": 10},
            )

            backup_manager = BackupManager(root_path)
            # Extract created modules from config for related files
            related_files = []
            if isinstance(config, dict):
                modules = config.get("modules", {})
                related_files = list(modules.keys())

            if progress_tracker:
                progress_tracker.set_description("Creating backup...")
                progress_tracker.set_progress(12)
            backup_uuid = backup_manager.create_backup(
                file_path_obj,
                command="split_file_to_package",
                related_files=related_files,
                comment="",  # Comment can be added later if needed
            )
            if not backup_uuid:
                return ErrorResult(
                    message=(
                        "Backup to old_code (versions) is mandatory before write; "
                        "create_backup failed. Aborting split_file_to_package."
                    ),
                    code="BACKUP_REQUIRED",
                    details={"file_path": str(file_path_obj)},
                )
            logger.info(f"Backup created before split_file_to_package: {backup_uuid}")
            if progress_tracker:
                progress_tracker.set_description("Git commit (before split)...")
                progress_tracker.set_progress(18)
            _timing_log(
                "after_backup", (time.monotonic() - t0) * 1000, {"progress_pct": 18}
            )

            config_data = BaseMCPCommand._get_raw_config()
            git_ok, git_err = commit_after_write(
                root_path,
                [file_path_obj],
                "split_file_to_package",
                commit_message_override=f"Before split_file_to_package: {file_path}",
                config_data=config_data,
            )
            if not git_ok and git_err:
                logger.warning("Git commit before split_file_to_package: %s", git_err)
            _timing_log(
                "after_git_before", (time.monotonic() - t0) * 1000, {"progress_pct": 22}
            )

            if progress_tracker:
                progress_tracker.set_description("Splitting file to package (CST)...")
                progress_tracker.set_progress(25)
            _timing_log(
                "split_start", (time.monotonic() - t0) * 1000, {"progress_pct": 25}
            )

            cmd = InternalRefactorCommand(proj_id, database=db, root_dir=root_path)
            result = await cmd.split_file_to_package(str(root_path), file_path, config)

            _timing_log(
                "split_end", (time.monotonic() - t0) * 1000, {"progress_pct": 65}
            )
            if progress_tracker:
                progress_tracker.set_progress(65)

            # Update database for all created files after successful split
            if result.get("success"):
                if progress_tracker:
                    progress_tracker.set_description("Updating database...")
                    progress_tracker.set_progress(70)
                _timing_log(
                    "db_update_start",
                    (time.monotonic() - t0) * 1000,
                    {"progress_pct": 70},
                )
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
                            init_content = init_file.read_text(encoding="utf-8")
                            db.add_file(
                                path=str(init_file.resolve()),
                                lines=len(init_content.splitlines()),
                                # Force index_file() to perform full AST/CST extraction.
                                last_modified=0.0,
                                has_docstring=init_content.strip().startswith('"""')
                                or init_content.strip().startswith("'''"),
                                project_id=proj_id,
                            )
                            update_result = db.index_file(
                                file_path=str(init_file.resolve()),
                                project_id=proj_id,
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
                                    module_content = module_path.read_text(
                                        encoding="utf-8"
                                    )
                                    db.add_file(
                                        path=str(module_path.resolve()),
                                        lines=len(module_content.splitlines()),
                                        # Force index_file() to perform full AST/CST extraction.
                                        last_modified=0.0,
                                        has_docstring=module_content.strip().startswith(
                                            '"""'
                                        )
                                        or module_content.strip().startswith("'''"),
                                        project_id=proj_id,
                                    )
                                    update_result = db.index_file(
                                        file_path=str(module_path.resolve()),
                                        project_id=proj_id,
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
                _timing_log(
                    "db_update_end",
                    (time.monotonic() - t0) * 1000,
                    {"progress_pct": 85},
                )

            db.disconnect()

            if result.get("success"):
                if progress_tracker:
                    progress_tracker.set_description("Finalizing...")
                    progress_tracker.set_progress(95)
                _timing_log(
                    "before_completed",
                    (time.monotonic() - t0) * 1000,
                    {"progress_pct": 95},
                )
                if progress_tracker:
                    progress_tracker.set_progress(100)
                    progress_tracker.set_description("Split completed")
                    progress_tracker.set_status("completed")
                _timing_log(
                    "completed", (time.monotonic() - t0) * 1000, {"progress_pct": 100}
                )
                file_dir = file_path_obj.resolve().parent
                file_stem = file_path_obj.resolve().stem
                package_dir = file_dir / file_stem
                git_ok, git_err = commit_after_write(
                    root_path,
                    [package_dir],
                    "split_file_to_package",
                    commit_message_override=f"split_file_to_package: {file_path}",
                    config_data=config_data,
                )
                if not git_ok and git_err:
                    logger.warning(
                        "Git commit after split_file_to_package: %s", git_err
                    )
                result_data = result.copy()
                if backup_uuid:
                    result_data["backup_uuid"] = backup_uuid
                # Report size in bytes and lines for each written file
                files_with_size = []
                init_file = package_dir / "__init__.py"
                if init_file.exists():
                    text = init_file.read_text(encoding="utf-8")
                    files_with_size.append(
                        {
                            "path": str(init_file.relative_to(root_path)),
                            "file_size_bytes": len(text.encode("utf-8")),
                            "file_lines": len(text.splitlines()),
                        }
                    )
                if isinstance(config, dict):
                    for module_name in config.get("modules", {}):
                        module_path = package_dir / f"{module_name}.py"
                        if module_path.exists():
                            text = module_path.read_text(encoding="utf-8")
                            files_with_size.append(
                                {
                                    "path": str(module_path.relative_to(root_path)),
                                    "file_size_bytes": len(text.encode("utf-8")),
                                    "file_lines": len(text.splitlines()),
                                }
                            )
                result_data["files"] = files_with_size
                return SuccessResult(data=result_data)
            msg = result.get("message", "split_file_to_package failed")
            code = (
                "DUPLICATE_TOP_LEVEL_NAMES"
                if "DUPLICATE_TOP_LEVEL_NAMES" in msg
                else "SPLIT_FILE_TO_PACKAGE_ERROR"
            )
            return ErrorResult(
                message=msg,
                code=code,
                details=result,
            )
        except Exception as e:
            if progress_tracker:
                progress_tracker.set_status("failed")
                progress_tracker.set_description(str(e)[:512])
            return self._handle_error(
                e, "SPLIT_FILE_TO_PACKAGE_ERROR", "split_file_to_package"
            )
