"""
MCP server manager.

Manages MCP server lifecycle: start, stop, status, config generation/validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import subprocess
import signal
import os
import socket
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .core.config import (
    generate_config,
    validate_config,
    load_config,
    save_config,
    ServerConfig,
)
from .core.database import CodeDatabase

logger = logging.getLogger(__name__)


class ServerManager:
    """Manages MCP server process."""

    def __init__(self, config_path: Path, pid_file: Optional[Path] = None):
        """
        Initialize server manager.

        Args:
            config_path: Path to server configuration file
            pid_file: Path to PID file (default: config_path.parent / "server.pid")
        """
        self.config_path = Path(config_path)
        self.pid_file = pid_file or self.config_path.parent / "server.pid"

    def _read_pid(self) -> Optional[int]:
        """Read process ID from PID file."""
        if not self.pid_file.exists():
            return None
        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())
            return pid
        except (ValueError, IOError):
            return None

    def _write_pid(self, pid: int) -> None:
        """Write process ID to PID file."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pid_file, "w") as f:
            f.write(str(pid))

    def _remove_pid(self) -> None:
        """Remove PID file."""
        if self.pid_file.exists():
            self.pid_file.unlink()

    def _is_process_running(self, pid: int) -> bool:
        """Check if process is running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def start(self) -> Dict[str, Any]:
        """
        Start MCP server.

        Returns:
            Dictionary with status information
        """
        # Validate config
        is_valid, error, config = validate_config(self.config_path)
        if not is_valid:
            return {
                "success": False,
                "message": f"Configuration validation failed: {error}",
            }

        if config is None:
            return {
                "success": False,
                "message": "Failed to load configuration",
            }

        # Validate project IDs and names (UUID4 format, no duplicates)
        ids_valid, ids_error = self._validate_project_ids_and_names(config)
        if not ids_valid:
            return {
                "success": False,
                "message": f"Project validation failed: {ids_error}",
            }

        # Validate paths exist
        paths_valid, path_error = self._validate_paths(config)
        if not paths_valid:
            return {
                "success": False,
                "message": f"Path validation failed: {path_error}",
            }

        # Check if port is available
        if not self._is_port_available(config.host, config.port):
            return {
                "success": False,
                "message": f"Port {config.port} is already in use on {config.host}",
            }

        # Validate database path exists
        if config.db_path:
            db_path = Path(config.db_path)
            if not db_path.exists():
                return {
                    "success": False,
                    "message": f"Database not found: {db_path}. "
                    "Please create database first using 'server create-db' command.",
                }
            if not db_path.is_file():
                return {
                    "success": False,
                    "message": f"Database path exists but is not a file: {db_path}",
                }
        else:
            # Check if default database exists for any project
            for dir_info in config.dirs:
                default_db = Path(dir_info.path) / "code_analysis" / "code_analysis.db"
                if not default_db.exists():
                    return {
                        "success": False,
                        "message": f"Database not found for project '{dir_info.name}': {default_db}. "
                        "Please create database first using 'server create-db' command.",
                    }

        # Check if already running
        pid = self._read_pid()
        if pid and self._is_process_running(pid):
            return {
                "success": False,
                "message": f"Server is already running (PID: {pid})",
                "pid": pid,
            }

        # Start server
        try:
            cmd = [
                "python",
                "-m",
                "code_analysis.mcp_server",
                "--host",
                config.host,
                "--port",
                str(config.port),
            ]

            # Add log file if specified
            if config.log:
                cmd.extend(["--log-level", "INFO"])
                # Redirect output to log file
                log_file = open(config.log, "a")
            else:
                log_file = None

            # Start in background
            process = subprocess.Popen(
                cmd,
                stdout=log_file or subprocess.PIPE,
                stderr=log_file or subprocess.PIPE,
                start_new_session=True,
            )

            if log_file:
                # Don't close log file, let process handle it
                pass

            self._write_pid(process.pid)

            logger.info(f"Server started with PID: {process.pid}")
            return {
                "success": True,
                "message": f"Server started successfully",
                "pid": process.pid,
                "host": config.host,
                "port": config.port,
            }
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return {
                "success": False,
                "message": f"Failed to start server: {str(e)}",
            }

    def stop(self) -> Dict[str, Any]:
        """
        Stop MCP server.

        Returns:
            Dictionary with status information
        """
        pid = self._read_pid()
        if not pid:
            return {
                "success": False,
                "message": "Server is not running (no PID file found)",
            }

        if not self._is_process_running(pid):
            self._remove_pid()
            return {
                "success": False,
                "message": f"Server process not found (PID: {pid})",
            }

        try:
            # Try graceful shutdown
            os.kill(pid, signal.SIGTERM)
            # Wait a bit
            import time

            time.sleep(1)

            # Check if still running
            if self._is_process_running(pid):
                # Force kill
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)

            self._remove_pid()
            logger.info(f"Server stopped (PID: {pid})")
            return {
                "success": True,
                "message": "Server stopped successfully",
                "pid": pid,
            }
        except ProcessLookupError:
            self._remove_pid()
            return {
                "success": False,
                "message": f"Process not found (PID: {pid})",
            }
        except Exception as e:
            logger.error(f"Failed to stop server: {e}")
            return {
                "success": False,
                "message": f"Failed to stop server: {str(e)}",
            }

    def status(self) -> Dict[str, Any]:
        """
        Get server status.

        Returns:
            Dictionary with status information
        """
        pid = self._read_pid()
        if not pid:
            return {
                "running": False,
                "message": "Server is not running (no PID file found)",
            }

        if not self._is_process_running(pid):
            self._remove_pid()
            return {
                "running": False,
                "message": f"Server process not found (PID: {pid})",
            }

        # Try to load config for additional info
        config_info = {}
        try:
            is_valid, _, config = validate_config(self.config_path)
            if is_valid and config:
                config_info = {
                    "host": config.host,
                    "port": config.port,
                    "projects": len(config.dirs),
                }
        except Exception:
            pass

        return {
            "running": True,
            "pid": pid,
            "message": f"Server is running (PID: {pid})",
            **config_info,
        }

    def generate_config(
        self,
        host: str = "127.0.0.1",
        port: int = 15000,
        dirs: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate configuration file.

        Args:
            host: Server host
            port: Server port
            log: Path to log file (optional)
            db_path: Path to SQLite database (optional)
            dirs: List of directories with 'name' and 'path' keys

        Returns:
            Dictionary with status information
        """
        try:
            config = generate_config(
                host=host, port=port, log=log, db_path=db_path, dirs=dirs
            )
            save_config(config, self.config_path)
            logger.info(f"Configuration generated: {self.config_path}")
            return {
                "success": True,
                "message": f"Configuration generated: {self.config_path}",
                "config": config,
            }
        except Exception as e:
            logger.error(f"Failed to generate configuration: {e}")
            return {
                "success": False,
                "message": f"Failed to generate configuration: {str(e)}",
            }

    def validate_config(self) -> Dict[str, Any]:
        """
        Validate configuration file.

        Returns:
            Dictionary with validation result
        """
        is_valid, error, config = validate_config(self.config_path)

        if not is_valid:
            return {
                "valid": False,
                "message": error or "Configuration is invalid",
            }

        if config is None:
            return {
                "valid": False,
                "message": "Failed to load configuration",
            }

        return {
            "valid": True,
            "message": "Configuration is valid",
            "config": {
                "host": config.host,
                "port": config.port,
                "log": config.log,
                "db_path": config.db_path,
                "projects": len(config.dirs),
                "dirs": [
                    {"id": d.id, "name": d.name, "path": d.path} for d in config.dirs
                ],
            },
        }

    def create_database(
        self, db_path: Optional[str] = None, project_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create new database and initialize projects.

        Args:
            db_path: Path to database file (optional, uses config if not provided)
            project_paths: List of project paths to initialize (optional)

        Returns:
            Dictionary with status information
        """
        try:
            # Determine database path
            if db_path:
                db_path_obj = Path(db_path)
            else:
                # Load config to get db_path or use default
                is_valid, error, config = validate_config(self.config_path)
                if not is_valid or config is None:
                    return {
                        "success": False,
                        "message": f"Cannot determine database path: {error}",
                    }

                if config.db_path:
                    db_path_obj = Path(config.db_path)
                else:
                    # Use first project's default database
                    if not config.dirs:
                        return {
                            "success": False,
                            "message": "No projects configured and no db_path specified",
                        }
                    db_path_obj = (
                        Path(config.dirs[0].path) / "code_analysis" / "code_analysis.db"
                    )

            # Ensure parent directory exists
            db_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Check if database already exists
            if db_path_obj.exists():
                return {
                    "success": False,
                    "message": f"Database already exists: {db_path_obj}",
                }

            # Create database (CodeDatabase creates schema on init)
            database = CodeDatabase(db_path_obj)

            # Initialize projects if paths provided
            projects_created = []
            if project_paths:
                for project_path in project_paths:
                    path_obj = Path(project_path)
                    if not path_obj.exists():
                        logger.warning(f"Project path does not exist: {project_path}")
                        continue
                    if not path_obj.is_dir():
                        logger.warning(
                            f"Project path is not a directory: {project_path}"
                        )
                        continue

                    project_id = database.get_or_create_project(
                        str(path_obj.resolve()), name=path_obj.name
                    )
                    projects_created.append(
                        {
                            "id": project_id,
                            "name": path_obj.name,
                            "path": str(path_obj),
                        }
                    )

            database.close()

            logger.info(f"Database created: {db_path_obj}")
            return {
                "success": True,
                "message": f"Database created successfully: {db_path_obj}",
                "db_path": str(db_path_obj),
                "projects_initialized": len(projects_created),
                "projects": projects_created,
            }
        except Exception as e:
            logger.error(f"Failed to create database: {e}")
            return {
                "success": False,
                "message": f"Failed to create database: {str(e)}",
            }
