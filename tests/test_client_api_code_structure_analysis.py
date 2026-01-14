"""
Tests for Code Structure and Analysis API methods in DatabaseClient.

Tests Class, Function, Method, Import, Issue, Usage, and CodeDuplicate operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import threading
import time

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.database_client.objects.file import File
from code_analysis.core.database_client.objects.class_function import Class, Function
from code_analysis.core.database_client.objects.method_import import Method, Import
from code_analysis.core.database_client.objects.analysis import Issue, Usage, CodeDuplicate
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestClientAPICodeStructureAnalysis:
    """Test Code Structure and Analysis API methods for DatabaseClient."""

    @pytest.fixture
    def rpc_server_with_full_schema(self, tmp_path):
        """Create RPC server with full database schema including code structure and analysis tables."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        driver = create_driver("sqlite", {"path": str(db_path)})

        # Create all necessary tables (reuse from test_client_api.py fixture logic)
        # Projects, datasets, files, ast_trees, cst_trees, vector_index
        # Plus: classes, functions, methods, imports, issues, usages, code_duplicates

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

        # Create files table
        driver._execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                path TEXT NOT NULL,
                relative_path TEXT,
                lines INTEGER,
                last_modified REAL,
                has_docstring INTEGER DEFAULT 0,
                deleted INTEGER DEFAULT 0,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                UNIQUE(project_id, dataset_id, path)
            )
            """
        )

        # Create classes table
        driver._execute(
            """
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                line INTEGER NOT NULL,
                docstring TEXT,
                bases TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                UNIQUE(file_id, name, line)
            )
            """
        )

        # Create functions table
        driver._execute(
            """
            CREATE TABLE IF NOT EXISTS functions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                line INTEGER NOT NULL,
                args TEXT,
                docstring TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                UNIQUE(file_id, name, line)
            )
            """
        )

        # Create methods table
        driver._execute(
            """
            CREATE TABLE IF NOT EXISTS methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                line INTEGER NOT NULL,
                args TEXT,
                docstring TEXT,
                is_abstract INTEGER DEFAULT 0,
                has_pass INTEGER DEFAULT 0,
                has_not_implemented INTEGER DEFAULT 0,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                UNIQUE(class_id, name, line)
            )
            """
        )

        # Create imports table
        driver._execute(
            """
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                module TEXT,
                import_type TEXT NOT NULL,
                line INTEGER NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
            """
        )

        # Create issues table
        driver._execute(
            """
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                project_id TEXT,
                class_id INTEGER,
                function_id INTEGER,
                method_id INTEGER,
                issue_type TEXT NOT NULL,
                line INTEGER,
                description TEXT,
                metadata TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )

        # Create usages table
        driver._execute(
            """
            CREATE TABLE IF NOT EXISTS usages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                line INTEGER NOT NULL,
                usage_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_class TEXT,
                target_name TEXT NOT NULL,
                context TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
            """
        )

        # Create code_duplicates table
        driver._execute(
            """
            CREATE TABLE IF NOT EXISTS code_duplicates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                duplicate_hash TEXT NOT NULL,
                similarity REAL NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, duplicate_hash)
            )
            """
        )

        driver._commit()

        request_queue = RequestQueue()
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        yield server, socket_path, db_path

        server.stop()
        driver.disconnect()

    # ============================================================================
    # Code Structure Tests
    # ============================================================================

    def test_create_and_get_class(self, rpc_server_with_full_schema):
        """Test create_class and get_class methods."""
        _, socket_path, _ = rpc_server_with_full_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create project and file
            project = Project(id="test-project-cs", root_path="/tmp/test_cs")
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset",
                path="/tmp/test_cs/test.py",
            )
            created_file = client.create_file(file)

            # Create class
            class_obj = Class(
                file_id=created_file.id,
                name="TestClass",
                line=10,
                docstring="Test class docstring",
            )
            created = client.create_class(class_obj)
            assert created.id is not None
            assert created.name == "TestClass"

            # Get class
            retrieved = client.get_class(created.id)
            assert retrieved is not None
            assert retrieved.name == "TestClass"
        finally:
            client.disconnect()

    def test_create_and_get_function(self, rpc_server_with_full_schema):
        """Test create_function and get_function methods."""
        _, socket_path, _ = rpc_server_with_full_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            project = Project(id="test-project-fn", root_path="/tmp/test_fn")
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset",
                path="/tmp/test_fn/test.py",
            )
            created_file = client.create_file(file)

            # Create function
            function = Function(
                file_id=created_file.id,
                name="test_function",
                line=20,
            )
            created = client.create_function(function)
            assert created.id is not None

            # Get function
            retrieved = client.get_function(created.id)
            assert retrieved is not None
            assert retrieved.name == "test_function"
        finally:
            client.disconnect()

    def test_create_and_get_method(self, rpc_server_with_full_schema):
        """Test create_method and get_method methods."""
        _, socket_path, _ = rpc_server_with_full_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            project = Project(id="test-project-meth", root_path="/tmp/test_meth")
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset",
                path="/tmp/test_meth/test.py",
            )
            created_file = client.create_file(file)

            # Create class first
            class_obj = Class(file_id=created_file.id, name="TestClass", line=10)
            created_class = client.create_class(class_obj)

            # Create method
            method = Method(
                class_id=created_class.id,
                name="test_method",
                line=15,
            )
            created = client.create_method(method)
            assert created.id is not None

            # Get method
            retrieved = client.get_method(created.id)
            assert retrieved is not None
            assert retrieved.name == "test_method"
        finally:
            client.disconnect()

    def test_get_file_structure(self, rpc_server_with_full_schema):
        """Test get_file_structure method."""
        _, socket_path, _ = rpc_server_with_full_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            project = Project(id="test-project-struct", root_path="/tmp/test_struct")
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset",
                path="/tmp/test_struct/test.py",
            )
            created_file = client.create_file(file)

            # Create structure
            class_obj = Class(file_id=created_file.id, name="TestClass", line=10)
            client.create_class(class_obj)

            function = Function(file_id=created_file.id, name="test_func", line=20)
            client.create_function(function)

            # Get structure
            structure = client.get_file_structure(created_file.id)
            assert "classes" in structure
            assert "functions" in structure
            assert "methods" in structure
            assert "imports" in structure
            assert len(structure["classes"]) == 1
            assert len(structure["functions"]) == 1
        finally:
            client.disconnect()

    # ============================================================================
    # Analysis Tests
    # ============================================================================

    def test_create_and_get_issue(self, rpc_server_with_full_schema):
        """Test create_issue and get_issue methods."""
        _, socket_path, _ = rpc_server_with_full_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            project = Project(id="test-project-issue", root_path="/tmp/test_issue")
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset",
                path="/tmp/test_issue/test.py",
            )
            created_file = client.create_file(file)

            # Create issue
            issue = Issue(
                file_id=created_file.id,
                project_id=project.id,
                issue_type="missing_docstring",
                line=10,
                description="Missing docstring",
            )
            created = client.create_issue(issue)
            assert created.id is not None

            # Get issue
            retrieved = client.get_issue(created.id)
            assert retrieved is not None
            assert retrieved.issue_type == "missing_docstring"
        finally:
            client.disconnect()

    def test_create_and_get_usage(self, rpc_server_with_full_schema):
        """Test create_usage and get_usage methods."""
        _, socket_path, _ = rpc_server_with_full_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            project = Project(id="test-project-usage", root_path="/tmp/test_usage")
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset",
                path="/tmp/test_usage/test.py",
            )
            created_file = client.create_file(file)

            # Create usage
            usage = Usage(
                file_id=created_file.id,
                line=25,
                usage_type="call",
                target_type="function",
                target_name="test_function",
            )
            created = client.create_usage(usage)
            assert created.id is not None

            # Get usage
            retrieved = client.get_usage(created.id)
            assert retrieved is not None
            assert retrieved.target_name == "test_function"
        finally:
            client.disconnect()

    def test_get_project_statistics(self, rpc_server_with_full_schema):
        """Test get_project_statistics method."""
        _, socket_path, _ = rpc_server_with_full_schema

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            project = Project(id="test-project-stats", root_path="/tmp/test_stats")
            client.create_project(project)

            file = File(
                project_id=project.id,
                dataset_id="test-dataset",
                path="/tmp/test_stats/test.py",
            )
            created_file = client.create_file(file)

            # Create some structure
            class_obj = Class(file_id=created_file.id, name="TestClass", line=10)
            created_class = client.create_class(class_obj)
            Method(class_id=created_class.id, name="test_method", line=15)
            client.create_method(Method(class_id=created_class.id, name="test_method", line=15))

            # Get statistics
            stats = client.get_project_statistics(project.id)
            assert "files" in stats
            assert "classes" in stats
            assert "functions" in stats
            assert "methods" in stats
            assert stats["files"] >= 1
            assert stats["classes"] >= 1
        finally:
            client.disconnect()
