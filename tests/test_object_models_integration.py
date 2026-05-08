"""
Integration tests for object models with real data from test_data/.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from pathlib import Path
from typing import Any

import pytest

from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from tests.sqlite_legacy_schema_bootstrap import bootstrap_sqlite_schema_paths

from code_analysis.core.database_client.objects import (
    ASTNode,
    Class,
    CodeChunk,
    File,
    Function,
    Import,
    Method,
    db_row_to_object,
    db_rows_to_objects,
    object_from_table,
    objects_from_table,
)

# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


def _fetchall(client: DatabaseClient, sql: str, params: tuple = ()) -> list:
    r = client.execute(sql, params)
    return r.get("data") or []


class TestObjectModelsRealData:
    """Test object models with real data from test_data/."""

    @pytest.fixture
    def test_db(self, tmp_path):
        """Create test database with real data."""
        driver_config = create_driver_config_for_worker(
            tmp_path / "test_objects.db",
            driver_type="sqlite",
            backup_dir=tmp_path / "backups",
        )
        path_str, backup_dir = bootstrap_sqlite_schema_paths(
            driver_config,
            default_backup_dir=str(tmp_path / "backups"),
        )
        driver = create_driver(
            "sqlite",
            {"path": path_str, "backup_dir": backup_dir},
        )
        rpc = InProcessRpcClient(RPCHandlers(driver))
        db = DatabaseClient(rpc_client=rpc, driver_type="sqlite")
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
                            chk = db.execute(
                                "SELECT id FROM projects WHERE id = ?",
                                (project_id,),
                            )
                            prow = chk.get("data") or []
                            if not prow:
                                db.execute(
                                    "INSERT INTO projects (id, root_path, name, updated_at) "
                                    "VALUES (?, ?, ?, julianday('now'))",
                                    (
                                        project_id,
                                        str(project_dir.absolute()),
                                        project_dir.name,
                                    ),
                                )
                    except Exception:
                        pass

        try:
            yield db
        finally:
            db.disconnect()
            driver.disconnect()

    def _check_test_data_available(self):
        """Check if test data is available."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")
        if not VAST_SRV_DIR.exists() and not BHLFF_DIR.exists():
            pytest.skip("No test projects found in test_data/")

    def test_project_from_real_database(self, test_db):
        """Test Project object with real projects from database."""
        self._check_test_data_available()

        projects = test_db.list_projects()
        if not projects:
            pytest.skip("No projects found in test database")

        assert len(projects) > 0
        for project in projects:
            assert isinstance(project, Project)
            assert project.id
            assert project.root_path
            assert Path(project.root_path).exists()

    def test_project_to_db_row_and_back(self, test_db):
        """Test Project object conversion to/from database row."""
        self._check_test_data_available()

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        for proj_obj in projects_list:
            # Create object from database row shape
            row = proj_obj.to_db_row()
            project = Project.from_db_row(dict(row))

            # Convert back to database row
            row2 = project.to_db_row()

            # Verify essential fields
            assert row2["id"] == project.id
            assert row2["root_path"] == project.root_path

    def test_file_from_real_database(self, test_db):
        """Test File object with real files from database."""
        self._check_test_data_available()

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        # Get files for first project
        project_id = projects_list[0].id
        files_data = _fetchall(
            test_db,
            "SELECT * FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )

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

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        project_id = projects_list[0].id
        files_data = _fetchall(
            test_db,
            "SELECT * FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )

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

    def test_class_from_real_database(self, test_db):
        """Test Class object with real classes from database."""
        self._check_test_data_available()

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        project_id = projects_list[0].id
        files_data = _fetchall(
            test_db,
            "SELECT * FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )[:10]

        if not files_data:
            pytest.skip("No files found for test project")

        # Get classes for first file
        file_id = files_data[0]["id"]
        classes_data = _fetchall(
            test_db, "SELECT * FROM classes WHERE file_id = ?", (file_id,)
        )

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

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        project_id = projects_list[0].id
        files_data = _fetchall(
            test_db,
            "SELECT * FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )[:10]

        if not files_data:
            pytest.skip("No files found for test project")

        # Get functions for first file
        file_id = files_data[0]["id"]
        functions_data = _fetchall(
            test_db, "SELECT * FROM functions WHERE file_id = ?", (file_id,)
        )

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

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        project_id = projects_list[0].id
        files_data = _fetchall(
            test_db,
            "SELECT * FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )[:10]

        if not files_data:
            pytest.skip("No files found for test project")

        # Get classes first
        file_id = files_data[0]["id"]
        classes_data = _fetchall(
            test_db, "SELECT * FROM classes WHERE file_id = ?", (file_id,)
        )

        if classes_data:
            # Get methods for first class
            class_id = classes_data[0]["id"]
            methods_data = _fetchall(
                test_db,
                "SELECT * FROM methods WHERE class_id = ?",
                (class_id,),
            )

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

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        project_id = projects_list[0].id
        files_data = _fetchall(
            test_db,
            "SELECT * FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )[:10]

        if not files_data:
            pytest.skip("No files found for test project")

        # Get imports for first file
        file_id = files_data[0]["id"]
        imports_data = _fetchall(
            test_db, "SELECT * FROM imports WHERE file_id = ?", (file_id,)
        )

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

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        project_id = projects_list[0].id
        files_data = _fetchall(
            test_db,
            "SELECT * FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )[:10]

        if not files_data:
            pytest.skip("No files found for test project")

        # Get AST trees for first file
        file_id = files_data[0]["id"]
        ast_trees = _fetchall(
            test_db, "SELECT * FROM ast_trees WHERE file_id = ?", (file_id,)
        )

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

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        project_id = projects_list[0].id
        chunks_data = _fetchall(
            test_db,
            "SELECT * FROM code_chunks WHERE project_id = ? LIMIT ?",
            (project_id, 10),
        )

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

        projects_data = test_db.select("projects")
        if not projects_data:
            pytest.skip("No projects found in test database")

        # Test db_row_to_object
        row_obj = db_row_to_object(projects_data[0], Project)
        assert isinstance(row_obj, Project)
        assert row_obj.id == projects_data[0]["id"]

        # Test db_rows_to_objects
        rows_objs = db_rows_to_objects(projects_data, Project)
        assert len(rows_objs) == len(projects_data)
        assert all(isinstance(p, Project) for p in rows_objs)

        # Test object_from_table
        tbl_obj = object_from_table(projects_data[0], "projects")
        assert isinstance(tbl_obj, Project)

        # Test objects_from_table
        tbl_objs = objects_from_table(projects_data, "projects")
        assert len(tbl_objs) == len(projects_data)
        assert all(isinstance(p, Project) for p in tbl_objs)

    def test_object_serialization_with_real_data(self, test_db):
        """Test object serialization/deserialization with real data."""
        self._check_test_data_available()

        projects_data = test_db.select("projects")
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

        projects_list = test_db.list_projects()
        if not projects_list:
            pytest.skip("No projects found in test database")

        project_id = projects_list[0].id
        files_data = _fetchall(
            test_db,
            "SELECT * FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (project_id,),
        )[:5]

        if not files_data:
            pytest.skip("No files found for test project")

        file_id = files_data[0]["id"]

        # Test all object types that might exist
        test_cases = [
            (
                "classes",
                Class,
                lambda: _fetchall(
                    test_db, "SELECT * FROM classes WHERE file_id = ?", (file_id,)
                ),
            ),
            (
                "functions",
                Function,
                lambda: _fetchall(
                    test_db, "SELECT * FROM functions WHERE file_id = ?", (file_id,)
                ),
            ),
            (
                "imports",
                Import,
                lambda: _fetchall(
                    test_db, "SELECT * FROM imports WHERE file_id = ?", (file_id,)
                ),
            ),
        ]

        for table_name, obj_class, get_data_func in test_cases:
            data = get_data_func()
            if data:
                cls: Any = obj_class
                obj = cls.from_db_row(data[0])
                assert isinstance(obj, obj_class)
                # Verify round-trip conversion
                row = obj.to_db_row()
                obj2 = cls.from_db_row(row)
                assert obj2.id == obj.id or (
                    obj2.file_id == obj.file_id and obj2.name == obj.name
                )
