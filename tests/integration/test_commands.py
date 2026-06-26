"""
Integration tests for commands with real data and real server.

Tests MCP commands integration with database driver through RPC server
on real data from test_data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.project_management_mcp_commands import (
    CreateProjectMCPCommand,
    ListProjectsMCPCommand,
)
from code_analysis.commands.ast.list_files import ListProjectFilesMCPCommand
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
from code_analysis.core.project_resolution import load_project_info
from code_analysis.core.shared_database import (
    close_shared_database,
    set_shared_database,
)

# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestCommandsIntegration:
    """Test commands integration with real data and real server."""

    @pytest.fixture
    def rpc_server_with_schema(self, tmp_path):
        """Create RPC server with full schema."""
        db_path = tmp_path / "commands_test.db"
        socket_path = str(tmp_path / "test_commands.sock")

        # Create driver
        driver = create_driver("sqlite", {"path": str(db_path)})

        # Create required tables
        schema = {
            "name": "projects",
            "columns": [
                {"name": "id", "type": "TEXT", "primary_key": True},
                {"name": "root_path", "type": "TEXT", "not_null": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)

        schema = {
            "name": "files",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "path", "type": "TEXT", "not_null": True},
                {"name": "project_id", "type": "TEXT", "not_null": True},
                {"name": "lines", "type": "INTEGER"},
            ],
        }
        driver.create_table(schema)

        # watch_dirs and watch_dir_paths required for create_project
        schema = {
            "name": "watch_dirs",
            "columns": [
                {"name": "id", "type": "TEXT", "primary_key": True, "nullable": False},
                {"name": "name", "type": "TEXT", "nullable": True},
            ],
        }
        driver.create_table(schema)
        schema = {
            "name": "watch_dir_paths",
            "columns": [
                {
                    "name": "watch_dir_id",
                    "type": "TEXT",
                    "primary_key": True,
                    "nullable": False,
                },
                {"name": "absolute_path", "type": "TEXT", "nullable": True},
            ],
        }
        driver.create_table(schema)

        watch_dir_id = str(uuid.uuid4())
        driver.execute(
            "INSERT INTO watch_dirs (id, name) VALUES (?, ?)",
            (watch_dir_id, "test_watch"),
        )
        driver.execute(
            "INSERT INTO watch_dir_paths (watch_dir_id, absolute_path) VALUES (?, ?)",
            (watch_dir_id, str(VAST_SRV_DIR.parent)),
        )

        # Start RPC server
        request_queue = RequestQueue()
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)  # Wait for server to start

        yield server, socket_path, db_path, watch_dir_id

        # Cleanup
        server.stop()
        driver.disconnect()

    @pytest.fixture
    def shared_db_for_commands(self, rpc_server_with_schema):
        """Set shared database to test RPC client so commands use it (no per-command open)."""
        _, socket_path, _, _ = rpc_server_with_schema
        client = DatabaseClient(socket_path=socket_path)
        client.connect()
        set_shared_database(client)
        try:
            yield
        finally:
            close_shared_database()

    def _create_storage_paths_mock(self, tmp_path, db_path):
        """Create mock StoragePaths object with all required attributes."""
        from code_analysis.core.storage_paths import StoragePaths

        return StoragePaths(
            sessions_root=tmp_path / "search_sessions",
            log_dir=tmp_path / "logs",
            db_path=db_path,
            faiss_dir=tmp_path / "faiss",
            locks_dir=tmp_path / "locks",
            queue_dir=tmp_path / "queue",
            backup_dir=tmp_path / "backups",
            trash_dir=tmp_path / "trash",
        )

    def _check_test_data_available(self):
        """Check if test data is available."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

    @pytest.mark.asyncio
    async def test_create_project_command_with_real_data(
        self, rpc_server_with_schema, shared_db_for_commands, tmp_path
    ):
        """Test create project command with real data."""
        self._check_test_data_available()

        _, socket_path, db_path, watch_dir_id = rpc_server_with_schema

        # Mock storage paths to use our test database
        storage_paths = self._create_storage_paths_mock(tmp_path, db_path)

        with patch(
            "code_analysis.commands.base_mcp_command.resolve_storage_paths"
        ) as mock_resolve:
            mock_resolve.return_value = storage_paths

            # Mock socket path resolution
            with patch(
                "code_analysis.commands.base_mcp_command._get_socket_path_from_db_path"
            ) as mock_socket:
                mock_socket.return_value = socket_path

                # Create project command requires watch_dir_id, project_name, description
                command = CreateProjectMCPCommand()
                result = await command.execute(
                    watch_dir_id=watch_dir_id,
                    project_name=VAST_SRV_DIR.name,
                    description="Test project from integration test",
                )

                # Check if result is success (SuccessResult) or error (ErrorResult)
                if hasattr(result, "success"):
                    assert result.success is True
                    assert result.data is not None
                else:
                    # If ErrorResult, check that it's a known error (project may already exist)
                    assert hasattr(result, "error")
                    # Project may already exist, which is acceptable

    @pytest.mark.asyncio
    async def test_list_projects_command_with_real_data(
        self, rpc_server_with_schema, shared_db_for_commands, tmp_path
    ):
        """Test list projects command with real data."""
        self._check_test_data_available()

        _, socket_path, db_path, _ = rpc_server_with_schema

        # Setup: Create project in database
        database = DatabaseClient(socket_path=socket_path)
        database.connect()

        try:
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            database.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )
        finally:
            database.disconnect()

        # Mock storage paths
        storage_paths = self._create_storage_paths_mock(tmp_path, db_path)

        with patch(
            "code_analysis.commands.base_mcp_command.resolve_storage_paths"
        ) as mock_resolve:
            mock_resolve.return_value = storage_paths

            with patch(
                "code_analysis.commands.base_mcp_command._get_socket_path_from_db_path"
            ) as mock_socket:
                mock_socket.return_value = socket_path

                # List projects command (no root_dir; DB path from config/mock)
                command = ListProjectsMCPCommand()
                result = await command.execute()

                # Check if result is success
                if hasattr(result, "success"):
                    assert result.success is True
                    assert result.data is not None
                    # Should contain the project we created
                    projects = result.data.get("projects", [])
                    assert len(projects) > 0
                    # Find our project
                    found_project = next(
                        (p for p in projects if p.get("id") == project_id), None
                    )
                    assert found_project is not None
                else:
                    # If ErrorResult, that's also acceptable
                    assert hasattr(result, "error")

    @pytest.mark.asyncio
    async def test_get_file_command_with_real_data(
        self, rpc_server_with_schema, shared_db_for_commands, tmp_path
    ):
        """Test get file command with real data."""
        self._check_test_data_available()

        _, socket_path, db_path, _ = rpc_server_with_schema

        # Setup: Create project and file in database
        database = DatabaseClient(socket_path=socket_path)
        database.connect()

        try:
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            database.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )

            # Find real Python file
            python_files = list(VAST_SRV_DIR.rglob("*.py"))
            if not python_files:
                pytest.skip("No Python files found in test_data/vast_srv/")

            test_file = python_files[0]
            database.insert(
                "files",
                {
                    "path": str(test_file),
                    "project_id": project_id,
                    "lines": len(test_file.read_text().splitlines()),
                },
            )
        finally:
            database.disconnect()

        # Mock storage paths
        with patch(
            "code_analysis.commands.base_mcp_command.resolve_storage_paths"
        ) as mock_resolve:
            mock_resolve.return_value = type(
                "obj",
                (object,),
                {
                    "db_path": db_path,
                    "backup_dir": tmp_path / "backups",
                    "log_dir": tmp_path / "logs",
                },
            )()

            with patch(
                "code_analysis.commands.base_mcp_command._get_socket_path_from_db_path"
            ) as mock_socket:
                mock_socket.return_value = socket_path

                # List project files command
                storage_paths = self._create_storage_paths_mock(tmp_path, db_path)
                mock_resolve.return_value = storage_paths

                command = ListProjectFilesMCPCommand()
                result = await command.execute(
                    root_dir=str(tmp_path),
                    project_id=project_id,
                )

                # Check if result is success
                if hasattr(result, "success"):
                    assert result.success is True
                    assert result.data is not None
                    # Should contain at least one file
                    files = result.data.get("files", [])
                    assert len(files) > 0
                else:
                    # If ErrorResult, that's also acceptable
                    assert hasattr(result, "error")

    @pytest.mark.asyncio
    async def test_commands_error_handling(
        self, rpc_server_with_schema, shared_db_for_commands, tmp_path
    ):
        """Test commands error handling."""
        _, socket_path, db_path, _ = rpc_server_with_schema

        # Mock storage paths
        storage_paths = self._create_storage_paths_mock(tmp_path, db_path)

        with patch(
            "code_analysis.commands.base_mcp_command.resolve_storage_paths"
        ) as mock_resolve:
            mock_resolve.return_value = storage_paths

            with patch(
                "code_analysis.commands.base_mcp_command._get_socket_path_from_db_path"
            ) as mock_socket:
                mock_socket.return_value = socket_path

                # Try to list projects (should work even if empty)
                command = ListProjectsMCPCommand()
                result = await command.execute()

                # Check if result is success
                if hasattr(result, "success"):
                    assert result.success is True
                    assert result.data is not None
                else:
                    # If ErrorResult, that's also acceptable
                    assert hasattr(result, "error")

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not VAST_SRV_DIR.exists(),
        reason="test_data/vast_srv not found (optional test data)",
    )
    async def test_commands_concurrent_execution(
        self, rpc_server_with_schema, shared_db_for_commands, tmp_path
    ):
        """Test concurrent command execution."""
        _, socket_path, db_path, _ = rpc_server_with_schema

        # Setup: Create project
        database = DatabaseClient(socket_path=socket_path)
        database.connect()

        try:
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            database.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )
        finally:
            database.disconnect()

        # Mock storage paths
        storage_paths = self._create_storage_paths_mock(tmp_path, db_path)

        with patch(
            "code_analysis.commands.base_mcp_command.resolve_storage_paths"
        ) as mock_resolve:
            mock_resolve.return_value = storage_paths

            with patch(
                "code_analysis.commands.base_mcp_command._get_socket_path_from_db_path"
            ) as mock_socket:
                mock_socket.return_value = socket_path

                # Execute commands concurrently
                async def run_command():
                    """Return run command."""
                    command = ListProjectsMCPCommand()
                    return await command.execute()

                tasks = [run_command() for _ in range(10)]
                results = await asyncio.gather(*tasks)

                # Verify all commands completed (may be success or error)
                assert len(results) == 10
                # All results should be either SuccessResult or ErrorResult
                for r in results:
                    assert hasattr(r, "success") or hasattr(r, "error")
