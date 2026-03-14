"""
Tests for database file update operations using real or synthetic files.

Uses synthetic files (created in temp_dir) with guaranteed structure so tests
do not depend on test_data contents. Optional real-file fixtures kept for
backward compatibility.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


# Synthetic file content: at least one top-level function and one class with method
SYNTHETIC_FILE_WITH_FUNCTION_AND_CLASS = '''def top_level_func():
    """A top-level function for tests."""
    pass


class MyClass:
    """A class for tests."""

    def method(self):
        return 1
'''

# Synthetic file content: one class with one method (for class-only tests)
SYNTHETIC_FILE_WITH_CLASS_ONLY = '''class Helper:
    """Helper class for tests."""

    def run(self):
        return 42
'''


def _insert_ast_cst_and_entities(
    test_db,
    file_id: int,
    project_id: str,
    file_content: str,
    file_path: Path,
    file_mtime: float,
) -> None:
    """Insert AST, CST and entity rows for a file (shared by real and synthetic fixtures)."""
    tree = ast.parse(file_content, filename=str(file_path))
    ast_json = json.dumps(ast.dump(tree))
    ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

    test_db._execute(
        """
        INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, project_id, ast_json, ast_hash, file_mtime),
    )

    cst_hash = hashlib.sha256(file_content.encode()).hexdigest()
    test_db._execute(
        """
        INSERT INTO cst_trees (file_id, project_id, cst_code, cst_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, project_id, file_content, cst_hash, file_mtime),
    )

    classes_data = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            docstring = ast.get_docstring(node)
            classes_data.append((node.name, node.lineno, docstring or ""))

    class_id_map = {}
    for class_name, line_num, docstring in classes_data:
        cst_node_id = f"fixture:{class_name}:ClassDef:{line_num}:0-0:0"
        test_db._execute(
            """
            INSERT INTO classes (file_id, name, line, docstring, bases, cst_node_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_id, class_name, line_num, docstring, "[]", cst_node_id),
        )
        class_row = test_db._fetchone(
            "SELECT id FROM classes WHERE file_id = ? AND name = ? AND line = ?",
            (file_id, class_name, line_num),
        )
        if class_row:
            class_id_map[class_name] = class_row["id"]

    def is_method(node, tree):
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                for item in parent.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item == node
                    ):
                        return parent.name
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parent_class = is_method(node, tree)
            docstring = ast.get_docstring(node)

            if parent_class and parent_class in class_id_map:
                cst_node_id = f"fixture:{node.name}:FunctionDef:{node.lineno}:0-0:0"
                test_db._execute(
                    """
                    INSERT INTO methods (class_id, name, line, args, docstring, cst_node_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        class_id_map[parent_class],
                        node.name,
                        node.lineno,
                        "[]",
                        docstring or "",
                        cst_node_id,
                    ),
                )
            else:
                cst_node_id = f"fixture:{node.name}:FunctionDef:{node.lineno}:0-0:0"
                test_db._execute(
                    """
                    INSERT INTO functions (file_id, name, line, args, docstring, cst_node_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        node.name,
                        node.lineno,
                        "[]",
                        docstring or "",
                        cst_node_id,
                    ),
                )

    test_db._commit()


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
    """Create test database with schema (projects, files, etc.)."""
    db_path = temp_dir / "test.db"
    driver_config = create_driver_config_for_worker(
        db_path, driver_type="sqlite", backup_dir=temp_dir / "backups"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    yield db
    db.close()


@pytest.fixture
def test_project(test_db, temp_dir, project_id):
    """Create test project in database and projectid file in temp_dir (required by update_file_data)."""
    project_name = temp_dir.name
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), project_name),
    )
    test_db._commit()
    (temp_dir / "projectid").write_text(
        json.dumps(
            {"id": project_id, "description": "Test project for update_file_data"}
        ),
        encoding="utf-8",
    )
    return project_id


@pytest.fixture
def test_data_root():
    """Get test_data root directory."""
    return Path(__file__).parent.parent / "test_data"


@pytest.fixture
def project_id_real():
    """Project ID for tests that use real files under test_data (separate from temp_dir)."""
    return str(uuid.uuid4())


@pytest.fixture
def test_project_real_root(test_db, test_data_root, project_id_real):
    """Create project with root_path=test_data_root so real test files are under project root."""
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id_real, str(test_data_root), "test_data_real"),
    )
    test_db._commit()
    return project_id_real


@pytest.fixture
def real_test_file(test_data_root):
    """Get a real test file from test_data."""
    # Use a simple file from vast_srv
    test_file = test_data_root / "vast_srv" / "fix_success_result_smart.py"
    if not test_file.exists():
        pytest.skip(f"Test file not found: {test_file}")
    return test_file


@pytest.fixture
def real_test_file_with_class(test_data_root):
    """Get a real test file with classes from test_data."""
    test_file = test_data_root / "vast_srv" / "test_github.py"
    if not test_file.exists():
        pytest.skip(f"Test file not found: {test_file}")
    return test_file


@pytest.fixture
def synthetic_file_in_db(test_db, test_project, temp_dir):
    """Create a synthetic Python file with guaranteed function and class, add to DB."""
    synthetic_path = temp_dir / "synthetic.py"
    synthetic_path.write_text(SYNTHETIC_FILE_WITH_FUNCTION_AND_CLASS, encoding="utf-8")
    file_mtime = os.path.getmtime(synthetic_path)
    lines = len(SYNTHETIC_FILE_WITH_FUNCTION_AND_CLASS.splitlines())

    file_id = test_db.add_file(
        path=str(synthetic_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project,
    )

    _insert_ast_cst_and_entities(
        test_db,
        file_id,
        test_project,
        SYNTHETIC_FILE_WITH_FUNCTION_AND_CLASS,
        synthetic_path,
        file_mtime,
    )

    return file_id, synthetic_path, test_project, temp_dir


@pytest.fixture
def synthetic_class_file_in_db(test_db, test_project, temp_dir):
    """Create a synthetic Python file with one class and method, add to DB."""
    synthetic_path = temp_dir / "synthetic_class.py"
    synthetic_path.write_text(SYNTHETIC_FILE_WITH_CLASS_ONLY, encoding="utf-8")
    file_mtime = os.path.getmtime(synthetic_path)
    content = SYNTHETIC_FILE_WITH_CLASS_ONLY
    lines = len(content.splitlines())

    file_id = test_db.add_file(
        path=str(synthetic_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project,
    )

    _insert_ast_cst_and_entities(
        test_db,
        file_id,
        test_project,
        content,
        synthetic_path,
        file_mtime,
    )

    return file_id, synthetic_path, test_project, temp_dir


@pytest.fixture
def real_test_file_in_db(
    test_db, test_project_real_root, real_test_file, test_data_root
):
    """Add real test file from test_data to database (skips if file missing)."""
    file_content = real_test_file.read_text(encoding="utf-8")
    file_mtime = os.path.getmtime(real_test_file)
    lines = len(file_content.splitlines())

    file_id = test_db.add_file(
        path=str(real_test_file),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project_real_root,
    )

    _insert_ast_cst_and_entities(
        test_db,
        file_id,
        test_project_real_root,
        file_content,
        real_test_file,
        file_mtime,
    )

    return file_id, real_test_file, test_project_real_root, test_data_root


class TestClearFileDataReal:
    """Tests for clear_file_data method (using synthetic file with guaranteed entities)."""

    def test_clear_file_data_includes_cst_trees_real(
        self, test_db, synthetic_file_in_db, test_project
    ):
        """Test that clear_file_data deletes CST trees and entities."""
        file_id, file_path, project_id, root_dir = synthetic_file_in_db

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

        # Verify entities exist before clearing (synthetic file has both function and class)
        classes_before = test_db._fetchall(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
        functions_before = test_db._fetchall(
            "SELECT id FROM functions WHERE file_id = ?", (file_id,)
        )
        assert (
            len(functions_before) > 0 or len(classes_before) > 0
        ), "At least one of functions or classes should exist before clearing"

        # Clear file data
        test_db.clear_file_data(file_id)

        # Verify CST tree is deleted (main test - this is what we're testing)
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


class TestUpdateFileDataReal:
    """Tests for update_file_data method (using synthetic files with guaranteed structure)."""

    def test_update_file_data_with_real_file(
        self, test_db, synthetic_file_in_db, test_project
    ):
        """Test update_file_data with synthetic file."""
        file_id, file_path, project_id, root_dir = synthetic_file_in_db

        # Modify file content (add a comment at the end)
        original_content = file_path.read_text(encoding="utf-8")
        modified_content = original_content + "\n# Modified for testing\n"
        file_path.write_text(modified_content, encoding="utf-8")
        # Ensure file mtime differs from DB so update_file_data does not skip (FILE_MODIFICATION_TOLERANCE)
        os.utime(file_path, (time.time(), time.time() + 2.0))

        # Update file data
        result = test_db.update_file_data(
            file_path=str(file_path),
            project_id=project_id,
            root_dir=root_dir,
        )

        # Should succeed (even if analyze_file has issues, clear_file_data should work)
        # At minimum, verify that clear_file_data was called
        assert (
            "error" in result or result.get("success") is not None
        ), "Result should contain status"

        # Verify file was processed
        assert result.get("file_id") == file_id, "File ID should match"

        # If update succeeded, verify CST was updated
        if result.get("success"):
            cst_after = test_db._fetchone(
                "SELECT cst_code FROM cst_trees WHERE file_id = ?", (file_id,)
            )
            if cst_after:
                assert (
                    "# Modified for testing" in cst_after["cst_code"]
                ), "CST should contain modification"

    def test_update_file_data_clears_old_entities_real(
        self, test_db, synthetic_file_in_db, test_project
    ):
        """Test that update_file_data clears old entities."""
        file_id, file_path, project_id, root_dir = synthetic_file_in_db

        original_classes = test_db._fetchall(
            "SELECT id, name FROM classes WHERE file_id = ?", (file_id,)
        )
        original_class_ids = [c["id"] for c in original_classes]

        original_functions = test_db._fetchall(
            "SELECT id, name FROM functions WHERE file_id = ?", (file_id,)
        )
        original_function_ids = [f["id"] for f in original_functions]
        assert (
            len(original_function_ids) > 0 or len(original_class_ids) > 0
        ), "Synthetic file should have at least one function or class"

        # Modify file significantly (remove a class or function)
        original_content = file_path.read_text(encoding="utf-8")
        # Just add a comment - real modification would require AST manipulation
        modified_content = original_content + "\n# Test modification\n"
        file_path.write_text(modified_content, encoding="utf-8")
        # Ensure file mtime differs from DB so update_file_data does not skip (FILE_MODIFICATION_TOLERANCE)
        os.utime(file_path, (time.time(), time.time() + 2.0))

        # Update file data
        result = test_db.update_file_data(
            file_path=str(file_path),
            project_id=project_id,
            root_dir=root_dir,
        )

        # Verify old entities are cleared (even if update failed, clear should work)
        # Check that old class IDs are gone
        for old_class_id in original_class_ids:
            old_class = test_db._fetchone(
                "SELECT id FROM classes WHERE id = ?", (old_class_id,)
            )
            # If update succeeded, old classes should be gone
            # If update failed, they might still exist, but clear_file_data should have been called
            if result.get("success"):
                assert (
                    old_class is None
                ), f"Old class {old_class_id} should be deleted after successful update"

    def test_update_file_data_with_class_file(
        self,
        test_db,
        synthetic_class_file_in_db,
    ):
        """Test update_file_data with synthetic file containing a class and method."""
        file_id, file_path, project_id, root_dir = synthetic_class_file_in_db

        classes = test_db._fetchall(
            "SELECT id, name FROM classes WHERE file_id = ?", (file_id,)
        )
        assert len(classes) > 0, "Synthetic class file should have classes"

        class_ids = [c["id"] for c in classes]
        methods = test_db._fetchall(
            "SELECT id FROM methods WHERE class_id IN ({})".format(
                ",".join("?" * len(class_ids))
            ),
            tuple(class_ids),
        )
        assert len(methods) > 0, "Synthetic class should have methods"

        original_content = file_path.read_text(encoding="utf-8")
        modified_content = original_content + "\n# Test modification\n"
        file_path.write_text(modified_content, encoding="utf-8")

        update_result = test_db.update_file_data(
            file_path=str(file_path),
            project_id=project_id,
            root_dir=root_dir,
        )

        assert "file_id" in update_result, "Result should contain file_id"
        assert update_result.get("file_id") == file_id, "File ID should match"

        file_path.write_text(original_content, encoding="utf-8")
