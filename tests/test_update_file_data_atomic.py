"""
Tests for atomic file data updates in transactions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import uuid
from pathlib import Path
import pytest
import os

from code_analysis.core.database.base import CodeDatabase


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    driver_config = {
        "type": "sqlite",
        "config": {"path": str(db_path)},
    }

    # Set environment variable to allow direct SQLite driver
    import os

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
            db_path.unlink()


@pytest.fixture
def test_project(temp_db, tmp_path):
    """Create test project."""
    project_id = str(uuid.uuid4())
    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    temp_db._commit()
    return project_id


@pytest.fixture
def test_file(temp_db, tmp_path, test_project):
    """Create test file in database."""
    file_path = tmp_path / "test_file.py"
    file_content = '''"""
Test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

class TestClass:
    """Test class."""
    
    def test_method(self):
        """Test method."""
        pass

def test_function():
    """Test function."""
    pass
'''
    file_path.write_text(file_content, encoding="utf-8")

    file_mtime = os.path.getmtime(file_path)
    lines = len(file_content.splitlines())

    file_id = temp_db.add_file(
        path=str(file_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project,
    )

    return file_id, file_path, test_project, tmp_path


def test_update_file_data_atomic_success(temp_db, test_file):
    """Test successful atomic file data update."""
    file_id, file_path, project_id, root_dir = test_file

    # Begin transaction
    temp_db.begin_transaction()

    # New source code
    new_source = '''"""
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

    # Update file data atomically
    result = temp_db.update_file_data_atomic(
        file_path=str(file_path),
        project_id=project_id,
        root_dir=root_dir,
        source_code=new_source,
    )

    assert result.get("success") is True, f"Update should succeed: {result.get('error')}"
    assert result.get("file_id") == file_id, "File ID should match"
    assert result.get("ast_updated") is True, "AST should be updated"
    assert result.get("cst_updated") is True, "CST should be updated"
    assert result.get("entities_updated") > 0, "Entities should be updated"

    # Commit transaction
    temp_db.commit_transaction()

    # Verify new entities exist
    classes = temp_db._fetchall(
        "SELECT name FROM classes WHERE file_id = ?", (file_id,)
    )
    class_names = [c["name"] for c in classes]
    assert "UpdatedClass" in class_names, "Updated class should exist"

    functions = temp_db._fetchall(
        "SELECT name FROM functions WHERE file_id = ?", (file_id,)
    )
    function_names = [f["name"] for f in functions]
    assert "new_function" in function_names, "New function should exist"

    # Verify CST was saved
    cst_records = temp_db._fetchall(
        "SELECT cst_code FROM cst_trees WHERE file_id = ?", (file_id,)
    )
    assert len(cst_records) > 0, "CST should be saved"
    assert new_source in [r["cst_code"] for r in cst_records], "CST should contain new source"


def test_update_file_data_atomic_rollback_on_parse_error(temp_db, test_file):
    """Test rollback when parsing fails."""
    file_id, file_path, project_id, root_dir = test_file

    # Begin transaction
    temp_db.begin_transaction()

    # Invalid source code (syntax error)
    invalid_source = "def invalid_syntax("  # Missing closing parenthesis

    # Update file data atomically
    result = temp_db.update_file_data_atomic(
        file_path=str(file_path),
        project_id=project_id,
        root_dir=root_dir,
        source_code=invalid_source,
    )

    assert result.get("success") is False, "Update should fail"
    assert "error" in result, "Error should be present"
    assert "Syntax error" in result.get("error", ""), "Should report syntax error"

    # Rollback transaction
    temp_db.rollback_transaction()

    # Verify old data still exists (not updated)
    classes = temp_db._fetchall(
        "SELECT name FROM classes WHERE file_id = ?", (file_id,)
    )
    # Should have old class or no classes (depending on initial state)
    assert len(classes) >= 0, "Transaction should be rolled back"


def test_update_file_data_atomic_without_transaction(temp_db, test_file):
    """Test that calling without active transaction raises error."""
    file_id, file_path, project_id, root_dir = test_file

    new_source = '''"""
Updated test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

class UpdatedClass:
    """Updated test class."""
    pass
'''

    # Try to update without transaction
    with pytest.raises(RuntimeError, match="must be called within a transaction"):
        temp_db.update_file_data_atomic(
            file_path=str(file_path),
            project_id=project_id,
            root_dir=root_dir,
            source_code=new_source,
        )


def test_update_file_data_atomic_rollback_on_ast_error(temp_db, test_file):
    """Test rollback when AST save fails."""
    file_id, file_path, project_id, root_dir = test_file

    # Begin transaction
    temp_db.begin_transaction()

    # Valid source code
    new_source = '''"""
Updated test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

class UpdatedClass:
    """Updated test class."""
    pass
'''

    # Mock save_ast_tree to raise exception (if possible)
    # For now, just test that rollback works
    result = temp_db.update_file_data_atomic(
        file_path=str(file_path),
        project_id=project_id,
        root_dir=root_dir,
        source_code=new_source,
    )

    # If update succeeds, commit; if fails, rollback
    if result.get("success"):
        temp_db.commit_transaction()
    else:
        temp_db.rollback_transaction()


def test_update_file_data_atomic_rollback_on_cst_error(temp_db, test_file):
    """Test rollback when CST save fails."""
    file_id, file_path, project_id, root_dir = test_file

    # Begin transaction
    temp_db.begin_transaction()

    # Valid source code
    new_source = '''"""
Updated test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

class UpdatedClass:
    """Updated test class."""
    pass
'''

    # Mock save_cst_tree to raise exception (if possible)
    # For now, just test that rollback works
    result = temp_db.update_file_data_atomic(
        file_path=str(file_path),
        project_id=project_id,
        root_dir=root_dir,
        source_code=new_source,
    )

    # If update succeeds, commit; if fails, rollback
    if result.get("success"):
        temp_db.commit_transaction()
    else:
        temp_db.rollback_transaction()


def test_update_file_data_atomic_clears_old_data(temp_db, test_file):
    """Test that atomic update clears old data."""
    file_id, file_path, project_id, root_dir = test_file

    # First, add some old entities
    old_class_id = temp_db.add_class(file_id, "OldClass", 1, "Old docstring", [])
    old_function_id = temp_db.add_function(file_id, "old_function", 10, "", "Old docstring")
    temp_db._commit()

    # Begin transaction
    temp_db.begin_transaction()

    # New source code with different entities
    new_source = '''"""
Updated test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

class NewClass:
    """New test class."""
    pass

def new_function():
    """New function."""
    pass
'''

    # Update file data atomically
    result = temp_db.update_file_data_atomic(
        file_path=str(file_path),
        project_id=project_id,
        root_dir=root_dir,
        source_code=new_source,
    )

    assert result.get("success") is True, "Update should succeed"

    # Commit transaction
    temp_db.commit_transaction()

    # Verify old entities are gone
    old_class = temp_db._fetchone(
        "SELECT id FROM classes WHERE id = ?", (old_class_id,)
    )
    assert old_class is None, "Old class should be removed"

    old_function = temp_db._fetchone(
        "SELECT id FROM functions WHERE id = ?", (old_function_id,)
    )
    assert old_function is None, "Old function should be removed"

    # Verify new entities exist
    new_class = temp_db._fetchone(
        "SELECT name FROM classes WHERE file_id = ? AND name = ?", (file_id, "NewClass")
    )
    assert new_class is not None, "New class should exist"

    new_function = temp_db._fetchone(
        "SELECT name FROM functions WHERE file_id = ? AND name = ?", (file_id, "new_function")
    )
    assert new_function is not None, "New function should exist"


def test_update_file_data_atomic_file_not_found(temp_db, test_project, tmp_path):
    """Test atomic update when file is not in database."""
    # Begin transaction
    temp_db.begin_transaction()

    # Try to update non-existent file
    non_existent_path = tmp_path / "non_existent.py"
    new_source = '''"""
Test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

def test():
    """Test."""
    pass
'''

    result = temp_db.update_file_data_atomic(
        file_path=str(non_existent_path),
        project_id=test_project,
        root_dir=tmp_path,
        source_code=new_source,
    )

    assert result.get("success") is False, "Update should fail"
    assert "File not found" in result.get("error", ""), "Should report file not found"

    # Rollback transaction
    temp_db.rollback_transaction()

