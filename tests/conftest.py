"""
Pytest fixtures for MCP commands testing.

Provides common fixtures for testing MCP commands with DatabaseClient.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import os
import threading
import time
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.database_client.objects.file import File
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


@pytest.fixture
def rpc_server_with_schema(tmp_path):
    """Create RPC server with full database schema for command testing."""
    db_path = tmp_path / "test.db"
    socket_path = str(tmp_path / "test.sock")

    # Create driver and full schema
    driver = create_driver("sqlite", {"path": str(db_path)})

    # Create projects table
    driver._execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            root_path TEXT UNIQUE NOT NULL,
            name TEXT,
            comment TEXT,
            watch_dir_id TEXT,
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now'))
        )
        """
    )

    # Create datasets table
    driver._execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            root_path TEXT NOT NULL,
            name TEXT,
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )

    # Create files table
    driver._execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            watch_dir_id TEXT,
            path TEXT NOT NULL,
            relative_path TEXT,
            lines INTEGER,
            last_modified REAL,
            has_docstring INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0,
            original_path TEXT,
            version_dir TEXT,
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
            UNIQUE(project_id, dataset_id, path)
        )
        """
    )

    # Create ast_trees table
    driver._execute(
        """
        CREATE TABLE IF NOT EXISTS ast_trees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            project_id TEXT NOT NULL,
            ast_json TEXT NOT NULL,
            ast_hash TEXT NOT NULL,
            file_mtime REAL NOT NULL DEFAULT 0,
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(file_id, ast_hash)
        )
        """
    )

    # Create cst_trees table
    driver._execute(
        """
        CREATE TABLE IF NOT EXISTS cst_trees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            project_id TEXT NOT NULL,
            cst_code TEXT NOT NULL,
            cst_hash TEXT NOT NULL,
            file_mtime REAL NOT NULL DEFAULT 0,
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(file_id, cst_hash)
        )
        """
    )

    # Create vector_index table
    driver._execute(
        """
        CREATE TABLE IF NOT EXISTS vector_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            vector_id INTEGER NOT NULL,
            vector_dim INTEGER NOT NULL,
            embedding_model TEXT,
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, entity_type, entity_id)
        )
        """
    )

    driver._commit()

    # Start RPC server
    request_queue = RequestQueue()
    server = RPCServer(driver, request_queue, socket_path)

    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    time.sleep(0.3)  # Wait for server to start

    yield server, socket_path, db_path

    # Cleanup
    server.stop()
    driver.disconnect()


@pytest.fixture
def database_client(rpc_server_with_schema):
    """Create DatabaseClient instance for testing."""
    _, socket_path, _ = rpc_server_with_schema

    client = DatabaseClient(socket_path=socket_path)
    client.connect()

    yield client

    client.disconnect()


@pytest.fixture
def test_project(database_client, tmp_path):
    """Create test project in database and filesystem."""
    project_id = str(uuid.uuid4())
    root_path = str(tmp_path)

    # Create project in database
    project = Project(
        id=project_id,
        root_path=root_path,
        name=tmp_path.name,
    )
    database_client.create_project(project)

    # Create projectid file
    projectid_file = tmp_path / "projectid"
    projectid_data = {
        "id": project_id,
        "description": "Test project"
    }
    projectid_file.write_text(json.dumps(projectid_data, indent=4), encoding="utf-8")

    return project_id, tmp_path


@pytest.fixture
def test_file(database_client, test_project, tmp_path):
    """Create test file in database and filesystem."""
    project_id, root_path = test_project

    # Create dataset
    dataset_id = str(uuid.uuid4())
    database_client.execute(
        """
        INSERT INTO datasets (id, project_id, root_path, name, updated_at)
        VALUES (?, ?, ?, ?, julianday('now'))
        """,
        (dataset_id, project_id, str(root_path), root_path.name),
    )

    # Create test file
    file_path = tmp_path / "test_file.py"
    file_content = '''"""
Test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


class TestClass:
    """Test class."""
    
    def test_method(self):
        """Test method."""
        pass


def test_function():
    """Test function."""
    pass
'''
    file_path.write_text(file_content, encoding="utf-8")

    file_mtime = os.path.getmtime(file_path)
    lines = len(file_content.splitlines())

    # Create file in database
    file_obj = File(
        project_id=project_id,
        dataset_id=dataset_id,
        path=str(file_path),
        relative_path="test_file.py",
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
    )
    created_file = database_client.create_file(file_obj)

    return created_file.id, file_path, project_id, root_path
