"""
Configuration manager for server configuration.

Provides methods for reading, writing, and managing project directories
in server configuration files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from .config import ProjectDir, ServerConfig


def validate_config(data: dict) -> ServerConfig:
    """
    Validate configuration data.

    Args:
        data: Configuration dictionary

    Returns:
        ServerConfig instance

    Raises:
        ValueError: If configuration is invalid
    """
    try:
        config = ServerConfig(**data)

        # Additional validations: check for duplicate IDs and names
        ids = [d.id for d in config.dirs]
        names = [d.name for d in config.dirs]

        # Check for duplicate IDs
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Duplicate project IDs found: {set(duplicates)}")

        # Check for duplicate names
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(f"Duplicate project names found: {set(duplicates)}")

        return config
    except Exception as e:
        raise ValueError(f"Invalid configuration: {str(e)}")


logger = logging.getLogger(__name__)


class ConfigManager:
    """Manager for server configuration files."""

    def __init__(self, config_path: Path):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self._config: Optional[ServerConfig] = None

    def read(self) -> ServerConfig:
        """
        Read configuration from file.

        Returns:
            ServerConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                # Empty file - return default config
                from .config import ServerConfig

                return ServerConfig()
            data = json.loads(content)

        self._config = validate_config(data)
        return self._config

    def write(self, config: Optional[ServerConfig] = None) -> None:
        """
        Write configuration to file.

        Args:
            config: ServerConfig to write (uses cached config if not provided)
        """
        if config is None:
            if self._config is None:
                raise ValueError("No configuration to write")
            config = self._config

        # Convert to dict
        config_dict = {
            "host": config.host,
            "port": config.port,
            "log": config.log,
            "db_path": config.db_path,
            "dirs": [
                {
                    "id": d.id,
                    "name": d.name,
                    "path": d.path,
                }
                for d in config.dirs
            ],
        }

        # Write to file
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

        self._config = config
        logger.info(f"Configuration written to {self.config_path}")

    def add_project(
        self,
        name: str,
        path: str,
        project_id: Optional[str] = None,
    ) -> str:
        """
        Add project to configuration.

        Args:
            name: Human-readable project name
            path: Absolute path to project directory
            project_id: Optional UUID4 (generated if not provided)

        Returns:
            Project UUID

        Raises:
            ValueError: If name or path is invalid, or if project already exists
        """
        # Read current config if not cached
        if self._config is None:
            try:
                self.read()
            except FileNotFoundError:
                # Create default config
                self._config = ServerConfig()

        # Validate UUID if provided
        if project_id:
            try:
                UUID(project_id)
            except ValueError:
                raise ValueError(f"Invalid UUID format: {project_id}")

            # Check for duplicate ID
            if any(d.id == project_id for d in self._config.dirs):
                raise ValueError(f"Project with ID {project_id} already exists")
        else:
            # Generate new UUID
            project_id = str(uuid4())

        # Check for duplicate name
        if any(d.name == name for d in self._config.dirs):
            raise ValueError(f"Project with name '{name}' already exists")

        # Validate path
        path_obj = Path(path)
        if not path_obj.is_absolute():
            raise ValueError(f"Path must be absolute: {path}")
        if not path_obj.exists():
            raise ValueError(f"Path does not exist: {path}")

        # Create project directory
        project_dir = ProjectDir(id=project_id, name=name, path=str(path_obj.resolve()))

        # Add to config
        self._config.dirs.append(project_dir)

        # Write config
        self.write()

        logger.info(f"Added project: {name} ({project_id}) at {path}")
        return project_id

    def remove_project(self, project_id: str) -> bool:
        """
        Remove project from configuration.

        Args:
            project_id: Project UUID to remove

        Returns:
            True if project was removed, False if not found

        Raises:
            ValueError: If UUID format is invalid
        """
        # Validate UUID
        try:
            UUID(project_id)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {project_id}")

        # Read current config if not cached
        if self._config is None:
            try:
                self.read()
            except FileNotFoundError:
                return False

        # Find and remove project
        initial_count = len(self._config.dirs)
        self._config.dirs = [d for d in self._config.dirs if d.id != project_id]

        if len(self._config.dirs) < initial_count:
            # Write config
            self.write()
            logger.info(f"Removed project: {project_id}")
            return True

        return False

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        path: Optional[str] = None,
    ) -> bool:
        """
        Update project data in configuration.

        Args:
            project_id: Project UUID to update
            name: New name (optional)
            path: New path (optional)

        Returns:
            True if project was updated, False if not found

        Raises:
            ValueError: If UUID format is invalid or if name/path is invalid
        """
        # Validate UUID
        try:
            UUID(project_id)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {project_id}")

        # Read current config if not cached
        if self._config is None:
            try:
                self.read()
            except FileNotFoundError:
                return False

        # Find project
        project = None
        for d in self._config.dirs:
            if d.id == project_id:
                project = d
                break

        if project is None:
            return False

        # Update name if provided
        if name is not None:
            # Check for duplicate name (excluding current project)
            if any(d.name == name and d.id != project_id for d in self._config.dirs):
                raise ValueError(f"Project with name '{name}' already exists")
            project.name = name

        # Update path if provided
        if path is not None:
            path_obj = Path(path)
            if not path_obj.is_absolute():
                raise ValueError(f"Path must be absolute: {path}")
            if not path_obj.exists():
                raise ValueError(f"Path does not exist: {path}")
            project.path = str(path_obj.resolve())

        # Write config
        self.write()

        logger.info(f"Updated project: {project_id}")
        return True

    def get_project(self, project_id: str) -> Optional[ProjectDir]:
        """
        Get project by UUID.

        Args:
            project_id: Project UUID

        Returns:
            ProjectDir if found, None otherwise
        """
        # Validate UUID
        try:
            UUID(project_id)
        except ValueError:
            return None

        # Read current config if not cached
        if self._config is None:
            try:
                self.read()
            except FileNotFoundError:
                return None

        # Find project
        for d in self._config.dirs:
            if d.id == project_id:
                return d

        return None

    def list_projects(self) -> List[ProjectDir]:
        """
        List all projects in configuration.

        Returns:
            List of ProjectDir instances
        """
        # Read current config if not cached
        if self._config is None:
            try:
                self.read()
            except FileNotFoundError:
                return []

        return self._config.dirs.copy()
