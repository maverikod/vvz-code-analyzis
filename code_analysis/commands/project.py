"""
Project management commands implementation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID

from ..core import CodeDatabase
from ..core.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class ProjectCommand:
    """Commands for managing projects."""

    def __init__(self, config_path: Path, db_path: Optional[Path] = None):
        """
        Initialize project command.

        Args:
            config_path: Path to server configuration file
            db_path: Path to database (optional, uses config if not provided)
        """
        self.config_manager = ConfigManager(config_path)
        self.db_path = db_path

    async def add_project(
        self,
        name: str,
        path: str,
        project_id: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add project to configuration and database.

        Args:
            name: Human-readable project name
            path: Absolute path to project directory
            project_id: Optional UUID4 (generated if not provided)
            comment: Optional comment/description

        Returns:
            Dictionary with success status and project information
        """
        try:
            # Validate inputs
            if not name or not name.strip():
                return {
                    "success": False,
                    "message": "Project name is required",
                }

            if not path or not path.strip():
                return {
                    "success": False,
                    "message": "Project path is required",
                }

            # Add to config
            project_uuid = self.config_manager.add_project(
                name=name.strip(),
                path=path.strip(),
                project_id=project_id,
            )

            # Create database entry
            if self.db_path:
                db = CodeDatabase(self.db_path)
            else:
                # Use default database path
                path_obj = Path(path.strip())
                db_path = path_obj / "code_analysis" / "code_analysis.db"
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db = CodeDatabase(db_path)

            try:
                # Create or update project in database
                db_project_id = db.get_or_create_project(
                    path.strip(), name=name.strip(), comment=comment
                )

                # If UUID was provided and different from DB, update DB
                if project_uuid != db_project_id:
                    # Note: This is a limitation - DB uses its own project_id
                    # We'll use the config UUID as the source of truth
                    logger.warning(
                        f"Project UUID mismatch: config={project_uuid}, "
                        f"db={db_project_id}"
                    )
            finally:
                db.close()

            logger.info(f"Added project: {name} ({project_uuid}) at {path}")

            return {
                "success": True,
                "message": f"Project '{name}' added successfully",
                "project_id": project_uuid,
                "name": name,
                "path": path,
            }
        except ValueError as e:
            logger.error(f"Error adding project: {e}")
            return {
                "success": False,
                "message": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected error adding project: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Unexpected error: {str(e)}",
            }

    async def remove_project(self, project_id: str) -> Dict[str, Any]:
        """
        Remove project from configuration.

        Args:
            project_id: Project UUID to remove

        Returns:
            Dictionary with success status and message
        """
        try:
            # Validate UUID
            try:
                UUID(project_id)
            except ValueError:
                return {
                    "success": False,
                    "message": f"Invalid UUID format: {project_id}",
                }

            # Remove from config
            removed = self.config_manager.remove_project(project_id)

            if not removed:
                return {
                    "success": False,
                    "message": f"Project {project_id} not found in configuration",
                }

            logger.info(f"Removed project: {project_id}")

            return {
                "success": True,
                "message": f"Project {project_id} removed successfully",
                "project_id": project_id,
            }
        except ValueError as e:
            logger.error(f"Error removing project: {e}")
            return {
                "success": False,
                "message": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected error removing project: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Unexpected error: {str(e)}",
            }

    async def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        path: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update project data in configuration and database.

        Args:
            project_id: Project UUID to update
            name: New name (optional)
            path: New path (optional)
            comment: New comment (optional)

        Returns:
            Dictionary with success status and message
        """
        try:
            # Validate UUID
            try:
                UUID(project_id)
            except ValueError:
                return {
                    "success": False,
                    "message": f"Invalid UUID format: {project_id}",
                }

            # Get current project
            project = self.config_manager.get_project(project_id)
            if not project:
                return {
                    "success": False,
                    "message": f"Project {project_id} not found",
                }

            # Update in config
            updated = self.config_manager.update_project(
                project_id, name=name, path=path
            )

            if not updated:
                return {
                    "success": False,
                    "message": f"Failed to update project {project_id}",
                }

            # Update in database if path changed or comment provided
            if path or comment:
                # Determine database path
                new_path = path if path else project.path
                if self.db_path:
                    db = CodeDatabase(self.db_path)
                else:
                    path_obj = Path(new_path)
                    db_path = path_obj / "code_analysis" / "code_analysis.db"
                    if db_path.exists():
                        db = CodeDatabase(db_path)
                    else:
                        db = None

                if db:
                    try:
                        # Update project in database
                        db_project_id = db.get_or_create_project(
                            new_path,
                            name=name if name else project.name,
                            comment=comment if comment else None,
                        )
                        logger.info(f"Updated project in database: {db_project_id}")
                    finally:
                        db.close()

            logger.info(f"Updated project: {project_id}")

            return {
                "success": True,
                "message": f"Project {project_id} updated successfully",
                "project_id": project_id,
            }
        except ValueError as e:
            logger.error(f"Error updating project: {e}")
            return {
                "success": False,
                "message": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected error updating project: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Unexpected error: {str(e)}",
            }
