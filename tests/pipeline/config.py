"""
Test pipeline configuration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


class PipelineConfig:
    """Configuration for test pipeline."""

    def __init__(
        self,
        test_data_dir: Optional[Path] = None,
        test_db_path: Optional[Path] = None,
        server_config_path: Optional[Path] = None,
        server_host: str = "127.0.0.1",
        server_port: int = 15001,
        timeout: int = 300,
    ):
        """Initialize pipeline configuration.

        Args:
            test_data_dir: Path to test_data directory
            test_db_path: Path to test database file
            server_config_path: Path to server config file
            server_host: Server host for testing
            server_port: Server port for testing
            timeout: Test timeout in seconds
        """
        self.test_data_dir = (
            test_data_dir or Path(__file__).parent.parent.parent / "test_data"
        )
        self.test_db_path = (
            test_db_path or Path(tempfile.gettempdir()) / "test_code_analysis.db"
        )
        self.server_config_path = server_config_path
        self.server_host = server_host
        self.server_port = server_port
        self.timeout = timeout

    def get_test_projects(self) -> list[Path]:
        """Get list of test project directories.

        Returns:
            List of project paths
        """
        projects = []
        if not self.test_data_dir.exists():
            return projects

        for item in self.test_data_dir.iterdir():
            if item.is_dir() and (item / "projectid").exists():
                projects.append(item)

        return projects

    def create_test_config(self, output_path: Path) -> None:
        """Create test server configuration file.

        Args:
            output_path: Path to write config file
        """
        # Load base config if exists
        base_config_path = Path(__file__).parent.parent.parent / "config.json"
        if base_config_path.exists():
            with open(base_config_path, "r", encoding="utf-8") as f:
                config: Dict[str, Any] = json.load(f)
        else:
            config = {}

        # Override server settings for testing
        if "server" not in config:
            config["server"] = {}
        config["server"]["host"] = self.server_host
        config["server"]["port"] = self.server_port

        # Override database path for testing
        if "code_analysis" not in config:
            config["code_analysis"] = {}
        config["code_analysis"]["db_path"] = str(self.test_db_path)

        # Add test_data to watch_dirs if not exists
        if "code_analysis" in config:
            if "worker" not in config["code_analysis"]:
                config["code_analysis"]["worker"] = {}
            if "watch_dirs" not in config["code_analysis"]["worker"]:
                config["code_analysis"]["worker"]["watch_dirs"] = []

            # Check if test_data already in watch_dirs
            test_data_path = str(self.test_data_dir.absolute())
            watch_dirs = config["code_analysis"]["worker"]["watch_dirs"]
            if isinstance(watch_dirs, list):
                found = False
                for watch_dir in watch_dirs:
                    if (
                        isinstance(watch_dir, dict)
                        and watch_dir.get("path") == test_data_path
                    ):
                        found = True
                        break
                    elif isinstance(watch_dir, str) and watch_dir == test_data_path:
                        found = True
                        break

                if not found:
                    watch_dirs.append({"id": "test-pipeline", "path": test_data_path})

        # Write config
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def verify_test_data(self) -> bool:
        """Verify test data is available.

        Returns:
            True if test data is available
        """
        if not self.test_data_dir.exists():
            return False

        projects = self.get_test_projects()
        return len(projects) > 0
