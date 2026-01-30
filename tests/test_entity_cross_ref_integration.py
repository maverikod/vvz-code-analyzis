"""
Integration tests for entity cross-ref: update_file_data_atomic and get_entity_dependencies.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database import CodeDatabase


@pytest.fixture
def temp_db():
    """Create temporary database for testing (in-process CodeDatabase)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    driver_config = {
        "type": "sqlite",
        "config": {"path": str(db_path)},
    }
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    try:
        db = CodeDatabase(driver_config)
        yield db
        db.close()
    finally:
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env
        if db_path.exists():
            db_path.unlink(missing_ok=True)


@pytest.fixture
def test_project(temp_db, tmp_path):
    """Create test project in database."""
    project_id = str(uuid.uuid4())
    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    temp_db._commit()
    return project_id


@pytest.fixture
def test_file_with_call(temp_db, tmp_path, test_project):
    """Create a file that has a function call (bar calls foo)."""
    file_path = tmp_path / "mod.py"
    source_code = '''"""
Module with call.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

def foo():
    """Foo."""
    pass

def bar():
    """Bar calls foo."""
    foo()
'''
    file_path.write_text(source_code, encoding="utf-8")
    file_mtime = os.path.getmtime(file_path)
    lines = len(source_code.splitlines())
    file_id = temp_db.add_file(
        path=str(file_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project,
    )
    return file_id, file_path, test_project, tmp_path, source_code


def test_update_file_data_atomic_builds_entity_cross_ref(temp_db, test_file_with_call):
    """After update_file_data_atomic, entity_cross_ref has rows and get_dependencies_by_caller works."""
    file_id, file_path, project_id, root_dir, source_code = test_file_with_call

    temp_db.begin_transaction()
    result = temp_db.update_file_data_atomic(
        file_path=str(file_path),
        project_id=project_id,
        root_dir=root_dir,
        source_code=source_code,
    )
    assert result.get("success") is True, result.get("error")
    temp_db.commit_transaction()

    # Get function ids: bar (caller) and foo (callee)
    funcs = temp_db._fetchall(
        "SELECT id, name FROM functions WHERE file_id = ? ORDER BY line",
        (file_id,),
    )
    name_to_id = {r["name"]: r["id"] for r in funcs}
    assert "foo" in name_to_id
    assert "bar" in name_to_id
    bar_id = name_to_id["bar"]
    foo_id = name_to_id["foo"]

    # Entity cross-ref should have been built
    rows = temp_db._fetchall(
        "SELECT * FROM entity_cross_ref WHERE file_id = ?", (file_id,)
    )
    assert len(rows) >= 1, "Expected at least one entity_cross_ref row (bar -> foo)"

    # get_dependencies_by_caller(bar) should return foo
    deps = temp_db.get_dependencies_by_caller("function", bar_id)
    assert len(deps) >= 1
    callee_ids = [
        d["callee_entity_id"] for d in deps if d["callee_entity_type"] == "function"
    ]
    assert foo_id in callee_ids

    # get_dependents_by_callee(foo) should return bar
    dependents = temp_db.get_dependents_by_callee("function", foo_id)
    assert len(dependents) >= 1
    caller_ids = [
        d["caller_entity_id"]
        for d in dependents
        if d["caller_entity_type"] == "function"
    ]
    assert bar_id in caller_ids


def test_clear_file_data_removes_entity_cross_ref(temp_db, test_file_with_call):
    """clear_file_data removes entity_cross_ref rows for the file."""
    file_id, file_path, project_id, root_dir, source_code = test_file_with_call

    temp_db.begin_transaction()
    result = temp_db.update_file_data_atomic(
        file_path=str(file_path),
        project_id=project_id,
        root_dir=root_dir,
        source_code=source_code,
    )
    assert result.get("success") is True
    temp_db.commit_transaction()

    rows_before = temp_db._fetchall(
        "SELECT COUNT(*) as c FROM entity_cross_ref WHERE file_id = ?",
        (file_id,),
    )
    count_before = rows_before[0]["c"] if rows_before else 0
    assert count_before >= 1

    temp_db.clear_file_data(file_id)

    rows_after = temp_db._fetchall(
        "SELECT COUNT(*) as c FROM entity_cross_ref WHERE file_id = ?",
        (file_id,),
    )
    count_after = rows_after[0]["c"] if rows_after else 0
    assert count_after == 0
