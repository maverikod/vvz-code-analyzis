"""
Unit tests for entity_cross_ref database module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


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
def test_db(temp_dir):
    """Create test database with schema (including entity_cross_ref)."""
    db_path = temp_dir / "test.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    yield db
    db.close()


@pytest.fixture
def test_project(test_db, temp_dir, project_id):
    """Create test project in database."""
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), temp_dir.name),
    )
    test_db._commit()
    return project_id


@pytest.fixture
def test_file_and_entities(test_db, temp_dir, test_project):
    """Create a file and entities (class, method, function) for cross-ref tests."""
    file_path = temp_dir / "module.py"
    file_path.write_text("", encoding="utf-8")
    test_db._execute(
        """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
           VALUES (?, ?, 0, 0, 0)""",
        (test_project, str(file_path)),
    )
    test_db._commit()
    file_id = test_db._lastrowid()

    test_db._execute(
        "INSERT INTO classes (file_id, name, line, end_line, docstring, bases) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "MyClass", 1, 10, None, "[]"),
    )
    test_db._commit()
    class_id = test_db._lastrowid()

    test_db._execute(
        "INSERT INTO methods (class_id, name, line, end_line, args, docstring) VALUES (?, ?, ?, ?, ?, ?)",
        (class_id, "my_method", 3, 8, "[]", None),
    )
    test_db._commit()
    method_id = test_db._lastrowid()

    test_db._execute(
        "INSERT INTO functions (file_id, name, line, end_line, args, docstring) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "my_func", 12, 15, "[]", None),
    )
    test_db._commit()
    function_id = test_db._lastrowid()

    return {
        "file_id": file_id,
        "class_id": class_id,
        "method_id": method_id,
        "function_id": function_id,
    }


class TestAddEntityCrossRef:
    """Tests for add_entity_cross_ref."""

    def test_add_caller_method_callee_function(self, test_db, test_file_and_entities):
        """Add cross-ref from method to function."""
        ids = test_file_and_entities
        ref_id = test_db.add_entity_cross_ref(
            caller_class_id=None,
            caller_method_id=ids["method_id"],
            caller_function_id=None,
            callee_class_id=None,
            callee_method_id=None,
            callee_function_id=ids["function_id"],
            ref_type="call",
            file_id=ids["file_id"],
            line=5,
        )
        assert ref_id is not None
        assert ref_id > 0
        row = test_db._fetchone(
            "SELECT * FROM entity_cross_ref WHERE id = ?", (ref_id,)
        )
        assert row is not None
        assert row["caller_method_id"] == ids["method_id"]
        assert row["callee_function_id"] == ids["function_id"]
        assert row["ref_type"] == "call"
        assert row["line"] == 5

    def test_add_caller_class_callee_class(self, test_db, test_file_and_entities):
        """Add cross-ref from class to class (e.g. inheritance)."""
        ids = test_file_and_entities
        ref_id = test_db.add_entity_cross_ref(
            caller_class_id=ids["class_id"],
            caller_method_id=None,
            caller_function_id=None,
            callee_class_id=ids["class_id"],
            callee_method_id=None,
            callee_function_id=None,
            ref_type="inherit",
            file_id=ids["file_id"],
            line=1,
        )
        assert ref_id > 0

    def test_add_entity_cross_ref_invalid_caller_raises(
        self, test_db, test_file_and_entities
    ):
        """Exactly one caller_* must be set."""
        ids = test_file_and_entities
        with pytest.raises(ValueError, match="Exactly one of caller"):
            test_db.add_entity_cross_ref(
                caller_class_id=ids["class_id"],
                caller_method_id=ids["method_id"],
                caller_function_id=None,
                callee_class_id=None,
                callee_method_id=None,
                callee_function_id=ids["function_id"],
                ref_type="call",
            )

    def test_add_entity_cross_ref_invalid_callee_raises(
        self, test_db, test_file_and_entities
    ):
        """Exactly one callee_* must be set."""
        ids = test_file_and_entities
        with pytest.raises(ValueError, match="Exactly one of callee"):
            test_db.add_entity_cross_ref(
                caller_class_id=None,
                caller_method_id=ids["method_id"],
                caller_function_id=None,
                callee_class_id=ids["class_id"],
                callee_method_id=ids["method_id"],
                callee_function_id=None,
                ref_type="call",
            )

    def test_add_entity_cross_ref_invalid_ref_type_raises(
        self, test_db, test_file_and_entities
    ):
        """ref_type must be valid."""
        ids = test_file_and_entities
        with pytest.raises(ValueError, match="ref_type"):
            test_db.add_entity_cross_ref(
                caller_class_id=None,
                caller_method_id=ids["method_id"],
                caller_function_id=None,
                callee_class_id=None,
                callee_method_id=None,
                callee_function_id=ids["function_id"],
                ref_type="invalid",
            )


class TestGetDependenciesByCaller:
    """Tests for get_dependencies_by_caller."""

    def test_get_dependencies_by_caller_method(self, test_db, test_file_and_entities):
        """Get dependencies of a method."""
        ids = test_file_and_entities
        test_db.add_entity_cross_ref(
            caller_class_id=None,
            caller_method_id=ids["method_id"],
            caller_function_id=None,
            callee_class_id=None,
            callee_method_id=None,
            callee_function_id=ids["function_id"],
            ref_type="call",
            file_id=ids["file_id"],
            line=5,
        )
        deps = test_db.get_dependencies_by_caller("method", ids["method_id"])
        assert len(deps) == 1
        assert deps[0]["callee_entity_type"] == "function"
        assert deps[0]["callee_entity_id"] == ids["function_id"]
        assert deps[0]["ref_type"] == "call"

    def test_get_dependencies_by_caller_class(self, test_db, test_file_and_entities):
        """Get dependencies of a class."""
        ids = test_file_and_entities
        test_db.add_entity_cross_ref(
            caller_class_id=ids["class_id"],
            caller_method_id=None,
            caller_function_id=None,
            callee_class_id=None,
            callee_method_id=None,
            callee_function_id=ids["function_id"],
            ref_type="call",
            file_id=ids["file_id"],
            line=2,
        )
        deps = test_db.get_dependencies_by_caller("class", ids["class_id"])
        assert len(deps) == 1
        assert deps[0]["callee_entity_type"] == "function"

    def test_get_dependencies_by_caller_empty(self, test_db, test_file_and_entities):
        """No dependencies returns empty list."""
        ids = test_file_and_entities
        deps = test_db.get_dependencies_by_caller("method", ids["method_id"])
        assert deps == []

    def test_get_dependencies_by_caller_invalid_type_raises(self, test_db):
        """Invalid caller_entity_type raises."""
        with pytest.raises(ValueError, match="caller_entity_type"):
            test_db.get_dependencies_by_caller("module", 1)


class TestGetDependentsByCallee:
    """Tests for get_dependents_by_callee."""

    def test_get_dependents_by_callee_function(self, test_db, test_file_and_entities):
        """Get dependents of a function."""
        ids = test_file_and_entities
        test_db.add_entity_cross_ref(
            caller_class_id=None,
            caller_method_id=ids["method_id"],
            caller_function_id=None,
            callee_class_id=None,
            callee_method_id=None,
            callee_function_id=ids["function_id"],
            ref_type="call",
            file_id=ids["file_id"],
            line=5,
        )
        deps = test_db.get_dependents_by_callee("function", ids["function_id"])
        assert len(deps) == 1
        assert deps[0]["caller_entity_type"] == "method"
        assert deps[0]["caller_entity_id"] == ids["method_id"]
        assert deps[0]["ref_type"] == "call"

    def test_get_dependents_by_callee_empty(self, test_db, test_file_and_entities):
        """No dependents returns empty list."""
        ids = test_file_and_entities
        deps = test_db.get_dependents_by_callee("function", ids["function_id"])
        assert deps == []

    def test_get_dependents_by_callee_invalid_type_raises(self, test_db):
        """Invalid callee_entity_type raises."""
        with pytest.raises(ValueError, match="callee_entity_type"):
            test_db.get_dependents_by_callee("module", 1)


class TestDeleteEntityCrossRefForFile:
    """Tests for delete_entity_cross_ref_for_file."""

    def test_delete_entity_cross_ref_for_file_removes_by_file_id(
        self, test_db, test_file_and_entities
    ):
        """Rows with file_id are removed."""
        ids = test_file_and_entities
        test_db.add_entity_cross_ref(
            caller_class_id=None,
            caller_method_id=ids["method_id"],
            caller_function_id=None,
            callee_class_id=None,
            callee_method_id=None,
            callee_function_id=ids["function_id"],
            ref_type="call",
            file_id=ids["file_id"],
            line=5,
        )
        count_before = test_db._fetchone("SELECT COUNT(*) as c FROM entity_cross_ref")[
            "c"
        ]
        assert count_before == 1
        test_db.delete_entity_cross_ref_for_file(ids["file_id"])
        count_after = test_db._fetchone("SELECT COUNT(*) as c FROM entity_cross_ref")[
            "c"
        ]
        assert count_after == 0

    def test_delete_entity_cross_ref_for_file_removes_by_caller_callee(
        self, test_db, test_file_and_entities
    ):
        """Rows where caller/callee belongs to file are removed."""
        ids = test_file_and_entities
        test_db.add_entity_cross_ref(
            caller_class_id=None,
            caller_method_id=ids["method_id"],
            caller_function_id=None,
            callee_class_id=None,
            callee_method_id=None,
            callee_function_id=ids["function_id"],
            ref_type="call",
            file_id=ids["file_id"],
            line=5,
        )
        test_db.delete_entity_cross_ref_for_file(ids["file_id"])
        count = test_db._fetchone("SELECT COUNT(*) as c FROM entity_cross_ref")["c"]
        assert count == 0
