"""
Integration tests for commands with real data and real server.

Tests MCP commands integration with database driver through RPC server
on real data from test_data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import threading
import time
import asyncio
from pathlib import Path
from unittest.mock import patch

from code_analysis.commands.project_management_mcp_commands import (
    CreateProjectMCPCommand,
    ListProjectsMCPCommand,
)
from code_analysis.commands.file_management_mcp_commands import (
    ListFilesMCPCommand,
)
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
from code_analysis.core.project_resolution import load_project_info

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

        # Start RPC server
        request_queue = RequestQueue()
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)  # Wait for server to start

        yield server, socket_path, db_path

        # Cleanup
        server.stop()
        driver.disconnect()

    def _check_test_data_available(self):
        """Check if test data is available."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

    @pytest.mark.asyncio
    async def test_create_project_command_with_real_data(
        self, rpc_server_with_schema, tmp_path
    ):
        """Test create project command with real data."""
        self._check_test_data_available()

        _, socket_path, db_path = rpc_server_with_schema

        # Mock storage paths to use our test database
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

            # Mock socket path resolution
            with patch(
                "code_analysis.commands.base_mcp_command._get_socket_path_from_db_path"
            ) as mock_socket:
                mock_socket.return_value = socket_path

                # Create project command
                command = CreateProjectMCPCommand()
                result = await command.execute(
                    root_dir=str(VAST_SRV_DIR),
                    project_id=None,
                )

                assert result.success is True
                assert result.data is not None

    @pytest.mark.asyncio
    async def test_get_project_command_with_real_data(
        self, rpc_server_with_schema, tmp_path
    ):
        """Test get project command with real data."""
        self._check_test_data_available()

        _, socket_path, db_path = rpc_server_with_schema

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

                # Get project command
                command = GetProjectMCPCommand()
                result = await command.execute(
                    root_dir=str(VAST_SRV_DIR),
                    project_id=project_id,
                )

                assert result.success is True
                assert result.data is not None
                assert result.data.get("id") == project_id

    @pytest.mark.asyncio
    async def test_get_file_command_with_real_data(
        self, rpc_server_with_schema, tmp_path
    ):
        """Test get file command with real data."""
        self._check_test_data_available()

        _, socket_path, db_path = rpc_server_with_schema

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

                # List files command
                command = ListFilesMCPCommand()
                result = await command.execute(
                    root_dir=str(VAST_SRV_DIR),
                    project_id=project_id,
                )

                assert result.success is True
                assert result.data is not None
                # Should contain at least one file
                files = result.data.get("files", [])
                assert len(files) > 0

    @pytest.mark.asyncio
    async def test_commands_error_handling(self, rpc_server_with_schema, tmp_path):
        """Test commands error handling."""
        _, socket_path, db_path = rpc_server_with_schema

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

                # Try to list projects (should work even if empty)
                command = ListProjectsMCPCommand()
                result = await command.execute(root_dir=str(tmp_path))

                # Should succeed but may return empty list
                assert result.success is True
                assert result.data is not None

    @pytest.mark.asyncio
    async def test_commands_concurrent_execution(
        self, rpc_server_with_schema, tmp_path
    ):
        """Test concurrent command execution."""
        _, socket_path, db_path = rpc_server_with_schema

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

                # Execute commands concurrently
                async def run_command():
                    command = ListProjectsMCPCommand()
                    return await command.execute(root_dir=str(VAST_SRV_DIR))

                tasks = [run_command() for _ in range(10)]
                results = await asyncio.gather(*tasks)

                # Verify all commands succeeded
                assert len(results) == 10
                assert all(r.success is True for r in results)
