"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ...core.git_integration import commit_after_write
from ..base_mcp_command import BaseMCPCommand
from ..file_management import RepairDatabaseCommand

logger = logging.getLogger(__name__)


class RepairDatabaseMCPCommand(BaseMCPCommand):
    """Repair database integrity - restore correct file status based on actual file presence."""

    name = "repair_database"
    version = "1.1.0"
    descr = "Repair database integrity - restore correct file status based on actual file presence in project and versions"
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "version_dir": {
                    "type": "string",
                    "description": "Version directory for deleted files (default: data/versions)",
                    "default": "data/versions",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only show what would be repaired",
                    "default": False,
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        version_dir: str = "data/versions",
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute repair database command.

        Args:
            project_id: Project UUID (from create_project or list_projects).
            version_dir: Version directory for deleted files (relative to project root)
            dry_run: If True, only show what would be repaired

        Returns:
            SuccessResult with repair statistics or ErrorResult on failure
        """
        try:
            root_path = self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)

            if not Path(version_dir).is_absolute():
                version_dir = str(root_path / version_dir)

            trash_dir: Optional[str] = None
            try:
                from ...core.storage_paths import load_raw_config, resolve_storage_paths

                config_path = self._resolve_config_path()
                config_data = load_raw_config(config_path)
                storage = resolve_storage_paths(
                    config_data=config_data, config_path=config_path
                )
                trash_dir = str(storage.trash_dir)
            except Exception:
                pass

            try:
                command = RepairDatabaseCommand(
                    database=database,
                    project_id=project_id,
                    root_dir=root_path,
                    version_dir=version_dir,
                    dry_run=dry_run,
                    trash_dir=trash_dir,
                )
                result = await command.execute()
                if not dry_run:
                    path_strs = result.get("repair_git_paths") or []
                    if path_strs:
                        paths = [Path(s).resolve() for s in path_strs]
                        git_ok, git_err = commit_after_write(
                            root_path.resolve(),
                            paths,
                            "repair_database",
                            config_data=BaseMCPCommand._get_raw_config(),
                        )
                        if not git_ok and git_err:
                            logger.warning(
                                "Git commit after repair_database: %s", git_err
                            )
                return SuccessResult(data=result)
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "REPAIR_DATABASE_ERROR", "repair_database")

    @classmethod
    def metadata(cls: type["RepairDatabaseMCPCommand"]) -> Dict[str, Any]:
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
                "The repair_database command repairs database integrity by restoring correct file "
                "status based on actual file presence in the project directory and version directory. "
                "It synchronizes the database with the actual file system state.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Resolves version_dir path (relative to root_dir if not absolute)\n"
                "5. For each file in database:\n"
                "   - Checks if file exists in project directory\n"
                "   - Checks if file exists in version directory\n"
                "   - Updates database status accordingly\n"
                "6. Repair actions:\n"
                "   - If file exists in project directory: Remove deleted flag (deleted=0)\n"
                "   - If file exists in versions but not in project: Set deleted flag (deleted=1)\n"
                "   - If file doesn't exist anywhere: Restore from CST nodes:\n"
                "     * Place file in versions directory\n"
                "     * Add to project files if not marked for deletion\n"
                "7. If dry_run=True:\n"
                "   - Lists files that would be repaired\n"
                "   - Shows repair actions without making changes\n"
                "8. If dry_run=False:\n"
                "   - Performs actual repairs\n"
                "   - Updates database records\n"
                "   - Restores files from CST if needed\n"
                "9. Returns repair statistics\n\n"
                "Repair Actions:\n"
                "- Restore deleted flag: Files in project directory should not be marked deleted\n"
                "- Set deleted flag: Files in versions but not in project should be marked deleted\n"
                "- Restore from CST: Files missing from filesystem can be restored from CST nodes\n\n"
                "Use cases:\n"
                "- Fix database inconsistencies after manual file operations\n"
                "- Restore correct file status after file system changes\n"
                "- Recover files from CST nodes\n"
                "- Synchronize database with file system state\n\n"
                "Important notes:\n"
                "- Always use dry_run=True first to preview repairs\n"
                "- Restores files from CST nodes if they don't exist in filesystem\n"
                "- Updates database to match actual file system state\n"
                "- version_dir defaults to 'data/versions' if not specified"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
                "version_dir": {
                    "description": (
                        "Version directory for deleted files. Default is 'data/versions'. "
                        "If relative, resolved relative to root_dir. "
                        "This is where deleted files are stored."
                    ),
                    "type": "string",
                    "required": False,
                    "default": "data/versions",
                },
                "dry_run": {
                    "description": (
                        "If True, only shows what would be repaired without actually repairing. "
                        "Default is False. Always use dry_run=True first to preview changes."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview database repairs (dry run)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Lists all files that would be repaired, showing repair actions "
                        "without actually making changes."
                    ),
                },
                {
                    "description": "Repair database integrity",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Repairs database integrity by synchronizing file status with actual file system. "
                        "Restores files from CST if needed."
                    ),
                },
                {
                    "description": "Repair with custom version directory",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "version_dir": "custom/versions",
                    },
                    "explanation": (
                        "Repairs database using custom version directory for deleted files."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "REPAIR_DATABASE_ERROR": {
                    "description": "General error during database repair",
                    "example": "Database error, file access error, or CST restoration failure",
                    "solution": (
                        "Check database integrity, verify file permissions, ensure version directory exists. "
                        "Use dry_run=True first to identify issues."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "repaired_files": (
                            "List of files that were repaired. Each entry contains:\n"
                            "- path: File path\n"
                            "- action: Repair action (restore_deleted_flag, set_deleted_flag, restore_from_cst)\n"
                            "- status: File status after repair"
                        ),
                        "total_repaired": "Total number of files repaired",
                        "dry_run": "Whether this was a dry run",
                        "message": "Status message",
                    },
                    "example": {
                        "repaired_files": [
                            {
                                "path": "src/main.py",
                                "action": "restore_deleted_flag",
                                "status": "active",
                            },
                        ],
                        "total_repaired": 1,
                        "dry_run": False,
                        "message": "Repaired 1 files",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, REPAIR_DATABASE_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Always use dry_run=True first to preview what would be repaired",
                "Run this command after manual file system operations",
                "Use to fix database inconsistencies",
                "Files can be restored from CST nodes if missing from filesystem",
                "Regular repairs help maintain database integrity",
            ],
        }
