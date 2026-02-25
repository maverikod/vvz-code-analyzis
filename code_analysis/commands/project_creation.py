"""
Internal commands for project creation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

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
    2. If project dir exists and not use_existing_dir: fails with PROJECT_DIR_EXISTS
    3. If project dir exists and use_existing_dir: creates only projectid file and registers
    4. If project dir does not exist: creates dir, projectid file, and registers in database

    Returns project ID, whether project already existed, and description.
    """

    def __init__(
        self,
        database: DatabaseClient,
        watch_dir_id: str,
        project_name: str,
        description: str,
        project_id: Optional[str] = None,
        use_existing_dir: bool = False,
    ):
        """
        Initialize create project command.

        Args:
            database: DatabaseClient instance
            watch_dir_id: Watch directory ID from watch_dirs table (must exist)
            project_name: Name of project subdirectory to create in watch_dir
            description: Human-readable description of the project (required)
            project_id: Optional project ID (UUID4). If not provided, will be generated.
            use_existing_dir: If True, when project directory already exists, create only
                projectid file and register in DB instead of failing with PROJECT_DIR_EXISTS.
        """
        self.database = database
        self.watch_dir_id = watch_dir_id
        self.project_name = project_name
        self.description = description
        self.project_id = project_id
        self.use_existing_dir = use_existing_dir

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
                if not self.use_existing_dir:
                    return {
                        "success": False,
                        "error": "PROJECT_DIR_EXISTS",
                        "message": f"Project directory already exists: {project_path}",
                    }
                # use_existing_dir: create only projectid file and register
                project_id = self.project_id or str(uuid.uuid4())
                projectid_path = project_path / "projectid"
                project_data = {
                    "id": project_id,
                    "description": self.description,
                }
                projectid_path.write_text(
                    json.dumps(project_data, indent=4, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                logger.info(
                    f"Created projectid file in existing directory: {projectid_path}"
                )
                project_name_val = project_path.name
                self.database.execute(
                    """
                    INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, julianday('now'))
                    """,
                    (
                        project_id,
                        str(project_path),
                        project_name_val,
                        self.description,
                        self.watch_dir_id,
                    ),
                )
                logger.info(f"Registered project in database: {project_id}")
                return {
                    "success": True,
                    "project_id": project_id,
                    "message": (
                        f"Created projectid in existing directory and registered: {project_id}"
                    ),
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

            except Exception:
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
