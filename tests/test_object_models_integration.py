"""
Integration tests for object models with real data from test_data/.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from pathlib import Path

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database_client.objects import (
    ASTNode,
    Class,
    CodeChunk,
    Dataset,
    File,
    Function,
    Import,
    Method,
    Project,
    db_row_to_object,
    db_rows_to_objects,
    object_from_table,
    objects_from_table,
)

# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestObjectModelsRealData:
    """Test object models with real data from test_data/."""

    @pytest.fixture
    def test_db(self, tmp_path):
        """Create test database with real data."""
        db_path = tmp_path / "test_objects.db"
        db = CodeDatabase(str(db_path))
        db.connect()

        # Load real projects if available
        if TEST_DATA_DIR.exists():
            for project_dir in [VAST_SRV_DIR, BHLFF_DIR]:
                if project_dir.exists() and (project_dir / "projectid").exists():
                    try:
                        projectid_path = project_dir / "projectid"
                        with open(projectid_path, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            if content.startswith("{"):
                                project_data = json.loads(content)
                                project_id = project_data.get("id", "")
                            else:
                                project_id = content

                        if project_id:
                            db.create_project(
                                project_id=project_id,
                                root_path=str(project_dir.absolute()),
                                name=project_dir.name,
                            )
                    except Exception:
                        pass

        yield db
        db.disconnect()

    def _check_test_data_available(self):
        """Check if test data is available."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")
        if not VAST_SRV_DIR.exists() and not BHLFF_DIR.exists():
            pytest.skip("No test projects found in test_data/")

    def test_project_from_real_database(self, test_db):
        """Test Project object with real projects from database."""
        self._check_test_data_available()

        # Get projects from database
        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        # Convert to Project objects
        projects = [Project.from_db_row(proj) for proj in projects_data]

        assert len(projects) > 0
        for project in projects:
            assert isinstance(project, Project)
            assert project.id
            assert project.root_path
            assert Path(project.root_path).exists()

    def test_project_to_db_row_and_back(self, test_db):
        """Test Project object conversion to/from database row."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        for proj_data in projects_data:
            # Create object from database row
            project = Project.from_db_row(proj_data)

            # Convert back to database row
            row = project.to_db_row()

            # Verify essential fields
            assert row["id"] == project.id
            assert row["root_path"] == project.root_path

    def test_file_from_real_database(self, test_db):
        """Test File object with real files from database."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        # Get files for first project
        project_id = projects_data[0]["id"]
        files_data = test_db.get_files(project_id=project_id)

        if not files_data:
            pytest.skip("No files found for test project")

        # Convert to File objects
        files = [File.from_db_row(file_data) for file_data in files_data]

        assert len(files) > 0
        for file_obj in files:
            assert isinstance(file_obj, File)
            assert file_obj.project_id == project_id
            assert file_obj.path

    def test_file_to_db_row_and_back(self, test_db):
        """Test File object conversion to/from database row."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        files_data = test_db.get_files(project_id=project_id)

        if not files_data:
            pytest.skip("No files found for test project")

        for file_data in files_data:
            # Create object from database row
            file_obj = File.from_db_row(file_data)

            # Convert back to database row
            row = file_obj.to_db_row()

            # Verify essential fields
            assert row["project_id"] == file_obj.project_id
            assert row["path"] == file_obj.path

    def test_dataset_from_real_database(self, test_db):
        """Test Dataset object with real datasets from database."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        datasets_data = test_db.get_datasets(project_id=project_id)

        if datasets_data:
            # Convert to Dataset objects
            datasets = [Dataset.from_db_row(ds_data) for ds_data in datasets_data]

            for dataset in datasets:
                assert isinstance(dataset, Dataset)
                assert dataset.project_id == project_id

    def test_class_from_real_database(self, test_db):
        """Test Class object with real classes from database."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        files_data = test_db.get_files(project_id=project_id, limit=10)

        if not files_data:
            pytest.skip("No files found for test project")

        # Get classes for first file
        file_id = files_data[0]["id"]
        classes_data = test_db.get_classes(file_id=file_id)

        if classes_data:
            # Convert to Class objects
            classes = [Class.from_db_row(cls_data) for cls_data in classes_data]

            for cls in classes:
                assert isinstance(cls, Class)
                assert cls.file_id == file_id
                assert cls.name

    def test_function_from_real_database(self, test_db):
        """Test Function object with real functions from database."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        files_data = test_db.get_files(project_id=project_id, limit=10)

        if not files_data:
            pytest.skip("No files found for test project")

        # Get functions for first file
        file_id = files_data[0]["id"]
        functions_data = test_db.get_functions(file_id=file_id)

        if functions_data:
            # Convert to Function objects
            functions = [
                Function.from_db_row(func_data) for func_data in functions_data
            ]

            for func in functions:
                assert isinstance(func, Function)
                assert func.file_id == file_id
                assert func.name

    def test_method_from_real_database(self, test_db):
        """Test Method object with real methods from database."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        files_data = test_db.get_files(project_id=project_id, limit=10)

        if not files_data:
            pytest.skip("No files found for test project")

        # Get classes first
        file_id = files_data[0]["id"]
        classes_data = test_db.get_classes(file_id=file_id)

        if classes_data:
            # Get methods for first class
            class_id = classes_data[0]["id"]
            methods_data = test_db.get_methods(class_id=class_id)

            if methods_data:
                # Convert to Method objects
                methods = [Method.from_db_row(meth_data) for meth_data in methods_data]

                for method in methods:
                    assert isinstance(method, Method)
                    assert method.class_id == class_id
                    assert method.name

    def test_import_from_real_database(self, test_db):
        """Test Import object with real imports from database."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        files_data = test_db.get_files(project_id=project_id, limit=10)

        if not files_data:
            pytest.skip("No files found for test project")

        # Get imports for first file
        file_id = files_data[0]["id"]
        imports_data = test_db.get_imports(file_id=file_id)

        if imports_data:
            # Convert to Import objects
            imports = [Import.from_db_row(imp_data) for imp_data in imports_data]

            for imp in imports:
                assert isinstance(imp, Import)
                assert imp.file_id == file_id
                assert imp.name

    def test_ast_node_from_real_database(self, test_db):
        """Test ASTNode object with real AST trees from database."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        files_data = test_db.get_files(project_id=project_id, limit=10)

        if not files_data:
            pytest.skip("No files found for test project")

        # Get AST trees for first file
        file_id = files_data[0]["id"]
        ast_trees = test_db.get_ast_trees(file_id=file_id)

        if ast_trees:
            # Convert to ASTNode objects
            ast_nodes = [ASTNode.from_db_row(ast_data) for ast_data in ast_trees]

            for node in ast_nodes:
                assert isinstance(node, ASTNode)
                assert node.file_id == file_id
                assert node.ast_json
                assert node.ast_hash

    def test_code_chunk_from_real_database(self, test_db):
        """Test CodeChunk object with real code chunks from database."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        chunks_data = test_db.get_chunks(project_id=project_id, limit=10)

        if chunks_data:
            # Convert to CodeChunk objects
            chunks = [CodeChunk.from_db_row(chunk_data) for chunk_data in chunks_data]

            for chunk in chunks:
                assert isinstance(chunk, CodeChunk)
                assert chunk.project_id == project_id
                assert chunk.chunk_uuid
                assert chunk.chunk_text

    def test_mapper_functions_with_real_data(self, test_db):
        """Test mapper functions with real database data."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        # Test db_row_to_object
        project = db_row_to_object(projects_data[0], Project)
        assert isinstance(project, Project)
        assert project.id == projects_data[0]["id"]

        # Test db_rows_to_objects
        projects = db_rows_to_objects(projects_data, Project)
        assert len(projects) == len(projects_data)
        assert all(isinstance(p, Project) for p in projects)

        # Test object_from_table
        project = object_from_table(projects_data[0], "projects")
        assert isinstance(project, Project)

        # Test objects_from_table
        projects = objects_from_table(projects_data, "projects")
        assert len(projects) == len(projects_data)
        assert all(isinstance(p, Project) for p in projects)

    def test_object_serialization_with_real_data(self, test_db):
        """Test object serialization/deserialization with real data."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        # Create object from real data
        project = Project.from_db_row(projects_data[0])

        # Serialize to JSON
        json_str = project.to_json()
        assert isinstance(json_str, str)

        # Deserialize from JSON
        project2 = Project.from_json(json_str)
        assert project2.id == project.id
        assert project2.root_path == project.root_path

    def test_all_object_types_with_real_data(self, test_db):
        """Test all object types can be created from real database data."""
        self._check_test_data_available()

        projects_data = test_db.get_projects()
        if not projects_data:
            pytest.skip("No projects found in test database")

        project_id = projects_data[0]["id"]
        files_data = test_db.get_files(project_id=project_id, limit=5)

        if not files_data:
            pytest.skip("No files found for test project")

        file_id = files_data[0]["id"]

        # Test all object types that might exist
        test_cases = [
            ("classes", Class, lambda: test_db.get_classes(file_id=file_id)),
            ("functions", Function, lambda: test_db.get_functions(file_id=file_id)),
            ("imports", Import, lambda: test_db.get_imports(file_id=file_id)),
        ]

        for table_name, obj_class, get_data_func in test_cases:
            data = get_data_func()
            if data:
                obj = obj_class.from_db_row(data[0])
                assert isinstance(obj, obj_class)
                # Verify round-trip conversion
                row = obj.to_db_row()
                obj2 = obj_class.from_db_row(row)
                assert obj2.id == obj.id or (
                    obj2.file_id == obj.file_id and obj2.name == obj.name
                )
