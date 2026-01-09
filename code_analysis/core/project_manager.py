"""
Project manager for centralized project management.

Provides unified interface for creating, managing, and validating projects
with integration to git and database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional

from .constants import (
    DEFAULT_IGNORE_PATTERNS,
    GIT_IGNORE_PATTERNS,
    GITIGNORE_FILENAME,
    PROJECTID_FILENAME,
)
from .exceptions import (
    GitOperationError,
    InvalidProjectIdFormatError,
    ProjectIdError,
    ProjectNotFoundError,
)
from .git_integration import is_git_available, is_git_repository
from .project_resolution import ProjectInfo, load_project_info, normalize_root_dir
from .settings_manager import get_settings

logger = logging.getLogger(__name__)


class ProjectManager:
    """
    Centralized project manager for creating and managing projects.

    Provides methods for:
    - Creating new projects with optional git initialization
    - Retrieving project information
    - Validating project IDs
    - Synchronizing with database and filesystem
    """

    def __init__(self, database=None):
        """
        Initialize project manager.

        Args:
            database: Optional CodeDatabase instance for project storage
        """
        self.database = database
        self.settings = get_settings()

    def get_project_list(self, watch_dirs: Optional[List[Path]] = None) -> List[ProjectInfo]:
        """
        Get list of all projects.

        If database is available, retrieves projects from database.
        Otherwise, discovers projects from watch_dirs or filesystem.

        Args:
            watch_dirs: Optional list of watch directories to discover projects from

        Returns:
            List of ProjectInfo objects
        """
        projects: List[ProjectInfo] = []

        # Try to get projects from database first
        if self.database:
            try:
                db_projects = self.database.get_all_projects()
                for db_project in db_projects:
                    root_path = Path(db_project["root_path"])
                    if root_path.exists():
                        try:
                            project_info = load_project_info(root_path)
                            projects.append(project_info)
                        except (ProjectIdError, InvalidProjectIdFormatError) as e:
                            logger.warning(
                                f"Failed to load project info for {root_path}: {e}"
                            )
                            continue
            except Exception as e:
                logger.warning(f"Failed to get projects from database: {e}")

        # If no projects found in database, discover from watch_dirs
        if not projects and watch_dirs:
            from .project_discovery import discover_projects_in_directory

            for watch_dir in watch_dirs:
                watch_dir_path = Path(watch_dir).resolve()
                if not watch_dir_path.exists():
                    continue

                try:
                    discovered = discover_projects_in_directory(watch_dir_path)
                    for project_root in discovered:
                        project_info = load_project_info(project_root.root_path)
                        # Avoid duplicates
                        if not any(p.project_id == project_info.project_id for p in projects):
                            projects.append(project_info)
                except Exception as e:
                    logger.warning(f"Failed to discover projects in {watch_dir_path}: {e}")

        return projects

    def get_project_info(self, project_id: str) -> Optional[ProjectInfo]:
        """
        Get project information by project ID.

        Args:
            project_id: Project ID (UUID4 string)

        Returns:
            ProjectInfo if found, None otherwise

        Raises:
            ProjectNotFoundError: If project not found
        """
        # Try to get from database first
        if self.database:
            try:
                db_project = self.database.get_project(project_id)
                if db_project:
                    root_path = Path(db_project["root_path"])
                    if root_path.exists():
                        try:
                            return load_project_info(root_path)
                        except (ProjectIdError, InvalidProjectIdFormatError) as e:
                            logger.warning(
                                f"Failed to load project info for {root_path}: {e}"
                            )
            except Exception as e:
                logger.warning(f"Failed to get project from database: {e}")

        # If not found in database, search filesystem
        # This is expensive, but necessary for projects not yet in database
        raise ProjectNotFoundError(
            message=f"Project with ID {project_id} not found",
            project_id=project_id,
        )

    def create_project(
        self, root_path: Path, description: str = "", init_git: bool = False
    ) -> ProjectInfo:
        """
        Create a new project.

        Creates projectid file with UUID4 identifier and optional description.
        Optionally initializes git repository and creates .gitignore.

        Args:
            root_path: Root directory path for the project
            description: Human-readable description of the project
            init_git: If True, initialize git repository and create .gitignore

        Returns:
            ProjectInfo with project_id and description

        Raises:
            ProjectIdError: If projectid file already exists
            GitOperationError: If git initialization fails (only if init_git=True)
        """
        root_path = normalize_root_dir(root_path)
        projectid_path = root_path / PROJECTID_FILENAME

        # Check if project already exists
        if projectid_path.exists():
            try:
                existing_info = load_project_info(root_path)
                logger.info(
                    f"Project already exists at {root_path} with ID {existing_info.project_id}"
                )
                return existing_info
            except (ProjectIdError, InvalidProjectIdFormatError):
                # File exists but is invalid, we'll overwrite it
                logger.warning(f"Invalid projectid file at {projectid_path}, will recreate")

        # Generate new project ID
        project_id = str(uuid.uuid4())
        if not description:
            description = f"Project {project_id}"

        # Create projectid file in JSON format
        project_data = {
            "id": project_id,
            "description": description,
        }
        projectid_path.write_text(
            json.dumps(project_data, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info(f"Created projectid file at {projectid_path} with ID {project_id}")

        # Initialize git if requested
        if init_git:
            self._init_git_repository(root_path, description)

        # Create project info
        project_info = ProjectInfo(
            root_path=root_path, project_id=project_id, description=description
        )

        # Register in database if available
        if self.database:
            try:
                self.database.get_or_create_project(
                    root_path=str(root_path),
                    name=Path(root_path).name,
                    comment=description,
                )
                logger.info(f"Registered project {project_id} in database")
            except Exception as e:
                logger.warning(f"Failed to register project in database: {e}")

        return project_info

    def _init_git_repository(self, root_path: Path, description: str) -> None:
        """
        Initialize git repository and create .gitignore.

        Args:
            root_path: Root directory path
            description: Project description for initial commit message

        Raises:
            GitOperationError: If git initialization fails
        """
        # Check if git is available
        if not is_git_available():
            logger.warning("Git is not available, skipping git initialization")
            return

        # Check if already a git repository
        if is_git_repository(root_path):
            logger.info(f"Directory {root_path} is already a git repository")
            return

        try:
            # Initialize git repository
            result = subprocess.run(
                ["git", "init"],
                cwd=root_path,
                capture_output=True,
                text=True,
                timeout=self.settings.get("git_timeout", 10.0),
            )
            if result.returncode != 0:
                raise GitOperationError(
                    message=f"Failed to initialize git repository: {result.stderr}",
                    operation="init",
                    git_command="git init",
                )
            logger.info(f"Initialized git repository at {root_path}")

            # Create .gitignore file
            gitignore_path = root_path / GITIGNORE_FILENAME
            if not gitignore_path.exists():
                ignore_patterns = set(DEFAULT_IGNORE_PATTERNS) | set(GIT_IGNORE_PATTERNS)
                gitignore_content = "\n".join(sorted(ignore_patterns)) + "\n"
                gitignore_path.write_text(gitignore_content, encoding="utf-8")
                logger.info(f"Created .gitignore file at {gitignore_path}")

            # Stage projectid and .gitignore
            for file_path in [PROJECTID_FILENAME, GITIGNORE_FILENAME]:
                result = subprocess.run(
                    ["git", "add", file_path],
                    cwd=root_path,
                    capture_output=True,
                    text=True,
                    timeout=self.settings.get("git_timeout", 10.0),
                )
                if result.returncode != 0:
                    logger.warning(f"Failed to stage {file_path}: {result.stderr}")

            # Create initial commit
            commit_message = f"Initial commit: Project {description}"
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=root_path,
                capture_output=True,
                text=True,
                timeout=self.settings.get("git_timeout", 10.0),
            )
            if result.returncode != 0:
                logger.warning(f"Failed to create initial commit: {result.stderr}")
            else:
                logger.info(f"Created initial commit: {commit_message}")

        except subprocess.TimeoutExpired:
            raise GitOperationError(
                message="Git command timed out",
                operation="init",
                git_command="git init",
            )
        except Exception as e:
            logger.error(f"Error initializing git repository: {e}")
            raise GitOperationError(
                message=f"Failed to initialize git repository: {str(e)}",
                operation="init",
                git_command="git init",
            ) from e

    def validate_project_id(self, root_path: Path, project_id: str) -> bool:
        """
        Validate that project_id matches the projectid file in root_path.

        Args:
            root_path: Project root directory
            project_id: Project ID to validate

        Returns:
            True if project_id matches, False otherwise

        Raises:
            ProjectIdError: If projectid file is missing or invalid
        """
        root_path = normalize_root_dir(root_path)
        try:
            project_info = load_project_info(root_path)
            return project_info.project_id == project_id
        except (ProjectIdError, InvalidProjectIdFormatError) as e:
            logger.warning(f"Failed to validate project_id: {e}")
            return False

