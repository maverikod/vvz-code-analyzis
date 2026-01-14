"""
Internal commands for project creation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
import uuid
from typing import Any, Dict, TYPE_CHECKING

from ..core.exceptions import (
    InvalidProjectIdFormatError,
    ProjectIdError,
)
from ..core.project_resolution import (
    load_project_info,
    normalize_root_dir,
)

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
        watched_dir: str,
        project_dir: str,
        description: str = "",
    ):
        """
        Initialize create project command.

        Args:
            database: DatabaseClient instance
            watched_dir: Watched directory path (must exist, must not contain projectid)
            project_dir: Project directory path (must exist, must not be registered)
            description: Human-readable description of the project
        """
        self.database = database
        self.watched_dir = watched_dir
        self.project_dir = project_dir
        self.description = description

    async def execute(self) -> Dict[str, Any]:
        """
        Execute project creation.

        Returns:
            Dictionary with:
            - project_id: UUID4 identifier
            - already_existed: Whether project already existed
            - description: Project description (from file if existed, or provided)
            - old_description: Old description if project was recreated

        Raises:
            FileNotFoundError: If watched_dir or project_dir does not exist
            ProjectIdError: If watched_dir contains projectid file
            ValidationError: If project_dir is already registered in database
        """
        # Step 1: Validate watched directory exists
        try:
            watched_path = normalize_root_dir(self.watched_dir)
        except FileNotFoundError:
            return {
                "success": False,
                "error": "WATCHED_DIR_NOT_FOUND",
                "message": f"Watched directory does not exist: {self.watched_dir}",
            }
        except NotADirectoryError:
            return {
                "success": False,
                "error": "WATCHED_DIR_NOT_DIRECTORY",
                "message": f"Watched path is not a directory: {self.watched_dir}",
            }

        # Step 2: Check if watched directory has projectid file
        watched_projectid_path = watched_path / "projectid"
        if watched_projectid_path.exists():
            try:
                # Try to load it to get project info
                watched_info = load_project_info(watched_path)
                return {
                    "success": False,
                    "error": "PROJECTID_EXISTS_IN_WATCHED_DIR",
                    "message": (
                        f"Watched directory already contains projectid file with project_id: "
                        f"{watched_info.project_id}"
                    ),
                    "existing_project_id": watched_info.project_id,
                }
            except (ProjectIdError, InvalidProjectIdFormatError) as e:
                # File exists but is invalid - this is also an error
                return {
                    "success": False,
                    "error": "INVALID_PROJECTID_IN_WATCHED_DIR",
                    "message": f"Watched directory contains invalid projectid file: {str(e)}",
                }

        # Step 3: Validate project directory exists
        try:
            project_path = normalize_root_dir(self.project_dir)
        except FileNotFoundError:
            return {
                "success": False,
                "error": "PROJECT_DIR_NOT_FOUND",
                "message": f"Project directory does not exist: {self.project_dir}",
            }
        except NotADirectoryError:
            return {
                "success": False,
                "error": "PROJECT_DIR_NOT_DIRECTORY",
                "message": f"Project path is not a directory: {self.project_dir}",
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

            # Return existing project info
            return {
                "success": True,
                "project_id": existing_project_id,
                "already_existed": True,
                "description": file_description
                or existing_description
                or self.description,
                "old_description": existing_description,
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
                    INSERT INTO projects (id, root_path, name, comment, updated_at)
                    VALUES (?, ?, ?, ?, julianday('now'))
                    """,
                    (
                        project_id,
                        str(project_path),
                        project_name,
                        old_description or self.description,
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
                INSERT INTO projects (id, root_path, name, comment, updated_at)
                VALUES (?, ?, ?, ?, julianday('now'))
                """,
                (project_id, str(project_path), project_name, final_description),
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
            "message": f"Created and registered new project: {project_id}",
        }
