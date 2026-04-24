"""
Integration test: update_file_data_atomic_batch writes known data; DB contents are asserted.

Uses real CodeDatabase (temp_db) with execute_batch so that the batch path is exercised
and we verify exact counts and content in ast_trees, cst_trees, classes, methods,
functions, imports.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid

import pytest

from code_analysis.core.database.base import CodeDatabase
from code_analysis.core.database_client.file_data_batch import (
    update_file_data_atomic_batch,
)


# Fixed source: known number of classes, methods, functions, imports.
# Expected: 1 class (Foo), 1 method (m), 1 function (bar), 2 imports (os, sys).
BATCH_TEST_SOURCE = '''"""
Module for batch integration test.
"""

import os
import sys


def bar():
    """Function bar."""
    pass


class Foo:
    """Class Foo."""

    def m(self):
        """Method m."""
        pass
'''


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database (CodeDatabase with direct sqlite, execute_batch)."""
    db_path = tmp_path / "batch_test.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    driver_config = {
        "type": "sqlite",
        "config": {"path": str(db_path), "backup_dir": str(backup_dir)},
    }
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    try:
        db = CodeDatabase(driver_config)
        db.sync_schema()
        yield db
        db.close()
    finally:
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env
        if db_path.exists():
            try:
                db_path.unlink(missing_ok=True)
            except OSError:
                pass


@pytest.fixture
def test_project(temp_db, tmp_path):
    """Create test project and file record; return (file_id, project_id, tmp_path)."""
    project_id = str(uuid.uuid4())
    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    temp_db._commit()

    file_path = tmp_path / "batch_test.py"
    file_path.write_text(BATCH_TEST_SOURCE, encoding="utf-8")
    file_mtime = os.path.getmtime(file_path)
    lines = len(BATCH_TEST_SOURCE.splitlines())
    file_id = temp_db.add_file(
        path=str(file_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=project_id,
    )
    return file_id, project_id, tmp_path


def test_update_file_data_atomic_batch_writes_expected_db_contents(
    temp_db, test_project
) -> None:
    """After update_file_data_atomic_batch, DB has exactly expected rows and content."""
    file_id, project_id, root_dir = test_project
    file_path = root_dir / "batch_test.py"
    file_mtime = 0.0

    # execute_logical_write_operation (used inside update_file_data_atomic_batch)
    # opens and commits its own transaction; do not wrap with begin_transaction here.
    result = update_file_data_atomic_batch(
        database=temp_db,
        file_id=file_id,
        project_id=project_id,
        source_code=BATCH_TEST_SOURCE,
        file_path=str(file_path),
        file_mtime=file_mtime,
    )

    assert result.get("success") is True
    assert result.get("classes") == 1
    assert result.get("methods") == 1
    assert result.get("functions") == 1
    assert result.get("imports") == 2

    # Expected DB contents
    classes = temp_db._fetchall(
        "SELECT id, name, line FROM classes WHERE file_id = ?", (file_id,)
    )
    assert len(classes) == 1
    assert classes[0]["name"] == "Foo"
    assert classes[0]["line"] >= 1

    methods = temp_db._fetchall(
        "SELECT id, name, line, class_id FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id = ?)",
        (file_id,),
    )
    assert len(methods) == 1
    assert methods[0]["name"] == "m"
    assert methods[0]["line"] >= 1

    functions = temp_db._fetchall(
        "SELECT id, name, line FROM functions WHERE file_id = ?", (file_id,)
    )
    assert len(functions) == 1
    assert functions[0]["name"] == "bar"
    assert functions[0]["line"] >= 1

    imports = temp_db._fetchall(
        "SELECT id, name, line FROM imports WHERE file_id = ?", (file_id,)
    )
    assert len(imports) == 2
    names = {r["name"] for r in imports}
    assert "os" in names
    assert "sys" in names

    # AST/CST stored
    ast_rows = temp_db._fetchall(
        "SELECT id, file_id, ast_hash FROM ast_trees WHERE file_id = ?", (file_id,)
    )
    assert len(ast_rows) == 1
    assert ast_rows[0]["file_id"] == file_id

    cst_rows = temp_db._fetchall(
        "SELECT id, file_id, cst_code FROM cst_trees WHERE file_id = ?", (file_id,)
    )
    assert len(cst_rows) == 1
    assert cst_rows[0]["cst_code"] == BATCH_TEST_SOURCE
