"""
Tests to verify that AST, CST, and chunks are created in database after file operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import uuid
import os
import time
from pathlib import Path
from code_analysis.core.database.base import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database file."""
    return tmp_path / "test.db"


@pytest.fixture
def test_db(temp_db_path):
    """Initialize a CodeDatabase instance with a temporary SQLite database."""
    driver_config = create_driver_config_for_worker(temp_db_path, driver_type="sqlite")
    db = CodeDatabase(driver_config=driver_config)
    yield db
    db.close()


@pytest.fixture
def test_project():
    """Generate a unique project ID."""
    return str(uuid.uuid4())


@pytest.fixture
def test_file_with_content(test_db, test_project, tmp_path):
    """
    Create a test file with classes and functions, add it to database via update_file_data.
    """
    # Create project first (required for foreign key constraint)
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (test_project, str(tmp_path), tmp_path.name),
    )
    test_db._commit()
    
    # Create test file with classes and functions
    test_file = tmp_path / "test_file.py"
    file_content = '''"""
File docstring.
"""

class MyClass:
    """Class docstring."""
    
    def __init__(self, value: int):
        """Init method docstring."""
        self.value = value
    
    def get_value(self) -> int:
        """Get value method docstring."""
        return self.value

def standalone_function(param: str) -> str:
    """Function docstring."""
    return param.upper()
'''
    test_file.write_text(file_content, encoding="utf-8")
    file_mtime = os.path.getmtime(test_file)
    lines = len(file_content.splitlines())
    
    # Add file to database
    file_id = test_db.add_file(
        path=str(test_file),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project,
    )
    
    # Use update_file_data to analyze file and create AST/CST
    result = test_db.update_file_data(
        file_path=str(test_file),
        project_id=test_project,
        root_dir=tmp_path,
    )
    
    assert result.get("success") is True, f"update_file_data should succeed: {result.get('error')}"
    
    return file_id, test_file, test_project, tmp_path


class TestASTCSTChunksVerification:
    """Test that AST, CST, and chunks are created after file operations."""
    
    def test_ast_created_after_update_file_data(
        self, test_db, test_file_with_content, test_project
    ):
        """Test that AST tree is created in database after update_file_data."""
        file_id, file_path, project_id, root_dir = test_file_with_content
        
        # Check AST tree exists
        ast_record = test_db._fetchone(
            "SELECT id, file_id, project_id FROM ast_trees WHERE file_id = ?",
            (file_id,)
        )
        assert ast_record is not None, "AST tree should be created after update_file_data"
        assert ast_record["file_id"] == file_id, "AST tree should be linked to correct file_id"
        assert ast_record["project_id"] == project_id, "AST tree should be linked to correct project_id"
        
        # Check AST JSON is not empty
        ast_json = test_db._fetchone(
            "SELECT ast_json FROM ast_trees WHERE file_id = ?",
            (file_id,)
        )
        assert ast_json is not None, "AST JSON should exist"
        assert len(ast_json["ast_json"]) > 0, "AST JSON should not be empty"
    
    def test_cst_created_after_update_file_data(
        self, test_db, test_file_with_content, test_project
    ):
        """Test that CST tree is created in database after update_file_data."""
        file_id, file_path, project_id, root_dir = test_file_with_content
        
        # Check CST tree exists
        cst_record = test_db._fetchone(
            "SELECT id, file_id, project_id FROM cst_trees WHERE file_id = ?",
            (file_id,)
        )
        assert cst_record is not None, "CST tree should be created after update_file_data"
        assert cst_record["file_id"] == file_id, "CST tree should be linked to correct file_id"
        assert cst_record["project_id"] == project_id, "CST tree should be linked to correct project_id"
        
        # Check CST code matches file content
        cst_code = test_db._fetchone(
            "SELECT cst_code FROM cst_trees WHERE file_id = ?",
            (file_id,)
        )
        assert cst_code is not None, "CST code should exist"
        assert len(cst_code["cst_code"]) > 0, "CST code should not be empty"
        
        # Verify CST code matches file content
        file_content = file_path.read_text(encoding="utf-8")
        assert cst_code["cst_code"] == file_content, "CST code should match file content"
    
    def test_entities_created_after_update_file_data(
        self, test_db, test_file_with_content, test_project
    ):
        """Test that code entities (classes, functions, methods) are created after update_file_data."""
        file_id, file_path, project_id, root_dir = test_file_with_content
        
        # Check classes exist
        classes = test_db._fetchall(
            "SELECT id, name FROM classes WHERE file_id = ?",
            (file_id,)
        )
        assert len(classes) > 0, "Classes should be created after update_file_data"
        class_names = [c["name"] for c in classes]
        assert "MyClass" in class_names, "MyClass should be created"
        
        # Check methods exist
        class_ids = [c["id"] for c in classes]
        methods = test_db._fetchall(
            "SELECT id, name FROM methods WHERE class_id IN ({})".format(
                ",".join("?" * len(class_ids))
            ),
            tuple(class_ids),
        )
        assert len(methods) > 0, "Methods should be created after update_file_data"
        method_names = [m["name"] for m in methods]
        assert "__init__" in method_names, "__init__ method should be created"
        assert "get_value" in method_names, "get_value method should be created"
        
        # Check functions exist
        functions = test_db._fetchall(
            "SELECT id, name FROM functions WHERE file_id = ?",
            (file_id,)
        )
        assert len(functions) > 0, "Functions should be created after update_file_data"
        function_names = [f["name"] for f in functions]
        assert "standalone_function" in function_names, "standalone_function should be created"
    
    def test_file_marked_for_chunking_after_update_file_data(
        self, test_db, test_file_with_content, test_project
    ):
        """Test that file is marked for chunking after update_file_data."""
        file_id, file_path, project_id, root_dir = test_file_with_content
        
        # mark_file_needs_chunking is called in _analyze_file (line 499)
        # It deletes existing chunks so worker can re-chunk the file
        # We verify that chunks are deleted (file is ready for re-chunking)
        
        # Check that no chunks exist for this file (they were deleted by mark_file_needs_chunking)
        chunks = test_db._fetchall(
            "SELECT id FROM code_chunks WHERE file_id = ?",
            (file_id,)
        )
        assert len(chunks) == 0, "Chunks should be deleted by mark_file_needs_chunking, file is ready for re-chunking"
        
        # Verify file exists and was updated
        file_record = test_db.get_file_by_path(str(file_path), project_id)
        assert file_record is not None, "File should exist in database"
        assert file_record["id"] == file_id, "File ID should match"
        
        # File should be eligible for chunking (has docstring, no chunks)
        # This is what get_files_needing_chunking checks
        files_needing_chunking = test_db.get_files_needing_chunking(project_id, limit=10)
        file_paths_needing_chunking = [f["path"] for f in files_needing_chunking]
        assert str(file_path) in file_paths_needing_chunking, "File should be marked for chunking"
    
    def test_ast_cst_updated_after_file_modification(
        self, test_db, test_file_with_content, test_project
    ):
        """Test that AST and CST are updated after file modification."""
        file_id, file_path, project_id, root_dir = test_file_with_content
        
        # Get initial AST hash
        initial_ast = test_db._fetchone(
            "SELECT ast_hash FROM ast_trees WHERE file_id = ?",
            (file_id,)
        )
        assert initial_ast is not None, "Initial AST should exist"
        initial_ast_hash = initial_ast["ast_hash"]
        
        # Get initial CST hash
        initial_cst = test_db._fetchone(
            "SELECT cst_hash FROM cst_trees WHERE file_id = ?",
            (file_id,)
        )
        assert initial_cst is not None, "Initial CST should exist"
        initial_cst_hash = initial_cst["cst_hash"]
        
        # Modify file
        new_content = '''"""
Modified file docstring.
"""

class MyClass:
    """Modified class docstring."""
    
    def __init__(self, value: int):
        """Modified init method docstring."""
        self.value = value
        self.new_field = "new"

def new_function() -> str:
    """New function docstring."""
    return "new"
'''
        file_path.write_text(new_content, encoding="utf-8")
        time.sleep(0.1)  # Ensure mtime changes
        
        # Update file data
        result = test_db.update_file_data(
            file_path=str(file_path),
            project_id=project_id,
            root_dir=root_dir,
        )
        assert result.get("success") is True, f"Update should succeed: {result.get('error')}"
        
        # Check AST was updated
        updated_ast = test_db._fetchone(
            "SELECT ast_hash FROM ast_trees WHERE file_id = ? ORDER BY updated_at DESC LIMIT 1",
            (file_id,)
        )
        assert updated_ast is not None, "Updated AST should exist"
        assert updated_ast["ast_hash"] != initial_ast_hash, "AST hash should change after modification"
        
        # Check CST was updated
        updated_cst = test_db._fetchone(
            "SELECT cst_hash FROM cst_trees WHERE file_id = ? ORDER BY updated_at DESC LIMIT 1",
            (file_id,)
        )
        assert updated_cst is not None, "Updated CST should exist"
        assert updated_cst["cst_hash"] != initial_cst_hash, "CST hash should change after modification"
        
        # Verify CST code matches new file content
        cst_code = test_db._fetchone(
            "SELECT cst_code FROM cst_trees WHERE file_id = ? ORDER BY updated_at DESC LIMIT 1",
            (file_id,)
        )
        assert cst_code["cst_code"] == new_content, "CST code should match new file content"
        
        # Verify new function was created
        functions = test_db._fetchall(
            "SELECT name FROM functions WHERE file_id = ?",
            (file_id,)
        )
        function_names = [f["name"] for f in functions]
        assert "new_function" in function_names, "New function should be created"
        # Old function should be removed (standalone_function)
        assert "standalone_function" not in function_names, "Old function should be removed"
        
        # Verify chunks were deleted (file is ready for re-chunking)
        chunks = test_db._fetchall(
            "SELECT id FROM code_chunks WHERE file_id = ?",
            (file_id,)
        )
        assert len(chunks) == 0, "Old chunks should be deleted after file modification"
    
    def test_chunks_structure_after_creation(
        self, test_db, test_file_with_content, test_project
    ):
        """Test that chunks can be created and have correct structure for FAISS."""
        file_id, file_path, project_id, root_dir = test_file_with_content
        
        # Simulate chunk creation (normally done by DocstringChunker)
        # Create a test chunk manually to verify structure
        import uuid as uuid_lib
        chunk_uuid = str(uuid_lib.uuid5(uuid_lib.NAMESPACE_URL, f"{file_id}-test-chunk"))
        
        # Add chunk without vector_id (will be set by vectorization worker)
        # Use direct SQL since add_code_chunk is async
        test_db._execute(
            """
            INSERT INTO code_chunks
            (file_id, project_id, chunk_uuid, chunk_type, chunk_text,
             chunk_ordinal, vector_id, embedding_model, embedding_vector,
             class_id, function_id, method_id, line, ast_node_type, source_type, binding_level,
             updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))
            """,
            (
                file_id, project_id, chunk_uuid, "DocBlock", "Test chunk text",
                0, None, None, None,
                None, None, None, 1, "Module", "file_docstring", 0,
            ),
        )
        test_db._commit()
        chunk_id = test_db._lastrowid()
        
        assert chunk_id is not None, "Chunk should be created"
        
        # Verify chunk structure
        chunk = test_db._fetchone(
            "SELECT * FROM code_chunks WHERE id = ?",
            (chunk_id,)
        )
        assert chunk is not None, "Chunk should exist in database"
        assert chunk["file_id"] == file_id, "Chunk should be linked to file"
        assert chunk["project_id"] == project_id, "Chunk should be linked to project"
        assert chunk["chunk_uuid"] == chunk_uuid, "Chunk UUID should match"
        assert chunk["chunk_type"] == "DocBlock", "Chunk type should be DocBlock"
        assert chunk["vector_id"] is None, "vector_id should be NULL until vectorized"
        assert chunk["embedding_model"] is None, "embedding_model should be NULL until vectorized"
        assert chunk["embedding_vector"] is None, "embedding_vector should be NULL until vectorized"
        
        # Now simulate vectorization: add embedding_vector and vector_id
        import json
        test_embedding = [0.1] * 384  # Simulate 384-dim embedding
        embedding_vector_json = json.dumps(test_embedding)
        test_vector_id = 0  # FAISS index position
        
        # Update chunk with embedding and vector_id
        test_db._execute(
            """
            UPDATE code_chunks 
            SET embedding_vector = ?, vector_id = ?, embedding_model = ?
            WHERE id = ?
            """,
            (embedding_vector_json, test_vector_id, "test-model", chunk_id),
        )
        test_db._commit()
        
        # Verify chunk was updated
        updated_chunk = test_db._fetchone(
            "SELECT * FROM code_chunks WHERE id = ?",
            (chunk_id,)
        )
        assert updated_chunk["vector_id"] == test_vector_id, "vector_id should be set after vectorization"
        assert updated_chunk["embedding_model"] == "test-model", "embedding_model should be set after vectorization"
        assert updated_chunk["embedding_vector"] == embedding_vector_json, "embedding_vector should be set after vectorization"
        
        # Verify embedding_vector can be parsed as JSON
        embedding_parsed = json.loads(updated_chunk["embedding_vector"])
        assert len(embedding_parsed) == 384, "Embedding should have correct dimension"
        assert embedding_parsed[0] == 0.1, "Embedding values should match"
    
    def test_full_cycle_add_and_modify_file(
        self, test_db, test_project, tmp_path
    ):
        """Test full cycle: add file → verify AST/CST/chunks → modify file → verify updates."""
        # Create project
        test_db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (test_project, str(tmp_path), tmp_path.name),
        )
        test_db._commit()
        
        # Step 1: Create and add file
        test_file = tmp_path / "full_cycle_test.py"
        initial_content = '''"""
Initial file docstring.
"""

class InitialClass:
    """Initial class docstring."""
    pass

def initial_function():
    """Initial function docstring."""
    pass
'''
        test_file.write_text(initial_content, encoding="utf-8")
        file_mtime = os.path.getmtime(test_file)
        lines = len(initial_content.splitlines())
        
        file_id = test_db.add_file(
            path=str(test_file),
            lines=lines,
            last_modified=file_mtime,
            has_docstring=True,
            project_id=test_project,
        )
        
        # Step 2: Update file data (analyze and create AST/CST)
        result = test_db.update_file_data(
            file_path=str(test_file),
            project_id=test_project,
            root_dir=tmp_path,
        )
        assert result.get("success") is True, f"Update should succeed: {result.get('error')}"
        assert result.get("ast_updated") is True, "AST should be updated"
        assert result.get("cst_updated") is True, "CST should be updated"
        assert result.get("entities_updated") > 0, "Entities should be updated"
        
        # Step 3: Verify AST exists
        ast_record = test_db._fetchone(
            "SELECT id, ast_hash FROM ast_trees WHERE file_id = ?",
            (file_id,)
        )
        assert ast_record is not None, "AST should exist after update_file_data"
        initial_ast_hash = ast_record["ast_hash"]
        
        # Step 4: Verify CST exists and matches file content
        cst_record = test_db._fetchone(
            "SELECT id, cst_hash, cst_code FROM cst_trees WHERE file_id = ?",
            (file_id,)
        )
        assert cst_record is not None, "CST should exist after update_file_data"
        assert cst_record["cst_code"] == initial_content, "CST should match file content"
        initial_cst_hash = cst_record["cst_hash"]
        
        # Step 5: Verify entities exist
        classes = test_db._fetchall("SELECT name FROM classes WHERE file_id = ?", (file_id,))
        assert len(classes) > 0, "Classes should exist"
        assert "InitialClass" in [c["name"] for c in classes], "InitialClass should exist"
        
        functions = test_db._fetchall("SELECT name FROM functions WHERE file_id = ?", (file_id,))
        assert len(functions) > 0, "Functions should exist"
        assert "initial_function" in [f["name"] for f in functions], "initial_function should exist"
        
        # Step 6: Verify chunks are deleted (file is ready for chunking)
        chunks = test_db._fetchall("SELECT id FROM code_chunks WHERE file_id = ?", (file_id,))
        assert len(chunks) == 0, "Chunks should be deleted, file ready for chunking"
        
        # Step 7: Modify file
        modified_content = '''"""
Modified file docstring.
"""

class ModifiedClass:
    """Modified class docstring."""
    def new_method(self):
        """New method docstring."""
        pass

def modified_function():
    """Modified function docstring."""
    pass

def new_function():
    """New function docstring."""
    pass
'''
        test_file.write_text(modified_content, encoding="utf-8")
        time.sleep(0.1)  # Ensure mtime changes
        
        # Step 8: Update file data again
        result2 = test_db.update_file_data(
            file_path=str(test_file),
            project_id=test_project,
            root_dir=tmp_path,
        )
        assert result2.get("success") is True, f"Second update should succeed: {result2.get('error')}"
        assert result2.get("ast_updated") is True, "AST should be updated after modification"
        assert result2.get("cst_updated") is True, "CST should be updated after modification"
        
        # Step 9: Verify AST was updated
        updated_ast = test_db._fetchone(
            "SELECT ast_hash FROM ast_trees WHERE file_id = ? ORDER BY updated_at DESC LIMIT 1",
            (file_id,)
        )
        assert updated_ast is not None, "Updated AST should exist"
        assert updated_ast["ast_hash"] != initial_ast_hash, "AST hash should change after modification"
        
        # Step 10: Verify CST was updated
        updated_cst = test_db._fetchone(
            "SELECT cst_hash, cst_code FROM cst_trees WHERE file_id = ? ORDER BY updated_at DESC LIMIT 1",
            (file_id,)
        )
        assert updated_cst is not None, "Updated CST should exist"
        assert updated_cst["cst_hash"] != initial_cst_hash, "CST hash should change after modification"
        assert updated_cst["cst_code"] == modified_content, "CST should match modified file content"
        
        # Step 11: Verify entities were updated
        updated_classes = test_db._fetchall("SELECT name FROM classes WHERE file_id = ?", (file_id,))
        class_names = [c["name"] for c in updated_classes]
        assert "ModifiedClass" in class_names, "ModifiedClass should exist"
        assert "InitialClass" not in class_names, "InitialClass should be removed"
        
        updated_functions = test_db._fetchall("SELECT name FROM functions WHERE file_id = ?", (file_id,))
        function_names = [f["name"] for f in updated_functions]
        assert "modified_function" in function_names, "modified_function should exist"
        assert "new_function" in function_names, "new_function should exist"
        assert "initial_function" not in function_names, "initial_function should be removed"
        
        # Step 12: Verify chunks are deleted again (ready for re-chunking)
        chunks_after_modify = test_db._fetchall("SELECT id FROM code_chunks WHERE file_id = ?", (file_id,))
        assert len(chunks_after_modify) == 0, "Chunks should be deleted after modification, ready for re-chunking"
        
        # Step 13: Verify file is marked for chunking
        files_needing_chunking = test_db.get_files_needing_chunking(test_project, limit=10)
        file_paths = [f["path"] for f in files_needing_chunking]
        assert str(test_file) in file_paths, "File should be marked for chunking after modification"

