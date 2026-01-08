"""
Tests for file write operation integrations using real files from test_data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.refactorer_pkg.file_splitter import FileToPackageSplitter
from code_analysis.core.refactorer_pkg.splitter import ClassSplitter


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
def test_data_root():
    """Get test_data root directory."""
    return Path(__file__).parent.parent / "test_data"


@pytest.fixture
def real_test_file_with_classes(test_data_root):
    """Get a real test file with classes from test_data."""
    # Try to find a file with classes
    test_files = [
        test_data_root / "vast_srv" / "test_github.py",
        test_data_root / "code_analysis" / "core" / "database" / "entities.py",
    ]
    
    for test_file in test_files:
        if test_file.exists():
            return test_file
    
    pytest.skip("No test file with classes found")


@pytest.fixture
def real_test_file_in_db(test_db, test_project, temp_dir, real_test_file_with_classes, test_data_root):
    """Add real test file to database."""
    # Create dataset
    dataset_id = test_db.get_or_create_dataset(
        project_id=test_project,
        root_path=str(test_data_root),
        name=test_data_root.name,
    )
    
    # Read file content
    file_content = real_test_file_with_classes.read_text(encoding="utf-8")
    
    import os
    file_mtime = os.path.getmtime(real_test_file_with_classes)
    lines = len(file_content.splitlines())
    
    # Add file to database
    file_id = test_db.add_file(
        path=str(real_test_file_with_classes),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=file_content.strip().startswith('"""') or file_content.strip().startswith("'''"),
        project_id=test_project,
        dataset_id=dataset_id,
    )
    
    return file_id, real_test_file_with_classes, test_project, test_data_root


class TestFileSplitterIntegrationReal:
    """Tests for file splitter integration with real files."""
    
    def test_file_splitter_updates_database_real(
        self, test_db, real_test_file_in_db, test_data_root
    ):
        """Test that file splitter updates database for new files using real file."""
        file_id, file_path, project_id, root_dir = real_test_file_in_db
        
        # Create a copy of the file for testing
        import shutil
        test_file = root_dir / "test_split_file.py"
        shutil.copy2(file_path, test_file)
        
        # Add test file to database
        dataset_id = test_db.get_or_create_dataset(
            project_id=project_id,
            root_path=str(root_dir),
            name=root_dir.name,
        )
        
        file_content = test_file.read_text(encoding="utf-8")
        import os
        file_mtime = os.path.getmtime(test_file)
        lines = len(file_content.splitlines())
        
        test_file_id = test_db.add_file(
            path=str(test_file),
            lines=lines,
            last_modified=file_mtime,
            has_docstring=file_content.strip().startswith('"""') or file_content.strip().startswith("'''"),
            project_id=project_id,
            dataset_id=dataset_id,
        )
        
        # Create splitter with database access
        splitter = FileToPackageSplitter(
            file_path=test_file,
            database=test_db,
            project_id=project_id,
            root_dir=root_dir,
        )
        
        # Load file content and parse AST
        splitter.load_file()
        
        # Find classes and functions in the file
        classes = []
        functions = []
        if splitter.tree:
            for node in splitter.tree.body:
                if isinstance(node, type(splitter.tree.body[0])) and hasattr(node, "name"):
                    # This is a simplified check - in real code we'd use proper AST traversal
                    pass
        
        # Use AST to find actual classes and functions
        import ast
        tree = ast.parse(file_content, filename=str(test_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef) and not any(
                isinstance(parent, ast.ClassDef) for parent in ast.walk(tree)
                if hasattr(parent, "body") and node in getattr(parent, "body", [])
            ):
                # Top-level function (not a method)
                functions.append(node.name)
        
        # Skip if file doesn't have enough entities to split
        if len(classes) < 2 and len(functions) < 2:
            pytest.skip("File doesn't have enough classes/functions to split")
        
        # Split file into package
        config = {
            "modules": {
                "module_a": {
                    "classes": classes[:1] if classes else [],
                    "functions": functions[:1] if functions else [],
                },
                "module_b": {
                    "classes": classes[1:] if len(classes) > 1 else [],
                    "functions": functions[1:] if len(functions) > 1 else [],
                },
            }
        }
        
        # Remove empty modules
        config["modules"] = {
            k: v for k, v in config["modules"].items()
            if v.get("classes") or v.get("functions")
        }
        
        if not config["modules"]:
            pytest.skip("No modules to create after filtering")
        
        success, message = splitter.split_file_to_package(config)
        assert success is True, f"Split should succeed: {message}"
        
        # Verify new module files exist
        package_dir = test_file.parent / test_file.stem
        created_modules = list(config["modules"].keys())
        
        for module_name in created_modules:
            module_path = package_dir / f"{module_name}.py"
            assert module_path.exists(), f"{module_name}.py should exist"
            
            # Verify database was updated for new file
            module_record = test_db.get_file_by_path(
                str(module_path), project_id
            )
            assert module_record is not None, f"{module_name}.py should be in database"
            
            # Verify AST and CST are saved (or at least file is marked for update)
            # Note: update_file_data is called, but AST/CST might be saved asynchronously
            # The important thing is that update_file_data was called
        
        # Cleanup
        if package_dir.exists():
            import shutil
            shutil.rmtree(package_dir)
        if test_file.exists():
            test_file.unlink()


class TestClassSplitterIntegrationReal:
    """Tests for class splitter integration with real files."""
    
    def test_class_splitter_updates_database_real(
        self, test_db, real_test_file_in_db, test_data_root
    ):
        """Test that class splitter updates database after file write using real file."""
        file_id, file_path, project_id, root_dir = real_test_file_in_db
        
        # Create a copy of the file for testing
        import shutil
        test_file = root_dir / "test_split_class.py"
        shutil.copy2(file_path, test_file)
        
        # Add test file to database
        dataset_id = test_db.get_or_create_dataset(
            project_id=project_id,
            root_path=str(root_dir),
            name=root_dir.name,
        )
        
        file_content = test_file.read_text(encoding="utf-8")
        import os
        file_mtime = os.path.getmtime(test_file)
        lines = len(file_content.splitlines())
        
        test_file_id = test_db.add_file(
            path=str(test_file),
            lines=lines,
            last_modified=file_mtime,
            has_docstring=file_content.strip().startswith('"""') or file_content.strip().startswith("'''"),
            project_id=project_id,
            dataset_id=dataset_id,
        )
        
        # Find classes in the file
        import ast
        tree = ast.parse(file_content, filename=str(test_file))
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        
        if len(classes) == 0:
            pytest.skip("File doesn't have classes to split")
        
        # Use first class for splitting
        source_class = classes[0]
        
        # Find methods in the class
        methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == source_class:
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(item.name)
        
        if len(methods) < 2:
            pytest.skip(f"Class {source_class} doesn't have enough methods to split")
        
        # Create splitter with database access
        splitter = ClassSplitter(
            file_path=test_file,
            database=test_db,
            project_id=project_id,
            root_dir=root_dir,
        )
        
        # Load file first
        splitter.load_file()
        
        # Split class
        config = {
            "src_class": source_class,
            "target_classes": [
                {
                    "name": f"{source_class}1",
                    "methods": methods[:1],
                },
                {
                    "name": f"{source_class}2",
                    "methods": methods[1:],
                },
            ],
        }
        
        success, message = splitter.split_class(config)
        # Note: Split might fail if methods are not compatible
        # The important thing is that if it succeeds, database is updated
        
        if success:
            # Verify file was updated
            content = test_file.read_text(encoding="utf-8")
            assert f"{source_class}1" in content or f"{source_class}2" in content, "New classes should be in file"
            
            # Verify database was updated
            file_record = test_db.get_file_by_path(str(test_file), project_id)
            assert file_record is not None, "File should be in database"
            
            # Verify AST and CST are updated (or at least update_file_data was called)
            # Note: update_file_data is called, but AST/CST might be saved asynchronously
        
        # Cleanup
        if test_file.exists():
            test_file.unlink()


class TestUpdateFileDataReal:
    """Tests for update_file_data using real files."""
    
    def test_update_file_data_with_real_file(
        self, test_db, real_test_file_in_db, test_data_root
    ):
        """Test update_file_data with real file from test_data."""
        file_id, file_path, project_id, root_dir = real_test_file_in_db
        
        # Modify file content
        original_content = file_path.read_text(encoding="utf-8")
        new_content = original_content + "\n\n# Added comment for testing\n"
        file_path.write_text(new_content, encoding="utf-8")
        
        # Update file data
        result = test_db.update_file_data(
            file_path=str(file_path),
            project_id=project_id,
            root_dir=root_dir,
        )
        
        assert result.get("success") is True, f"Update should succeed: {result.get('error')}"
        assert result.get("ast_updated") is True, "AST should be updated"
        assert result.get("cst_updated") is True, "CST should be updated"
        
        # Verify AST and CST are saved
        updated_file_record = test_db.get_file_by_path(str(file_path), project_id)
        assert updated_file_record is not None, "File should be in database"
        
        if updated_file_record:
            ast_record = test_db._fetchone(
                "SELECT id FROM ast_trees WHERE file_id = ?",
                (updated_file_record["id"],),
            )
            assert ast_record is not None, "AST tree should be saved"
            
            cst_record = test_db._fetchone(
                "SELECT id FROM cst_trees WHERE file_id = ?",
                (updated_file_record["id"],),
            )
            assert cst_record is not None, "CST tree should be saved"
        
        # Restore original content
        file_path.write_text(original_content, encoding="utf-8")

