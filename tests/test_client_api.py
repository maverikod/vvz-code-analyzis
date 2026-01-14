"""
Tests for high-level API methods in DatabaseClient.

Tests Project, File, and Attribute operations using object models.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import threading
import time
from pathlib import Path
from datetime import datetime

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.database_client.objects.file import File
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestClientAPI:
    """Test high-level API methods for DatabaseClient."""

    @pytest.fixture
    def rpc_server_with_schema(self, tmp_path):
        """Create RPC server with full database schema."""
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

    # ============================================================================
    # Project Operations Tests
    # ============================================================================

    def test_create_project(self, rpc_server_with_schema):
        """Test create_project method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            project = Project(
                id="test-project-1",
                root_path="/tmp/test_project",
                name="Test Project",
                comment="Test description",
            )

            created = client.create_project(project)
            assert created.id == project.id
            assert created.root_path == project.root_path
            assert created.name == project.name
            assert created.comment == project.comment
            assert created.created_at is not None
            assert created.updated_at is not None
        finally:
            client.disconnect()

    def test_get_project(self, rpc_server_with_schema):
        """Test get_project method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project first
            project = Project(
                id="test-project-2",
                root_path="/tmp/test_project_2",
                name="Test Project 2",
            )
            client.create_project(project)

            # Get project
            retrieved = client.get_project("test-project-2")
            assert retrieved is not None
            assert retrieved.id == project.id
            assert retrieved.root_path == project.root_path

            # Get non-existent project
            not_found = client.get_project("non-existent")
            assert not_found is None
        finally:
            client.disconnect()

    def test_update_project(self, rpc_server_with_schema):
        """Test update_project method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project
            project = Project(
                id="test-project-3",
                root_path="/tmp/test_project_3",
                name="Original Name",
            )
            client.create_project(project)

            # Update project
            project.name = "Updated Name"
            project.comment = "Updated comment"
            updated = client.update_project(project)

            assert updated.name == "Updated Name"
            assert updated.comment == "Updated comment"

            # Try to update non-existent project
            non_existent = Project(
                id="non-existent",
                root_path="/tmp/non_existent",
            )
            with pytest.raises(ValueError, match="not found"):
                client.update_project(non_existent)
        finally:
            client.disconnect()

    def test_delete_project(self, rpc_server_with_schema):
        """Test delete_project method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project
            project = Project(
                id="test-project-4",
                root_path="/tmp/test_project_4",
            )
            client.create_project(project)

            # Delete project
            result = client.delete_project("test-project-4")
            assert result is True

            # Verify deleted
            retrieved = client.get_project("test-project-4")
            assert retrieved is None

            # Delete non-existent project
            result = client.delete_project("non-existent")
            assert result is False
        finally:
            client.disconnect()

    def test_list_projects(self, rpc_server_with_schema):
        """Test list_projects method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create multiple projects
            for i in range(3):
                project = Project(
                    id=f"test-project-list-{i}",
                    root_path=f"/tmp/test_project_list_{i}",
                    name=f"Project {i}",
                )
                client.create_project(project)

            # List projects
            projects = client.list_projects()
            assert len(projects) >= 3

            # Verify all created projects are in list
            project_ids = {p.id for p in projects}
            assert "test-project-list-0" in project_ids
            assert "test-project-list-1" in project_ids
            assert "test-project-list-2" in project_ids
        finally:
            client.disconnect()

    # ============================================================================
    # File Operations Tests
    # ============================================================================

    def test_create_file(self, rpc_server_with_schema):
        """Test create_file method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project and dataset first
            project = Project(
                id="test-project-file",
                root_path="/tmp/test_project_file",
            )
            client.create_project(project)

            # Create file
            file = File(
                project_id=project.id,
                dataset_id="test-dataset-1",
                path="/tmp/test_project_file/test.py",
                relative_path="test.py",
                lines=100,
            )

            created = client.create_file(file)
            assert created.id is not None
            assert created.project_id == file.project_id
            assert created.dataset_id == file.dataset_id
            assert created.path == file.path
            assert created.lines == file.lines
            assert created.created_at is not None
        finally:
            client.disconnect()

    def test_get_file(self, rpc_server_with_schema):
        """Test get_file method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project and file
            project = Project(
                id="test-project-file-2",
                root_path="/tmp/test_project_file_2",
            )
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset-2",
                path="/tmp/test_project_file_2/test2.py",
            )
            created = client.create_file(file)

            # Get file
            retrieved = client.get_file(created.id)
            assert retrieved is not None
            assert retrieved.id == created.id
            assert retrieved.path == file.path

            # Get non-existent file
            not_found = client.get_file(99999)
            assert not_found is None
        finally:
            client.disconnect()

    def test_update_file(self, rpc_server_with_schema):
        """Test update_file method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project and file
            project = Project(
                id="test-project-file-3",
                root_path="/tmp/test_project_file_3",
            )
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset-3",
                path="/tmp/test_project_file_3/test3.py",
                lines=50,
            )
            created = client.create_file(file)

            # Update file
            created.lines = 150
            updated = client.update_file(created)

            assert updated.lines == 150

            # Try to update file without id
            file_no_id = File(
                project_id=project.id,
                dataset_id="test-dataset-3",
                path="/tmp/test_project_file_3/test4.py",
            )
            with pytest.raises(ValueError, match="id is required"):
                client.update_file(file_no_id)
        finally:
            client.disconnect()

    def test_delete_file(self, rpc_server_with_schema):
        """Test delete_file method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project and file
            project = Project(
                id="test-project-file-4",
                root_path="/tmp/test_project_file_4",
            )
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset-4",
                path="/tmp/test_project_file_4/test4.py",
            )
            created = client.create_file(file)

            # Delete file
            result = client.delete_file(created.id)
            assert result is True

            # Verify deleted
            retrieved = client.get_file(created.id)
            assert retrieved is None

            # Delete non-existent file
            result = client.delete_file(99999)
            assert result is False
        finally:
            client.disconnect()

    def test_get_project_files(self, rpc_server_with_schema):
        """Test get_project_files method."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project
            project = Project(
                id="test-project-files",
                root_path="/tmp/test_project_files",
            )
            client.create_project(project)

            # Create multiple files
            for i in range(3):
                file = File(
                    project_id=project.id,
                    dataset_id="test-dataset-files",
                    path=f"/tmp/test_project_files/file{i}.py",
                )
                client.create_file(file)

            # Get project files
            files = client.get_project_files(project.id)
            assert len(files) == 3

            # Get project files excluding deleted
            files = client.get_project_files(project.id, include_deleted=False)
            assert len(files) == 3
        finally:
            client.disconnect()

    # ============================================================================
    # Attribute Operations Tests
    # ============================================================================

    def test_save_and_get_ast(self, rpc_server_with_schema):
        """Test save_ast and get_ast methods."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project and file
            project = Project(
                id="test-project-ast",
                root_path="/tmp/test_project_ast",
            )
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset-ast",
                path="/tmp/test_project_ast/test_ast.py",
                last_modified=datetime.now(),
            )
            created = client.create_file(file)

            # Save AST
            ast_data = {"type": "Module", "body": []}
            result = client.save_ast(created.id, ast_data)
            assert result is True

            # Get AST
            retrieved = client.get_ast(created.id)
            assert retrieved is not None
            assert retrieved["type"] == "Module"

            # Get AST for non-existent file
            with pytest.raises(ValueError, match="not found"):
                client.save_ast(99999, ast_data)
        finally:
            client.disconnect()

    def test_save_and_get_cst(self, rpc_server_with_schema):
        """Test save_cst and get_cst methods."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project and file
            project = Project(
                id="test-project-cst",
                root_path="/tmp/test_project_cst",
            )
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset-cst",
                path="/tmp/test_project_cst/test_cst.py",
                last_modified=datetime.now(),
            )
            created = client.create_file(file)

            # Save CST
            cst_code = "def hello():\n    print('Hello, World!')"
            result = client.save_cst(created.id, cst_code)
            assert result is True

            # Get CST
            retrieved = client.get_cst(created.id)
            assert retrieved == cst_code

            # Get CST for non-existent file
            with pytest.raises(ValueError, match="not found"):
                client.save_cst(99999, cst_code)
        finally:
            client.disconnect()

    def test_save_and_get_vectors(self, rpc_server_with_schema):
        """Test save_vectors and get_vectors methods."""
        _, socket_path, _ = rpc_server_with_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project and file
            project = Project(
                id="test-project-vectors",
                root_path="/tmp/test_project_vectors",
            )
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset-vectors",
                path="/tmp/test_project_vectors/test_vectors.py",
            )
            created = client.create_file(file)

            # Save vectors
            vectors = [
                {
                    "entity_type": "file",
                    "entity_id": created.id,
                    "vector_id": 1,
                    "vector_dim": 768,
                    "embedding_model": "test-model",
                }
            ]
            result = client.save_vectors(created.id, vectors)
            assert result is True

            # Get vectors
            retrieved = client.get_vectors(created.id)
            assert len(retrieved) == 1
            assert retrieved[0]["entity_type"] == "file"
            assert retrieved[0]["vector_id"] == 1

            # Save vectors for non-existent file
            with pytest.raises(ValueError, match="not found"):
                client.save_vectors(99999, vectors)
        finally:
            client.disconnect()
