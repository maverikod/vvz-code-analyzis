"""
Tests for database file update operations.

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
    """Create test database."""
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
    project_name = temp_dir.name
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), project_name),
    )
    test_db._commit()
    return project_id


@pytest.fixture
def test_file(test_db, temp_dir, test_project):
    """Create test file in database and filesystem."""
    file_path = temp_dir / "test_file.py"
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
    
    import os
    file_mtime = os.path.getmtime(file_path)
    lines = len(file_content.splitlines())
    
    file_id = test_db.add_file(
        path=str(file_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project,
    )
    
    # Add AST and CST trees directly via SQL
    import ast
    import json
    import hashlib
    
    tree = ast.parse(file_content, filename=str(file_path))
    ast_json = json.dumps(ast.dump(tree))
    ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()
    
    # Insert AST tree
    test_db._execute(
        """
        INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, test_project, ast_json, ast_hash, file_mtime),
    )
    
    # Insert CST tree
    cst_hash = hashlib.sha256(file_content.encode()).hexdigest()
    test_db._execute(
        """
        INSERT INTO cst_trees (file_id, project_id, cst_code, cst_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, test_project, file_content, cst_hash, file_mtime),
    )
    
    # Add some entities directly via SQL
    # Insert class (column is 'line', not 'line_number')
    test_db._execute(
        """
        INSERT INTO classes (file_id, name, line, docstring, bases)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, "TestClass", 7, "Test class.", "[]"),
    )
    class_row = test_db._fetchone(
        "SELECT id FROM classes WHERE file_id = ? AND name = ?", (file_id, "TestClass")
    )
    class_id = class_row["id"] if class_row else None
    
    # Insert method
    if class_id:
        test_db._execute(
            """
            INSERT INTO methods (class_id, name, line, args, docstring)
            VALUES (?, ?, ?, ?, ?)
            """,
            (class_id, "test_method", 10, "[]", "Test method."),
        )
    
    # Insert function
    test_db._execute(
        """
        INSERT INTO functions (file_id, name, line, args, docstring)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, "test_function", 14, "[]", "Test function."),
    )
    
    test_db._commit()
    
    return file_id, file_path, test_project


class TestClearFileData:
    """Tests for clear_file_data method."""

    def test_clear_file_data_includes_cst_trees(
        self, test_db, test_file, test_project
    ):
        """Test that clear_file_data deletes CST trees."""
        file_id, file_path, project_id = test_file
        
        # Verify CST tree exists before clearing
        cst_before = test_db._fetchone(
            "SELECT id FROM cst_trees WHERE file_id = ?", (file_id,)
        )
        assert cst_before is not None, "CST tree should exist before clearing"
        
        # Verify AST tree exists before clearing
        ast_before = test_db._fetchone(
            "SELECT id FROM ast_trees WHERE file_id = ?", (file_id,)
        )
        assert ast_before is not None, "AST tree should exist before clearing"
        
        # Verify entities exist before clearing
        classes_before = test_db._fetchall(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(classes_before) > 0, "Classes should exist before clearing"
        
        # Clear file data
        test_db.clear_file_data(file_id)
        
        # Verify CST tree is deleted
        cst_after = test_db._fetchone(
            "SELECT id FROM cst_trees WHERE file_id = ?", (file_id,)
        )
        assert cst_after is None, "CST tree should be deleted after clearing"
        
        # Verify AST tree is deleted
        ast_after = test_db._fetchone(
            "SELECT id FROM ast_trees WHERE file_id = ?", (file_id,)
        )
        assert ast_after is None, "AST tree should be deleted after clearing"
        
        # Verify entities are deleted
        classes_after = test_db._fetchall(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(classes_after) == 0, "Classes should be deleted after clearing"
        
        functions_after = test_db._fetchall(
            "SELECT id FROM functions WHERE file_id = ?", (file_id,)
        )
        assert len(functions_after) == 0, "Functions should be deleted after clearing"


class TestUpdateFileData:
    """Tests for update_file_data method."""

    def test_update_file_data_success(
        self, test_db, test_file, test_project, temp_dir
    ):
        """Test successful file data update."""
        file_id, file_path, project_id = test_file
        
        # Update file content
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
        
        # Use absolute path for update_file_data
        abs_path = str(file_path.resolve())
        
        # Update file data
        result = test_db.update_file_data(
            file_path=abs_path,
            project_id=project_id,
            root_dir=temp_dir,
        )
        
        assert result.get("success") is True, "Update should succeed"
        assert result.get("file_id") == file_id, "File ID should match"
        assert result.get("ast_updated") is True, "AST should be updated"
        assert result.get("cst_updated") is True, "CST should be updated"
        assert result.get("entities_updated") > 0, "Entities should be updated"
        
        # Verify new entities exist
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

    def test_update_file_data_file_not_found(
        self, test_db, test_project, temp_dir
    ):
        """Test update_file_data with file not in database."""
        result = test_db.update_file_data(
            file_path="nonexistent.py",
            project_id=test_project,
            root_dir=temp_dir,
        )
        
        assert result.get("success") is False, "Update should fail"
        assert "not found" in result.get("error", "").lower(), "Error should mention file not found"

    def test_update_file_data_syntax_error(
        self, test_db, test_file, test_project, temp_dir
    ):
        """Test update_file_data with syntax error in file."""
        file_id, file_path, project_id = test_file
        
        # Write invalid Python code
        invalid_content = "class Invalid:\n    def method(\n    pass"  # Missing closing paren
        file_path.write_text(invalid_content, encoding="utf-8")
        
        abs_path = str(file_path.resolve())
        
        # Update file data - should handle syntax error gracefully
        result = test_db.update_file_data(
            file_path=abs_path,
            project_id=project_id,
            root_dir=temp_dir,
        )
        
        # Should fail but not crash
        assert result.get("success") is False, "Update should fail on syntax error"
        assert "error" in result, "Result should contain error information"

    def test_update_file_data_clears_old_records(
        self, test_db, test_file, test_project, temp_dir
    ):
        """Test that update_file_data clears old records before creating new ones."""
        file_id, file_path, project_id = test_file
        
        # Verify old entities exist
        old_classes = test_db._fetchall(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(old_classes) > 0, "Old classes should exist"
        
        old_class_ids = [c["id"] for c in old_classes]
        
        # Update file with different content
        new_content = '''"""
New content.
"""

class NewClass:
    """New class."""
    pass
'''
        file_path.write_text(new_content, encoding="utf-8")
        
        abs_path = str(file_path.resolve())
        
        # Update file data
        result = test_db.update_file_data(
            file_path=abs_path,
            project_id=project_id,
            root_dir=temp_dir,
        )
        
        assert result.get("success") is True, "Update should succeed"
        
        # Verify old class IDs are gone
        for old_class_id in old_class_ids:
            old_class = test_db._fetchone(
                "SELECT id FROM classes WHERE id = ?", (old_class_id,)
            )
            assert old_class is None, f"Old class {old_class_id} should be deleted"
        
        # Verify new class exists
        new_classes = test_db._fetchall(
            "SELECT name FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(new_classes) == 1, "Should have one new class"
        assert new_classes[0]["name"] == "NewClass", "New class should be named NewClass"

    def test_update_file_data_creates_new_records(
        self, test_db, test_file, test_project, temp_dir
    ):
        """Test that update_file_data creates new records."""
        file_id, file_path, project_id = test_file
        
        # Update file content
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
        
        abs_path = str(file_path.resolve())
        
        # Update file data
        result = test_db.update_file_data(
            file_path=abs_path,
            project_id=project_id,
            root_dir=temp_dir,
        )
        
        assert result.get("success") is True, "Update should succeed"
        assert result.get("entities_updated") == 4, "Should have 2 classes + 2 functions"
        
        # Verify AST and CST are saved
        ast_record = test_db._fetchone(
            "SELECT id FROM ast_trees WHERE file_id = ?", (file_id,)
        )
        assert ast_record is not None, "AST tree should be saved"
        
        cst_record = test_db._fetchone(
            "SELECT id FROM cst_trees WHERE file_id = ?", (file_id,)
        )
        assert cst_record is not None, "CST tree should be saved"
        
        # Verify entities are created
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

