"""
Unit tests for entity_cross_ref_builder module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import uuid
from pathlib import Path

import pytest

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

from code_analysis.core.entity_cross_ref_builder import (
    resolve_caller,
    resolve_callee,
    build_entity_cross_ref_for_file,
)


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
    """Create test database with full schema via in-process RPC + DatabaseClient."""
    facade, raw_client = make_sqlite_in_process_legacy_facade(temp_dir)
    try:
        yield facade
    finally:
        raw_client.disconnect()


@pytest.fixture
def test_project(test_db, temp_dir, project_id):
    """Create test project in database."""
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), temp_dir.name),
    )
    test_db._commit()
    return project_id


def _make_uuid4():
    """Return a valid UUID4 string for test entity cst_node_id."""
    return str(uuid.uuid4())


@pytest.fixture
def file_with_entities(test_db, test_project, temp_dir):
    """Create a file and entities with line ranges for resolve_caller."""
    file_path = temp_dir / "mod.py"
    file_path.write_text("", encoding="utf-8")
    file_row_id = str(uuid.uuid4())
    test_db._execute(
        """INSERT INTO files (id, project_id, path, lines, last_modified, has_docstring)
           VALUES (?, ?, ?, 10, 0, 0)""",
        (file_row_id, test_project, str(file_path)),
    )
    test_db._commit()
    file_id = file_row_id

    # Class lines 1-20
    class_cst_id = _make_uuid4()
    class_row_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (class_row_id, file_id, "Foo", 1, 20, None, "[]", class_cst_id),
    )
    test_db._commit()
    class_id = class_row_id

    # Method lines 3-8
    method_cst_id = _make_uuid4()
    method_row_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO methods (id, class_id, name, line, end_line, args, docstring, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (method_row_id, class_id, "bar", 3, 8, "[]", None, method_cst_id),
    )
    test_db._commit()
    method_id = method_row_id

    # Function lines 12-18
    func_cst_id = _make_uuid4()
    function_row_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO functions (id, file_id, name, line, end_line, args, docstring, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (function_row_id, file_id, "baz", 12, 18, "[]", None, func_cst_id),
    )
    test_db._commit()
    function_id = function_row_id

    return {
        "file_id": file_id,
        "class_id": class_id,
        "method_id": method_id,
        "function_id": function_id,
        "project_id": test_project,
    }


class TestResolveCaller:
    """Tests for resolve_caller."""

    def test_resolve_caller_line_in_method(self, test_db, file_with_entities):
        """Line inside method returns method."""
        ids = file_with_entities
        result = resolve_caller(test_db, ids["file_id"], 5)
        assert result is not None
        assert result[0] == "method"
        assert result[1] == ids["method_id"]

    def test_resolve_caller_line_in_function(self, test_db, file_with_entities):
        """Line inside function returns function."""
        ids = file_with_entities
        result = resolve_caller(test_db, ids["file_id"], 14)
        assert result is not None
        assert result[0] == "function"
        assert result[1] == ids["function_id"]

    def test_resolve_caller_line_in_class_only(self, test_db, file_with_entities):
        """Line in class but not in method/function returns class (e.g. line 9)."""
        ids = file_with_entities
        result = resolve_caller(test_db, ids["file_id"], 9)
        assert result is not None
        assert result[0] == "class"
        assert result[1] == ids["class_id"]

    def test_resolve_caller_prefer_smallest_span(self, test_db, file_with_entities):
        """When line is in both method and class, prefer method (smaller span)."""
        ids = file_with_entities
        result = resolve_caller(test_db, ids["file_id"], 4)
        assert result is not None
        assert result[0] == "method"
        assert result[1] == ids["method_id"]

    def test_resolve_caller_out_of_range_returns_none(
        self, test_db, file_with_entities
    ):
        """Line not in any entity returns None."""
        ids = file_with_entities
        result = resolve_caller(test_db, ids["file_id"], 100)
        assert result is None

    def test_resolve_caller_null_end_line_treated_as_single_line(
        self, test_db, file_with_entities
    ):
        """Entity with NULL end_line: line must equal start line."""
        ids = file_with_entities
        test_db._execute(
            "UPDATE methods SET end_line = NULL WHERE id = ?",
            (ids["method_id"],),
        )
        test_db._commit()
        result = resolve_caller(test_db, ids["file_id"], 3)
        assert result is not None
        assert result[0] == "method"
        result_none = resolve_caller(test_db, ids["file_id"], 4)
        assert result_none is None or result_none[0] != "method"


class TestResolveCallee:
    """Tests for resolve_callee."""

    def test_resolve_callee_class(self, test_db, file_with_entities):
        """Resolve class by name in project."""
        ids = file_with_entities
        result = resolve_callee(
            test_db, ids["project_id"], ids["file_id"], 1, "class", "Foo", None
        )
        assert result is not None
        assert result[0] == "class"
        assert result[1] == ids["class_id"]

    def test_resolve_callee_function(self, test_db, file_with_entities):
        """Resolve function by name in project."""
        ids = file_with_entities
        result = resolve_callee(
            test_db, ids["project_id"], ids["file_id"], 1, "function", "baz", None
        )
        assert result is not None
        assert result[0] == "function"
        assert result[1] == ids["function_id"]

    def test_resolve_callee_method(self, test_db, file_with_entities):
        """Resolve method by class name and method name."""
        ids = file_with_entities
        result = resolve_callee(
            test_db, ids["project_id"], ids["file_id"], 1, "method", "bar", "Foo"
        )
        assert result is not None
        assert result[0] == "method"
        assert result[1] == ids["method_id"]

    def test_resolve_callee_method_no_class_returns_none(
        self, test_db, file_with_entities
    ):
        """Method without target_class returns None."""
        ids = file_with_entities
        result = resolve_callee(
            test_db, ids["project_id"], ids["file_id"], 1, "method", "bar", None
        )
        assert result is None

    def test_resolve_callee_not_found_returns_none(self, test_db, file_with_entities):
        """Unknown entity name returns None."""
        ids = file_with_entities
        result = resolve_callee(
            test_db,
            ids["project_id"],
            ids["file_id"],
            1,
            "function",
            "NonExistent",
            None,
        )
        assert result is None


class TestBuildEntityCrossRefForFile:
    """Tests for build_entity_cross_ref_for_file."""

    def test_build_entity_cross_ref_for_file_adds_rows(
        self, test_db, file_with_entities
    ):
        """When usages exist and caller/callee resolve, rows are added."""
        ids = file_with_entities
        test_db._execute(
            """INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ids["file_id"], 5, "call", "function", "baz", None),
        )
        test_db._commit()
        added = build_entity_cross_ref_for_file(
            test_db, ids["file_id"], ids["project_id"], ""
        )
        assert added >= 1
        rows = test_db._fetchall(
            "SELECT * FROM entity_cross_ref WHERE file_id = ?",
            (ids["file_id"],),
        )
        assert len(rows) >= 1

    def test_build_entity_cross_ref_for_file_no_usages(
        self, test_db, file_with_entities
    ):
        """No usages => no cross-ref rows added."""
        ids = file_with_entities
        added = build_entity_cross_ref_for_file(
            test_db, ids["file_id"], ids["project_id"], ""
        )
        assert added == 0

    def test_build_entity_cross_ref_for_file_unresolved_callee_skipped(
        self, test_db, file_with_entities
    ):
        """Usage that cannot resolve callee does not add row."""
        ids = file_with_entities
        test_db._execute(
            """INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ids["file_id"], 5, "call", "function", "NonExistent", None),
        )
        test_db._commit()
        added = build_entity_cross_ref_for_file(
            test_db, ids["file_id"], ids["project_id"], ""
        )
        assert added == 0
