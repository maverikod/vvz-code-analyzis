"""
Integration tests for AST/CST tree operations on real data from test_data.

Tests AST/CST query and modify operations through real RPC server
on actual Python files from test_data projects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import threading
import time
import hashlib
import json
import ast
from pathlib import Path

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.objects import (
    ASTNode,
    CSTNode,
    TreeAction,
    XPathFilter,
)
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
from code_analysis.core.database import CodeDatabase
from code_analysis.core.project_resolution import load_project_info

# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestASTCSTOperationsRealData:
    """Test AST/CST operations on real data from test_data/."""

    @pytest.fixture
    def rpc_server_with_real_data(self, tmp_path):
        """Create RPC server with real data setup."""
        db_path = tmp_path / "ast_cst_test.db"
        socket_path = str(tmp_path / "test_ast_cst.sock")

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

        schema = {
            "name": "ast_trees",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "file_id", "type": "INTEGER", "not_null": True},
                {"name": "project_id", "type": "TEXT", "not_null": True},
                {"name": "ast_json", "type": "TEXT", "not_null": True},
                {"name": "ast_hash", "type": "TEXT", "not_null": True},
                {"name": "file_mtime", "type": "REAL"},
                {"name": "created_at", "type": "REAL"},
                {"name": "updated_at", "type": "REAL"},
            ],
        }
        driver.create_table(schema)

        schema = {
            "name": "cst_trees",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "file_id", "type": "INTEGER", "not_null": True},
                {"name": "project_id", "type": "TEXT", "not_null": True},
                {"name": "cst_code", "type": "TEXT", "not_null": True},
                {"name": "cst_hash", "type": "TEXT", "not_null": True},
                {"name": "file_mtime", "type": "REAL"},
                {"name": "created_at", "type": "REAL"},
                {"name": "updated_at", "type": "REAL"},
            ],
        }
        driver.create_table(schema)

        # Start RPC server
        request_queue = RequestQueue()
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.5)  # Wait for server to start

        yield server, socket_path, db_path, driver

        # Cleanup
        server.stop()
        driver.disconnect()

    def _check_test_data_available(self):
        """Check if test data is available."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

    def _setup_real_file(
        self, client: DatabaseClient, file_path: Path, project_id: str
    ) -> int:
        """Setup real file in database and return file_id."""
        # Insert file
        file_id = client.insert(
            "files",
            {
                "path": str(file_path),
                "project_id": project_id,
                "lines": len(file_path.read_text().splitlines()),
            },
        )

        # Save AST tree
        source_code = file_path.read_text(encoding="utf-8")
        ast_tree = ast.parse(source_code, filename=str(file_path))
        ast_json = json.dumps(ast.dump(ast_tree))
        ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

        client.insert(
            "ast_trees",
            {
                "file_id": file_id,
                "project_id": project_id,
                "ast_json": ast_json,
                "ast_hash": ast_hash,
                "file_mtime": time.time(),
            },
        )

        # Save CST tree
        cst_hash = hashlib.sha256(source_code.encode()).hexdigest()
        client.insert(
            "cst_trees",
            {
                "file_id": file_id,
                "project_id": project_id,
                "cst_code": source_code,
                "cst_hash": cst_hash,
                "file_mtime": time.time(),
            },
        )

        return file_id

    def test_query_cst_functions_real_file(self, rpc_server_with_real_data):
        """Test querying CST functions in real file."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        # Find real Python files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Setup project and file
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass  # Project may already exist

            file_id = self._setup_real_file(client, test_file, project_id)

            # Query for functions
            filter_obj = XPathFilter(selector="function")
            result = client.query_cst(file_id, filter_obj)

            assert result.is_success(), f"Query failed: {result.error_description}"
            assert result.data is not None
            assert isinstance(result.data, list)
            # May have no top-level functions, so just check it's a list

        finally:
            client.disconnect()

    def test_query_cst_classes_real_file(self, rpc_server_with_real_data):
        """Test querying CST classes in real file."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file, project_id)

            # Query for classes
            filter_obj = XPathFilter(selector="class")
            result = client.query_cst(file_id, filter_obj)

            assert result.is_success(), f"Query failed: {result.error_description}"
            assert result.data is not None
            assert isinstance(result.data, list)

            # If classes found, verify structure
            if result.data:
                cst_node = CSTNode.from_dict(result.data[0])
                assert cst_node.file_id == file_id
                assert cst_node.project_id == project_id

        finally:
            client.disconnect()

    def test_query_cst_with_predicates_real_file(self, rpc_server_with_real_data):
        """Test querying CST with predicates on real file."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file, project_id)

            # Query for functions with name starting with specific prefix
            filter_obj = XPathFilter(selector='function[name^="test"]')
            result = client.query_cst(file_id, filter_obj)

            assert result.is_success(), f"Query failed: {result.error_description}"
            assert result.data is not None
            assert isinstance(result.data, list)

        finally:
            client.disconnect()

    def test_query_ast_real_file(self, rpc_server_with_real_data):
        """Test querying AST in real file."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file, project_id)

            # Query AST (basic implementation returns AST tree)
            filter_obj = XPathFilter(selector="function")
            result = client.query_ast(file_id, filter_obj)

            assert result.is_success(), f"Query failed: {result.error_description}"
            assert result.data is not None
            assert isinstance(result.data, list)

        finally:
            client.disconnect()

    def test_modify_cst_delete_real_file(self, rpc_server_with_real_data, tmp_path):
        """Test deleting CST nodes in real file."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        # Create a copy of test file for modification
        test_file = python_files[0]
        test_file_copy = tmp_path / "test_modify.py"
        test_file_copy.write_text(test_file.read_text())

        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file_copy, project_id)

            # First, query for functions to find something to delete
            filter_obj = XPathFilter(selector="function")
            query_result = client.query_cst(file_id, filter_obj)

            if not query_result.is_success() or not query_result.data:
                pytest.skip("No functions found to delete")

            # Get original source
            original_source = test_file_copy.read_text()

            # Delete first function
            delete_result = client.modify_cst(
                file_id, filter_obj, TreeAction.DELETE, []
            )

            assert (
                delete_result.is_success()
            ), f"Delete failed: {delete_result.error_description}"
            assert delete_result.data is not None

            # Verify file was modified (if we had functions)
            modified_cst = CSTNode.from_dict(delete_result.data)
            assert (
                modified_cst.cst_code != original_source or len(query_result.data) == 0
            )

        finally:
            client.disconnect()

    def test_modify_cst_replace_real_file(self, rpc_server_with_real_data, tmp_path):
        """Test replacing CST nodes in real file."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        # Create a copy of test file for modification
        test_file = python_files[0]
        test_file_copy = tmp_path / "test_replace.py"
        original_content = test_file.read_text()
        test_file_copy.write_text(original_content)

        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file_copy, project_id)

            # Query for first function
            filter_obj = XPathFilter(selector="function:first")
            query_result = client.query_cst(file_id, filter_obj)

            if not query_result.is_success() or not query_result.data:
                pytest.skip("No functions found to replace")

            # Create replacement node
            replacement_code = "def replaced_function():\n    pass\n"
            replacement_node = CSTNode(
                file_id=file_id,
                project_id=project_id,
                cst_code=replacement_code,
                cst_hash="",
            )

            # Replace function
            replace_result = client.modify_cst(
                file_id, filter_obj, TreeAction.REPLACE, [replacement_node]
            )

            assert (
                replace_result.is_success()
            ), f"Replace failed: {replace_result.error_description}"
            assert replace_result.data is not None

            modified_cst = CSTNode.from_dict(replace_result.data)
            assert replacement_code in modified_cst.cst_code

        finally:
            client.disconnect()

    def test_modify_ast_real_file(self, rpc_server_with_real_data, tmp_path):
        """Test modifying AST in real file (via CST translation)."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        # Create a copy of test file for modification
        test_file = python_files[0]
        test_file_copy = tmp_path / "test_ast_modify.py"
        original_content = test_file.read_text()
        test_file_copy.write_text(original_content)

        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file_copy, project_id)

            # Query CST to get node with code
            filter_obj = XPathFilter(selector="function:first")
            query_result = client.query_cst(file_id, filter_obj)

            if not query_result.is_success() or not query_result.data:
                pytest.skip("No functions found to modify")

            # Get original AST
            ast_rows = client.select("ast_trees", where={"file_id": file_id}, limit=1)
            original_ast_json = ast_rows[0]["ast_json"] if ast_rows else None

            # Create replacement node with cst_code
            # For AST modification, we need CSTNode with cst_code
            replacement_code = "def ast_replaced_function():\n    '''Modified via AST->CST->AST'''\n    return 42\n"
            replacement_node = CSTNode(
                file_id=file_id,
                project_id=project_id,
                cst_code=replacement_code,
                cst_hash="",
            )

            # Modify AST (requires file to exist)
            # Note: modify_ast expects ASTNode, but we pass CSTNode which has cst_code
            # The handler will extract cst_code from the node dict
            modify_result = client.modify_ast(
                file_id, filter_obj, TreeAction.REPLACE, [replacement_node]
            )

            # Should succeed if file exists
            if test_file_copy.exists():
                assert (
                    modify_result.is_success()
                ), f"Modify failed: {modify_result.error_description}"
                if modify_result.data:
                    modified_ast = ASTNode.from_dict(modify_result.data)
                    assert modified_ast.ast_json != original_ast_json

        finally:
            client.disconnect()

    def test_complex_query_real_file(self, rpc_server_with_real_data):
        """Test complex CST queries on real file."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file, project_id)

            # Complex query: methods in classes
            filter_obj = XPathFilter(selector="class method")
            result = client.query_cst(file_id, filter_obj)

            assert result.is_success(), f"Query failed: {result.error_description}"
            assert result.data is not None
            assert isinstance(result.data, list)

            # Complex query: return statements in functions
            filter_obj = XPathFilter(selector="function smallstmt[type='Return']")
            result = client.query_cst(file_id, filter_obj)

            assert result.is_success(), f"Query failed: {result.error_description}"
            assert result.data is not None

        finally:
            client.disconnect()

    def test_xpath_filter_with_additional_filters(self, rpc_server_with_real_data):
        """Test XPathFilter with additional filters on real file."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file, project_id)

            # Filter with additional constraints
            filter_obj = XPathFilter(
                selector="function",
                node_type="function",
                start_line=1,
                end_line=100,
            )
            result = client.query_cst(file_id, filter_obj)

            assert result.is_success(), f"Query failed: {result.error_description}"
            assert result.data is not None

        finally:
            client.disconnect()

    def test_atomicity_cst_modify(self, rpc_server_with_real_data, tmp_path):
        """Test that CST modifications are atomic."""
        self._check_test_data_available()

        _, socket_path, _, _ = rpc_server_with_real_data

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        test_file_copy = tmp_path / "test_atomic.py"
        original_content = test_file.read_text()
        test_file_copy.write_text(original_content)

        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                pass

            file_id = self._setup_real_file(client, test_file_copy, project_id)

            # Get original AST hash
            ast_rows = client.select("ast_trees", where={"file_id": file_id}, limit=1)
            original_ast_hash = ast_rows[0]["ast_hash"] if ast_rows else None

            # Try invalid modification (should fail and not change AST)
            invalid_filter = XPathFilter(selector="nonexistent_node_type")
            invalid_result = client.modify_cst(
                file_id, invalid_filter, TreeAction.DELETE, []
            )

            # Should fail
            assert not invalid_result.is_success() or invalid_result.data is None

            # Verify AST was not modified
            ast_rows_after = client.select(
                "ast_trees", where={"file_id": file_id}, limit=1
            )
            if ast_rows_after and original_ast_hash:
                assert ast_rows_after[0]["ast_hash"] == original_ast_hash

        finally:
            client.disconnect()
