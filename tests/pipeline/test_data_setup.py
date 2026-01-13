"""
Test data setup utilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from code_analysis.core.database.base import CodeDatabase

if TYPE_CHECKING:
    from tests.pipeline.config import PipelineConfig


class TestDataSetup:
    """Utilities for setting up test data."""

    def __init__(self, config: "PipelineConfig"):  # noqa: F821
        """Initialize test data setup.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self.test_db: Optional[CodeDatabase] = None

    def setup_test_database(self) -> CodeDatabase:
        """Setup test database with schema.

        Returns:
            CodeDatabase instance
        """
        # Ensure test database directory exists
        self.config.test_db_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing test database if exists
        if self.config.test_db_path.exists():
            self.config.test_db_path.unlink()

        # Create driver config
        driver_config = {
            "type": "sqlite",
            "config": {"path": str(self.config.test_db_path)},
        }

        # Set environment variable to allow direct SQLite driver
        original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
        os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

        try:
            # Create database
            db = CodeDatabase(driver_config)
            self.test_db = db
            return db
        except Exception:
            if original_env is None:
                os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
            else:
                os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env
            raise

    def load_test_projects(self, db: CodeDatabase) -> list[dict]:
        """Load test projects into database.

        Args:
            db: Database instance

        Returns:
            List of project info dictionaries
        """
        projects = []
        test_projects = self.config.get_test_projects()

        for project_path in test_projects:
            # Load projectid
            projectid_path = project_path / "projectid"
            if not projectid_path.exists():
                continue

            try:
                with open(projectid_path, "r", encoding="utf-8") as f:
                    projectid_data = (
                        json.load(f)
                        if projectid_path.suffix == ".json"
                        else f.read().strip()
                    )
                    if isinstance(projectid_data, dict):
                        project_id = projectid_data.get("id", "")
                    else:
                        project_id = projectid_data

                if not project_id:
                    continue

                # Create project in database
                project_info = {
                    "project_id": project_id,
                    "root_path": str(project_path.absolute()),
                    "name": project_path.name,
                }

                # Insert or update project
                try:
                    db.create_project(
                        project_id=project_id,
                        root_path=str(project_path.absolute()),
                        name=project_path.name,
                    )
                except Exception:
                    # Project might already exist, try update
                    try:
                        db.update_project(
                            project_id=project_id,
                            root_path=str(project_path.absolute()),
                            name=project_path.name,
                        )
                    except Exception:
                        pass

                projects.append(project_info)

            except Exception:
                continue

        return projects

    def load_test_files(
        self, db: CodeDatabase, project_id: str, project_path: Path
    ) -> int:
        """Load test files from project into database.

        Args:
            db: Database instance
            project_id: Project ID
            project_path: Path to project directory

        Returns:
            Number of files loaded
        """
        file_count = 0

        # Find all Python files
        for py_file in project_path.rglob("*.py"):
            # Skip __pycache__ and other ignored directories
            if "__pycache__" in py_file.parts or ".git" in py_file.parts:
                continue

            try:
                relative_path = py_file.relative_to(project_path)
                file_path = str(py_file.absolute())

                # Read file content
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Insert file into database
                try:
                    db.create_file(
                        project_id=project_id,
                        file_path=file_path,
                        relative_path=str(relative_path),
                        content=content,
                    )
                    file_count += 1
                except Exception:
                    # File might already exist, try update
                    try:
                        db.update_file(
                            project_id=project_id,
                            file_path=file_path,
                            relative_path=str(relative_path),
                            content=content,
                        )
                        file_count += 1
                    except Exception:
                        pass

            except Exception:
                continue

        return file_count

    def cleanup_test_database(self) -> None:
        """Cleanup test database."""
        if self.test_db:
            try:
                self.test_db.close()
            except Exception:
                pass
            self.test_db = None

        # Restore environment
        if "CODE_ANALYSIS_DB_WORKER" in os.environ:
            original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
            if original_env != "1":
                if original_env is None:
                    os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
                else:
                    os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env

        # Remove test database file
        if self.config.test_db_path.exists():
            try:
                self.config.test_db_path.unlink()
            except Exception:
                pass
