"""
Tests for database file update operations (DatabaseClient + InProcessRpcClient).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterator, List, Optional

import pytest

from code_analysis.core.database.files.trash_standalone_support import (
    clear_file_data_via_driver,
    clear_file_vectors_via_driver,
)
from code_analysis.core.database.files.update import update_file_data
from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers

from tests.test_fixture_content import DEFAULT_TEST_FILE_CONTENT


class _ClientFacade:
    """Surface for :func:`update_file_data` and CRUD helpers used by these tests."""

    def __init__(self, client: DatabaseClient, driver: SQLiteDriver) -> None:
        """Initialize the instance."""
        self._c = client
        self._driver = driver

    def __getattr__(self, name: str) -> Any:
        """Return getattr."""
        return getattr(self._c, name)

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Return execute."""
        self._c.execute(sql, params)

    def _commit(self) -> None:
        """Return commit."""
        pass

    def _fetchone(self, sql: str, params: Optional[tuple] = None):
        """Return fetchone."""
        r = self._c.execute(sql, params)
        rows = r.get("data") or []
        return rows[0] if rows else None

    def _fetchall(self, sql: str, params: Optional[tuple] = None) -> List[dict]:
        """Return fetchall."""
        r = self._c.execute(sql, params)
        return list(r.get("data") or [])

    def _clear_file_vectors(self, file_id: Any) -> None:
        """Return clear file vectors."""
        clear_file_vectors_via_driver(self._driver, str(file_id))

    def clear_file_data(self, file_id: Any) -> None:
        """Return clear file data."""
        clear_file_data_via_driver(self._driver, str(file_id))


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_id():
    """Generate valid UUID4 project ID."""
    return str(uuid.uuid4())


@pytest.fixture
def test_db(temp_dir: Path) -> Iterator[_ClientFacade]:
    """Create test database."""
    db_path = temp_dir / "test.db"
    driver = create_driver("sqlite", {"path": str(db_path)})
    assert isinstance(driver, SQLiteDriver)
    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=ipc)
    client.connect()
    backup_dir = temp_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    client.sync_schema(get_schema_definition(), backup_dir=str(backup_dir))
    try:
        yield _ClientFacade(client, driver)
    finally:
        client.disconnect()


@pytest.fixture
def test_project(test_db: _ClientFacade, temp_dir: Path, project_id: str):
    """Create test project in database and projectid file for path validation."""
    project_name = temp_dir.name
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), project_name),
    )
    (temp_dir / "projectid").write_text(
        json.dumps({"id": project_id}), encoding="utf-8"
    )
    return project_id


@pytest.fixture
def test_file(test_db: _ClientFacade, temp_dir: Path, test_project: str):
    """Create test file in database and filesystem (substantial content for search)."""
    file_path = temp_dir / "test_file.py"
    file_content = DEFAULT_TEST_FILE_CONTENT
    file_path.write_text(file_content, encoding="utf-8")

    file_mtime = os.path.getmtime(file_path)
    lines = len(file_content.splitlines())

    file_id = test_db.add_file(
        path=str(file_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project,
    )

    tree = ast.parse(file_content, filename=str(file_path))
    ast_json = json.dumps(ast.dump(tree))
    ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

    test_db._execute(
        """
        INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, test_project, ast_json, ast_hash, file_mtime),
    )

    cst_hash = hashlib.sha256(file_content.encode()).hexdigest()
    test_db._execute(
        """
        INSERT INTO cst_trees (file_id, project_id, cst_code, cst_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, test_project, file_content, cst_hash, file_mtime),
    )

    test_db._execute(
        """
        INSERT INTO classes (file_id, name, line, docstring, bases, cst_node_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            file_id,
            "TestClass",
            10,
            "Helper class for validation and configuration in tests.",
            "[]",
            "fixture:TestClass:ClassDef:10:0-14:0",
        ),
    )
    class_row = test_db._fetchone(
        "SELECT id FROM classes WHERE file_id = ? AND name = ?", (file_id, "TestClass")
    )
    class_id = class_row["id"] if class_row else None

    if class_id:
        test_db._execute(
            """
            INSERT INTO methods (class_id, name, line, args, docstring, cst_node_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                class_id,
                "test_method",
                14,
                "[]",
                "Validates input configuration and returns True if settings are correct.",
                "fixture:test_method:FunctionDef:14:0-18:0",
            ),
        )

    test_db._execute(
        """
        INSERT INTO functions (file_id, name, line, args, docstring, cst_node_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            file_id,
            "test_function",
            22,
            "[]",
            "Processes raw data and returns normalized result.",
            "fixture:test_function:FunctionDef:22:0-26:0",
        ),
    )

    return file_id, file_path, test_project


class TestClearFileData:
    """Tests for clear_file_data method."""

    def test_clear_file_data_includes_cst_trees(self, test_db, test_file, test_project):
        """Test that clear_file_data deletes CST trees."""
        file_id, file_path, project_id = test_file

        cst_before = test_db._fetchone(
            "SELECT id FROM cst_trees WHERE file_id = ?", (file_id,)
        )
        assert cst_before is not None, "CST tree should exist before clearing"

        ast_before = test_db._fetchone(
            "SELECT id FROM ast_trees WHERE file_id = ?", (file_id,)
        )
        assert ast_before is not None, "AST tree should exist before clearing"

        classes_before = test_db._fetchall(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(classes_before) > 0, "Classes should exist before clearing"

        test_db.clear_file_data(file_id)

        cst_after = test_db._fetchone(
            "SELECT id FROM cst_trees WHERE file_id = ?", (file_id,)
        )
        assert cst_after is None, "CST tree should be deleted after clearing"

        ast_after = test_db._fetchone(
            "SELECT id FROM ast_trees WHERE file_id = ?", (file_id,)
        )
        assert ast_after is None, "AST tree should be deleted after clearing"

        classes_after = test_db._fetchall(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(classes_after) == 0, "Classes should be deleted after clearing"

        functions_after = test_db._fetchall(
            "SELECT id FROM functions WHERE file_id = ?", (file_id,)
        )
        assert len(functions_after) == 0, "Functions should be deleted after clearing"


class TestUpdateFileData:
    """Tests for update_file_data via :func:`update_file_data`."""

    def test_update_file_data_success(self, test_db, test_file, test_project, temp_dir):
        """Test successful file data update."""
        file_id, file_path, project_id = test_file

        new_content = '''"""
Updated test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

class UpdatedClass:
    """Updated test class."""
    
    def new_method(self):
        """New method."""
        pass

def new_function():
    """New function."""
    pass
'''
        file_path.write_text(new_content, encoding="utf-8")

        test_db._execute("UPDATE files SET last_modified = 0 WHERE id = ?", (file_id,))

        abs_path = str(file_path.resolve())

        result = update_file_data(
            test_db,
            file_path=abs_path,
            project_id=project_id,
            root_dir=temp_dir,
        )

        assert result.get("success") is True, "Update should succeed"
        assert result.get("file_id") == file_id, "File ID should match"
        assert result.get("ast_updated") is True, "AST should be updated"
        assert result.get("cst_updated") is True, "CST should be updated"
        assert (result.get("entities_updated") or 0) > 0, "Entities should be updated"

        classes = test_db._fetchall(
            "SELECT name FROM classes WHERE file_id = ?", (file_id,)
        )
        class_names = [c["name"] for c in classes]
        assert "UpdatedClass" in class_names, "Updated class should exist"
        assert "TestClass" not in class_names, "Old class should be removed"

        functions = test_db._fetchall(
            "SELECT name FROM functions WHERE file_id = ?", (file_id,)
        )
        function_names = [f["name"] for f in functions]
        assert "new_function" in function_names, "New function should exist"
        assert "test_function" not in function_names, "Old function should be removed"

    def test_update_file_data_file_not_found(self, test_db, test_project, temp_dir):
        """Test update_file_data with file not in database."""
        result = update_file_data(
            test_db,
            file_path="nonexistent.py",
            project_id=test_project,
            root_dir=temp_dir,
        )

        assert result.get("success") is False, "Update should fail"
        assert (
            "not found" in result.get("error", "").lower()
        ), "Error should mention file not found"

    def test_update_file_data_project_not_found(self, test_db, temp_dir):
        """Test update_file_data when project_id is not in projects (FK race guard)."""
        missing_project_id = str(uuid.uuid4())
        result = update_file_data(
            test_db,
            file_path=str(temp_dir / "any.py"),
            project_id=missing_project_id,
            root_dir=temp_dir,
        )
        assert result.get("success") is False
        assert "Project not found" in result.get("error", "")
        assert missing_project_id in result.get("error", "")

    def test_update_file_data_syntax_error(
        self, test_db, test_file, test_project, temp_dir
    ):
        """Test update_file_data with syntax error in file."""
        file_id, file_path, project_id = test_file

        invalid_content = (
            "class Invalid:\n    def method(\n    pass"  # Missing closing paren
        )
        file_path.write_text(invalid_content, encoding="utf-8")

        test_db._execute("UPDATE files SET last_modified = 0 WHERE id = ?", (file_id,))

        abs_path = str(file_path.resolve())

        result = update_file_data(
            test_db,
            file_path=abs_path,
            project_id=project_id,
            root_dir=temp_dir,
        )

        assert result.get("success") is False, "Update should fail on syntax error"
        assert "error" in result, "Result should contain error information"

    def test_update_file_data_clears_old_records(
        self, test_db, test_file, test_project, temp_dir
    ):
        """Test that update_file_data clears old records before creating new ones."""
        file_id, file_path, project_id = test_file

        old_classes = test_db._fetchall(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(old_classes) > 0, "Old classes should exist"

        old_class_ids = [c["id"] for c in old_classes]

        new_content = '''"""
New content.
"""

class NewClass:
    """New class."""
    pass
'''
        file_path.write_text(new_content, encoding="utf-8")

        test_db._execute("UPDATE files SET last_modified = 0 WHERE id = ?", (file_id,))

        abs_path = str(file_path.resolve())

        result = update_file_data(
            test_db,
            file_path=abs_path,
            project_id=project_id,
            root_dir=temp_dir,
        )

        assert result.get("success") is True, "Update should succeed"

        for old_class_id in old_class_ids:
            old_class = test_db._fetchone(
                "SELECT id FROM classes WHERE id = ?", (old_class_id,)
            )
            assert old_class is None, f"Old class {old_class_id} should be deleted"

        new_classes = test_db._fetchall(
            "SELECT name FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(new_classes) == 1, "Should have one new class"
        assert (
            new_classes[0]["name"] == "NewClass"
        ), "New class should be named NewClass"

    def test_update_file_data_creates_new_records(
        self, test_db, test_file, test_project, temp_dir
    ):
        """Test that update_file_data creates new records."""
        file_id, file_path, project_id = test_file

        new_content = '''"""
Test file with multiple entities.
"""

class ClassA:
    """Class A."""
    pass

class ClassB:
    """Class B."""
    pass

def func_a():
    """Function A."""
    pass

def func_b():
    """Function B."""
    pass
'''
        file_path.write_text(new_content, encoding="utf-8")

        test_db._execute("UPDATE files SET last_modified = 0 WHERE id = ?", (file_id,))

        abs_path = str(file_path.resolve())

        result = update_file_data(
            test_db,
            file_path=abs_path,
            project_id=project_id,
            root_dir=temp_dir,
        )

        assert result.get("success") is True, "Update should succeed"
        assert (
            result.get("entities_updated") == 4
        ), "Should have 2 classes + 2 functions"

        ast_record = test_db._fetchone(
            "SELECT id FROM ast_trees WHERE file_id = ?", (file_id,)
        )
        assert ast_record is not None, "AST tree should be saved"

        cst_record = test_db._fetchone(
            "SELECT id FROM cst_trees WHERE file_id = ?", (file_id,)
        )
        assert cst_record is not None, "CST tree should be saved"

        classes = test_db._fetchall(
            "SELECT name FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(classes) == 2, "Should have 2 classes"
        class_names = {c["name"] for c in classes}
        assert class_names == {"ClassA", "ClassB"}, "Should have both classes"

        functions = test_db._fetchall(
            "SELECT name FROM functions WHERE file_id = ?", (file_id,)
        )
        assert len(functions) == 2, "Should have 2 functions"
        function_names = {f["name"] for f in functions}
        assert function_names == {"func_a", "func_b"}, "Should have both functions"
