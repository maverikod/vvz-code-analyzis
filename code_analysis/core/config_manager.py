"""
Config manager (compatibility + facade).

Some tests and legacy integrations expect `code_analysis.core.config_manager`.
The current project keeps most config models in `code_analysis.core.config`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from .config import ProjectDir, ServerConfig, generate_config as generate_config_dict
from .config import load_config as load_config_file
from .config import validate_config as validate_config_file


def validate_config(config_data: dict[str, Any]) -> ServerConfig:
    """
    Validate in-memory config dict and return a `ServerConfig`.

    This function exists because some tests (and older code paths) validate a dict,
    not a JSON file path.
    """
    config = ServerConfig(**config_data)

    # Additional validations: duplicates (kept here for backward compatibility)
    ids = [d.id for d in config.dirs]
    names = [d.name for d in config.dirs]
    if len(ids) != len(set(ids)):
        duplicates = {i for i in ids if ids.count(i) > 1}
        raise ValueError(f"Duplicate project IDs found: {duplicates}")
    if len(names) != len(set(names)):
        duplicates = {n for n in names if names.count(n) > 1}
        raise ValueError(f"Duplicate project names found: {duplicates}")
    return config


class ConfigManager:
    """
    Manage reading/writing/validating server configuration files.

    This is a thin facade over `code_analysis.core.config`.
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = Path(config_path)
        self._config: Optional[ServerConfig] = None

    def read(self) -> ServerConfig:
        """Read and validate config file."""
        if not self.config_path.exists():
            raise FileNotFoundError(str(self.config_path))
        if self._config is None:
            self._config = load_config_file(self.config_path)
        return self._config

    def write(self, config: ServerConfig) -> None:
        """Write config to disk as JSON."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(config.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._config = None

    def validate_config_file(
        self,
    ) -> tuple[bool, Optional[str], Optional[ServerConfig]]:
        """Validate config file and return (ok, error, config)."""
        return validate_config_file(self.config_path)

    def _read_or_default(self) -> ServerConfig:
        """
        Read config if exists, otherwise create a minimal default config.

        Default values match tests:
        - host=127.0.0.1
        - port=15000
        """
        if self.config_path.exists():
            return self.read()
        return ServerConfig(host="127.0.0.1", port=15000, dirs=[])

    def list_projects(self) -> list[ProjectDir]:
        """List configured project directories."""
        if not self.config_path.exists():
            return []
        cfg = self.read()
        return list(cfg.dirs)

    def get_project(self, project_id: str) -> Optional[ProjectDir]:
        """Get a project by UUID4 string. Returns None if invalid or not found."""
        try:
            # Validate UUID4 format via ProjectDir validator expectations.
            # We keep it simple here: if uuid parsing fails, treat as invalid.
            import uuid

            uuid.UUID(project_id, version=4)
        except Exception:
            return None

        if not self.config_path.exists():
            return None
        for p in self.read().dirs:
            if p.id == project_id:
                return p
        return None

    def add_project(
        self, name: str, path: str, project_id: Optional[str] = None
    ) -> str:
        """
        Add a project directory to config.

        Raises:
            ValueError on duplicate name/id or invalid path/uuid.
        """
        cfg = self._read_or_default()

        if any(p.name == name for p in cfg.dirs):
            raise ValueError(f"Project with name '{name}' already exists")

        if project_id is None:
            import uuid

            project_id = str(uuid.uuid4())
        else:
            # Validate UUID
            import uuid

            try:
                uuid.UUID(project_id, version=4)
            except Exception as e:
                raise ValueError("Invalid UUID") from e

        if any(p.id == project_id for p in cfg.dirs):
            raise ValueError(f"Project with id '{project_id}' already exists")

        p = Path(path)
        if not p.is_absolute():
            raise ValueError("Path must be absolute")
        if not p.exists():
            raise ValueError("Path does not exist")
        if not p.is_dir():
            raise ValueError("Path must be a directory")

        new_dirs = list(cfg.dirs) + [
            ProjectDir(id=project_id, name=name, path=str(p.resolve()))
        ]
        new_cfg = cfg.model_copy(update={"dirs": new_dirs})
        self.write(new_cfg)
        return project_id

    def remove_project(self, project_id: str) -> bool:
        """
        Remove project by id. Returns False if not found or config missing.

        Raises:
            ValueError if UUID is invalid.
        """
        import uuid

        try:
            uuid.UUID(project_id, version=4)
        except Exception as e:
            raise ValueError("Invalid UUID") from e

        if not self.config_path.exists():
            return False

        cfg = self.read()
        new_dirs = [p for p in cfg.dirs if p.id != project_id]
        if len(new_dirs) == len(cfg.dirs):
            return False
        new_cfg = cfg.model_copy(update={"dirs": new_dirs})
        self.write(new_cfg)
        return True

    def update_project(
        self,
        project_id: str,
        *,
        name: Optional[str] = None,
        path: Optional[str] = None,
    ) -> bool:
        """
        Update project fields. Returns False if project not found or config missing.

        Raises:
            ValueError on invalid UUID, invalid path, or duplicate name.
        """
        import uuid

        try:
            uuid.UUID(project_id, version=4)
        except Exception as e:
            raise ValueError("Invalid UUID") from e

        if not self.config_path.exists():
            return False

        cfg = self.read()
        target = None
        for p in cfg.dirs:
            if p.id == project_id:
                target = p
                break
        if target is None:
            return False

        if name is not None:
            if any(p.name == name and p.id != project_id for p in cfg.dirs):
                raise ValueError(f"Project with name '{name}' already exists")

        new_path = None
        if path is not None:
            pth = Path(path)
            if not pth.is_absolute():
                raise ValueError("Path must be absolute")
            if not pth.exists():
                raise ValueError("Path does not exist")
            if not pth.is_dir():
                raise ValueError("Path must be a directory")
            new_path = str(pth.resolve())

        new_dirs: list[ProjectDir] = []
        for p in cfg.dirs:
            if p.id != project_id:
                new_dirs.append(p)
                continue
            upd = {"name": p.name, "path": p.path}
            if name is not None:
                upd["name"] = name
            if new_path is not None:
                upd["path"] = new_path
            new_dirs.append(ProjectDir(id=p.id, name=upd["name"], path=upd["path"]))

        new_cfg = cfg.model_copy(update={"dirs": new_dirs})
        self.write(new_cfg)
        return True

    def generate_config(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db_path: Optional[str] = None,
        overwrite: bool = False,
    ) -> ServerConfig:
        """
        Generate a config using CLI args overriding env vars.

        Environment variables supported (legacy):
        - CODE_ANALYSIS_HOST
        - CODE_ANALYSIS_PORT
        - CODE_ANALYSIS_DB_PATH
        """
        env_host = os.getenv("CODE_ANALYSIS_HOST")
        env_port = os.getenv("CODE_ANALYSIS_PORT")
        env_db_path = os.getenv("CODE_ANALYSIS_DB_PATH")

        final_host = host or env_host or "0.0.0.0"
        final_port = port if port is not None else int(env_port) if env_port else 15000
        final_db_path = db_path or env_db_path

        cfg_dict = generate_config_dict(
            host=final_host,
            port=final_port,
            db_path=final_db_path,
        )
        cfg = ServerConfig(**cfg_dict)

        if overwrite or not self.config_path.exists():
            self.write(cfg)
        return cfg


__all__ = ["ConfigManager", "validate_config"]
