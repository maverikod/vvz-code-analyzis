"""
Internal commands for project creation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..core.exceptions import (
    InvalidProjectIdFormatError,
    ProjectIdError,
)
from pathlib import Path

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class CreateProjectCommand:
    """
    Command to create or register a new project.

    This command:
    1. Validates that watched directory exists
    2. Validates that project directory does not have projectid file
    3. Validates that project is not already registered in database
    4. Creates projectid file with UUID4 and description
    5. Registers project in database

    Returns project ID, whether project already existed, and description.
    """

    def __init__(
        self,
        database: DatabaseClient,
        watch_dir_id: str,
        project_name: str,
        description: str,
        project_id: Optional[str] = None,
    ):
        """
        Initialize create project command.

        Args:
            database: DatabaseClient instance
            watch_dir_id: Watch directory ID from watch_dirs table (must exist)
            project_name: Name of project subdirectory to create in watch_dir
            description: Human-readable description of the project (required)
            project_id: Optional project ID (UUID4). If not provided, will be generated.
        """
        self.database = database
        self.watch_dir_id = watch_dir_id
        self.project_name = project_name
        self.description = description
        self.project_id = project_id

    def _get_watch_dir_path(self) -> Optional[Path]:
        """
        Get watch directory path from watch_dir_id.

        Returns:
            Path to watch directory or None if not found
        """
        try:
            result = self.database.execute(
                """
                SELECT absolute_path FROM watch_dir_paths WHERE watch_dir_id = ?
                """,
                (self.watch_dir_id,),
            )

            # Handle different result formats
            rows = []
            if isinstance(result, dict):
                if "data" in result and isinstance(result["data"], list):
                    rows = result["data"]
                elif isinstance(result, list):
                    rows = result
            elif isinstance(result, list):
                rows = result

            if not rows or len(rows) == 0:
                logger.error(
                    f"Watch directory {self.watch_dir_id} not found in database"
                )
                return None

            path_str = (
                rows[0].get("absolute_path") if isinstance(rows[0], dict) else rows[0]
            )
            if not path_str:
                logger.error(f"Watch directory {self.watch_dir_id} has no path set")
                return None

            watch_path = Path(path_str)
            if not watch_path.exists():
                logger.error(f"Watch directory path does not exist: {watch_path}")
                return None

            return watch_path

        except Exception as e:
            logger.error(
                f"Error getting watch_dir path for {self.watch_dir_id}: {e}",
                exc_info=True,
            )
            return None

    async def execute(self) -> Dict[str, Any]:
        """
        Execute project creation atomically.

        Returns:
            Dictionary with:
            - project_id: UUID4 identifier

        Raises:
            ValueError: If watch_dir_id not found or project_name invalid
        """
        transaction_id = None
        project_path = None
        projectid_path = None

        try:
            # Step 1: Get watch directory path from database
            watch_dir_path = self._get_watch_dir_path()
            if not watch_dir_path:
                return {
                    "success": False,
                    "error": "WATCH_DIR_NOT_FOUND",
                    "message": f"Watch directory {self.watch_dir_id} not found in database or path not set",
                }

            # Step 2: Validate project name
            if not self.project_name or not self.project_name.strip():
                return {
                    "success": False,
                    "error": "INVALID_PROJECT_NAME",
                    "message": "Project name cannot be empty",
                }

            # Step 3: Construct project path
            project_path = watch_dir_path / self.project_name.strip()

            # Step 4: Check if project directory already exists
            if project_path.exists():
                # Check if it's already registered
                from .base_mcp_command import BaseMCPCommand

                existing_project_id = BaseMCPCommand._get_project_id_by_root_path(
                    self.database, str(project_path)
                )
                if existing_project_id:
                    return {
                        "success": False,
                        "error": "PROJECT_ALREADY_EXISTS",
                        "message": f"Project directory already exists and is registered: {existing_project_id}",
                        "existing_project_id": existing_project_id,
                    }
                return {
                    "success": False,
                    "error": "PROJECT_DIR_EXISTS",
                    "message": f"Project directory already exists: {project_path}",
                }

            # Step 5: Generate or use provided project_id
            project_id = self.project_id or str(uuid.uuid4())

            # Step 6: Begin transaction
            transaction_id = self.database.begin_transaction()
            logger.info(f"Started transaction {transaction_id} for project creation")

            try:
                # Step 7: Create project directory
                project_path.mkdir(parents=True, exist_ok=False)
                logger.info(f"Created project directory: {project_path}")

                # Step 8: Create projectid file
                projectid_path = project_path / "projectid"
                project_data = {
                    "id": project_id,
                    "description": self.description,
                }
                projectid_path.write_text(
                    json.dumps(project_data, indent=4, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                logger.info(f"Created projectid file: {projectid_path}")

                # Step 9: Register project in database
                project_name = project_path.name
                self.database.execute(
                    """
                    INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, julianday('now'))
                    """,
                    (
                        project_id,
                        str(project_path),
                        project_name,
                        self.description,
                        self.watch_dir_id,
                    ),
                    transaction_id=transaction_id,
                )
                logger.info(f"Registered project in database: {project_id}")

                # Step 10: Commit transaction
                self.database.commit_transaction(transaction_id)
                logger.info(f"Committed transaction {transaction_id}")

                return {
                    "success": True,
                    "project_id": project_id,
                    "message": f"Created and registered new project: {project_id}",
                }

            except Exception as e:
                # Rollback transaction on error
                if transaction_id:
                    try:
                        self.database.rollback_transaction(transaction_id)
                        logger.info(f"Rolled back transaction {transaction_id}")
                    except Exception as rollback_error:
                        logger.error(f"Error during rollback: {rollback_error}")

                # Clean up created files/directories
                if projectid_path and projectid_path.exists():
                    try:
                        projectid_path.unlink()
                        logger.info(f"Removed projectid file: {projectid_path}")
                    except Exception:
                        pass

                if project_path and project_path.exists():
                    try:
                        project_path.rmdir()
                        logger.info(f"Removed project directory: {project_path}")
                    except Exception:
                        pass

                raise

        except Exception as e:
            logger.error(
                f"Error creating project: {e}",
                exc_info=True,
            )
            return {
                "success": False,
                "error": "CREATE_PROJECT_ERROR",
                "message": f"Failed to create project: {str(e)}",
            }

        # Step 4: Check if project is already registered in database
        from .base_mcp_command import BaseMCPCommand

        existing_project_id = BaseMCPCommand._get_project_id_by_root_path(
            self.database, str(project_path)
        )
        if existing_project_id:
            # Project is already registered - get existing info
            existing_project = self.database.get_project(existing_project_id)
            existing_description = existing_project.comment if existing_project else ""

            # Try to load projectid file if it exists
            projectid_path = project_path / "projectid"
            file_description = ""
            if projectid_path.exists():
                try:
                    project_info = load_project_info(project_path)
                    file_description = project_info.description
                except (ProjectIdError, InvalidProjectIdFormatError):
                    # File exists but is invalid - ignore
                    pass

            # Update watch_dir_id if needed
            if watch_dir_id and existing_project:
                existing_watch_dir_id = getattr(existing_project, "watch_dir_id", None)
                if existing_watch_dir_id != watch_dir_id:
                    self.database.execute(
                        """
                        UPDATE projects 
                        SET watch_dir_id = ?, updated_at = julianday('now')
                        WHERE id = ?
                        """,
                        (watch_dir_id, existing_project_id),
                    )
                    logger.info(
                        f"Updated project {existing_project_id} watch_dir_id to {watch_dir_id}"
                    )

            # Return existing project info
            return {
                "success": True,
                "project_id": existing_project_id,
                "already_existed": True,
                "description": file_description
                or existing_description
                or self.description,
                "old_description": existing_description,
                "watch_dir_id": watch_dir_id,
                "message": f"Project already registered: {existing_project_id}",
            }

        # Step 5: Check if projectid file exists in project directory
        projectid_path = project_path / "projectid"
        old_description = ""
        if projectid_path.exists():
            try:
                # Load existing projectid file
                project_info = load_project_info(project_path)
                project_id = project_info.project_id
                old_description = project_info.description

                # Register in database
                project_name = project_path.name
                self.database.execute(
                    """
                    INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, julianday('now'))
                    """,
                    (
                        project_id,
                        str(project_path),
                        project_name,
                        old_description or self.description,
                        watch_dir_id,
                    ),
                )

                logger.info(
                    f"Registered existing project {project_id} from projectid file: {project_path}"
                )

                return {
                    "success": True,
                    "project_id": project_id,
                    "already_existed": False,
                    "description": old_description or self.description,
                    "old_description": old_description,
                    "watch_dir_id": watch_dir_id,
                    "message": f"Registered project from existing projectid file: {project_id}",
                }
            except (ProjectIdError, InvalidProjectIdFormatError) as e:
                # File exists but is invalid - we'll recreate it
                logger.warning(
                    f"Invalid projectid file at {projectid_path}, will recreate: {e}"
                )
                old_description = ""

        # Step 6: Create new projectid file
        project_id = str(uuid.uuid4())
        final_description = (
            self.description or old_description or f"Project {project_path.name}"
        )

        project_data = {
            "id": project_id,
            "description": final_description,
        }

        try:
            projectid_path.write_text(
                json.dumps(project_data, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            logger.info(
                f"Created projectid file at {projectid_path} with ID {project_id}"
            )
        except Exception as e:
            return {
                "success": False,
                "error": "PROJECTID_WRITE_ERROR",
                "message": f"Failed to write projectid file: {str(e)}",
            }

        # Step 7: Register in database
        try:
            project_name = project_path.name
            self.database.execute(
                """
                INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)
                VALUES (?, ?, ?, ?, ?, julianday('now'))
                """,
                (
                    project_id,
                    str(project_path),
                    project_name,
                    final_description,
                    watch_dir_id,
                ),
            )

            logger.info(
                f"Registered new project {project_id} in database: {project_path}"
            )
        except Exception as e:
            # If database registration fails, try to clean up projectid file
            try:
                if projectid_path.exists():
                    projectid_path.unlink()
            except Exception:
                pass

            return {
                "success": False,
                "error": "DATABASE_REGISTRATION_ERROR",
                "message": f"Failed to register project in database: {str(e)}",
            }

        return {
            "success": True,
            "project_id": project_id,
            "already_existed": False,
            "description": final_description,
            "old_description": old_description,
            "watch_dir_id": watch_dir_id,
            "message": f"Created and registered new project: {project_id}",
        }
