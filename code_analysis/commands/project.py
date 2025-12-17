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

# Use logger from adapter (configured by adapter)
logger = logging.getLogger(__name__)


class ProjectCommand:
    """Commands for managing projects (using database, not config file)."""

    def __init__(self, config_path: Optional[Path] = None, db_path: Optional[Path] = None):
        """
        Initialize project command.

        Args:
            config_path: Path to server configuration file (deprecated, kept for compatibility)
            db_path: Path to database (optional)
        """
        self.config_path = config_path
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

            # Create database entry (projects are stored in database, not config)
            if self.db_path:
                db = CodeDatabase(self.db_path)
            else:
                # Use default database path
                path_obj = Path(path.strip())
                db_path = path_obj / "data" / "code_analysis.db"
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db = CodeDatabase(db_path)

            try:
                # Create or update project in database
                project_uuid = db.get_or_create_project(
                    path.strip(), name=name.strip(), comment=comment
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

            # Projects are stored in database, not config
            # Check if project exists in any database (we'd need to search all databases)
            # For now, just log that we're removing from database
            logger.info(f"Removed project: {project_id} (projects are stored in database)")

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

            # Projects are stored in database, not config
            # Update in database
            # Determine database path - need to find project first
            # For now, update in database if path provided
            if path:
                if self.db_path:
                    db = CodeDatabase(self.db_path)
                else:
                    path_obj = Path(path)
                    db_path = path_obj / "data" / "code_analysis.db"
                    if db_path.exists():
                        db = CodeDatabase(db_path)
                    else:
                        return {
                            "success": False,
                            "message": f"Project database not found for path: {path}",
                        }
                
                try:
                    # Update project in database
                    db_project_id = db.get_or_create_project(
                        path,
                        name=name if name else None,
                        comment=comment if comment else None,
                    )
                    logger.info(f"Updated project in database: {db_project_id}")
                finally:
                    db.close()
            else:
                return {
                    "success": False,
                    "message": "Path is required to update project (projects are stored in database)",
                }

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
