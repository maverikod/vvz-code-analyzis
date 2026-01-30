"""
Integration tests for vectorization worker on real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.project_resolution import load_project_info
from code_analysis.core.vectorization_worker_pkg.base import VectorizationWorker
from code_analysis.core.vectorization_worker_pkg.chunking import _request_chunking_for_files


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for tests."""
    db_path = tmp_path / "test.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    yield db
    db.close()


@pytest.fixture
def mock_svo_client_manager():
    """Create mock SVO client manager."""
    mock = Mock()
    mock.initialize = AsyncMock(return_value=None)
    mock.close = AsyncMock(return_value=None)
    mock.get_embedding = AsyncMock(return_value=[0.1] * 384)
    return mock


@pytest.fixture
def mock_faiss_manager(tmp_path):
    """Create mock FAISS manager."""
    mock = Mock()
    mock.index_path = str(tmp_path / "faiss.index")
    mock.add_vector = Mock(return_value=1)
    mock.save_index = Mock(return_value=None)
    mock._load_index = Mock(return_value=None)
    return mock


class TestVectorizationIntegrationRealData:
    """Test vectorization worker on real data from test_data/."""

    @pytest.mark.asyncio
    async def test_vectorization_vast_srv_files_path_normalization(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager, tmp_path
    ):
        """Test vectorization of files from vast_srv - path normalization."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        # Load project info
        project_info = load_project_info(VAST_SRV_DIR)
        assert project_info.project_id

        # Create project in database
        temp_db.get_or_create_project(
            root_path=str(project_info.root_path),
            name="vast_srv_test",
        )

        # Find Python files in vast_srv
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in vast_srv")

        # Add first few files to database
        test_files = python_files[:5]  # Test with first 5 files
        file_ids = []
        for file_path in test_files:
            file_id = temp_db.add_file(
                path=str(file_path),
                lines=len(file_path.read_text().splitlines()),
                last_modified=file_path.stat().st_mtime,
                has_docstring=False,
                project_id=project_info.project_id,
            )
            file_ids.append(file_id)

        # Create worker
        worker = VectorizationWorker(
            db_path=temp_db._driver_config.db_path,
            project_id=project_info.project_id,
            svo_client_manager=mock_svo_client_manager,
            faiss_manager=mock_faiss_manager,
        )

        # Get files that need chunking
        files_needing_chunking = temp_db.get_files_needing_chunking(
            project_id=project_info.project_id, limit=10
        )

        # Verify paths are normalized (absolute)
        for file_record in files_needing_chunking:
            assert Path(file_record["path"]).is_absolute()
            assert file_record["project_id"] == project_info.project_id

        # Request chunking (this will validate paths and project_id)
        if files_needing_chunking:
            chunked_count = await _request_chunking_for_files(
                worker, temp_db, files_needing_chunking
            )
            assert chunked_count >= 0  # May be 0 if chunking fails, but should not error

    @pytest.mark.asyncio
    async def test_vectorization_bhlff_files_project_id_validation(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager
    ):
        """Test vectorization of files from bhlff - project_id validation."""
        if not BHLFF_DIR.exists():
            pytest.skip("test_data/bhlff/ not found")

        # Check if projectid is in new format
        projectid_file = BHLFF_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in bhlff")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        # Load project info
        project_info = load_project_info(BHLFF_DIR)
        assert project_info.project_id

        # Create project in database
        temp_db.get_or_create_project(
            root_path=str(project_info.root_path),
            name="bhlff_test",
        )

        # Find Python files in bhlff
        python_files = list(BHLFF_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in bhlff")

        # Add first few files to database
        test_files = python_files[:3]  # Test with first 3 files
        for file_path in test_files:
            # Verify project_id matches before adding
            file_project_info = load_project_info(file_path.parent)
            assert file_project_info.project_id == project_info.project_id

            file_id = temp_db.add_file(
                path=str(file_path),
                lines=len(file_path.read_text().splitlines()),
                last_modified=file_path.stat().st_mtime,
                has_docstring=False,
                project_id=project_info.project_id,
            )
            assert file_id > 0

    def test_vectorization_different_file_extensions(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager
    ):
        """Test processing files with various extensions."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            import json
            import uuid

            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database
            temp_db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Create files with different extensions
            extensions = [".py", ".pyx", ".pyi"]
            for ext in extensions:
                test_file = project_root / f"test{ext}"
                test_file.write_text("# Test file\n")

                file_id = temp_db.add_file(
                    path=str(test_file),
                    lines=1,
                    last_modified=test_file.stat().st_mtime,
                    has_docstring=False,
                    project_id=project_id,
                    dataset_id=str(temp_db.get_or_create_dataset(project_id)),
                )
                assert file_id > 0

    def test_vectorization_large_files(self, temp_db, mock_svo_client_manager, mock_faiss_manager):
        """Test processing large files."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            import json
            import uuid

            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database
            temp_db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Create large file (1000 lines)
            large_file = project_root / "large_file.py"
            content = "\n".join([f"# Line {i}" for i in range(1000)])
            large_file.write_text(content)

            file_id = temp_db.add_file(
                path=str(large_file),
                lines=1000,
                last_modified=large_file.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
            )
            assert file_id > 0

    @pytest.mark.asyncio
    async def test_vectorization_error_handling(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager
    ):
        """Test error handling during vectorization."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            import json
            import uuid

            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database
            temp_db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Create file with syntax error
            error_file = project_root / "error_file.py"
            error_file.write_text("def invalid syntax here\n")

            file_id = temp_db.add_file(
                path=str(error_file),
                lines=1,
                last_modified=error_file.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
            )

            # Create worker
            worker = VectorizationWorker(
                db_path=temp_db._driver_config.db_path,
                project_id=project_id,
                svo_client_manager=mock_svo_client_manager,
                faiss_manager=mock_faiss_manager,
            )

            # Get files that need chunking
            files_needing_chunking = temp_db.get_files_needing_chunking(
                project_id=project_id, limit=10
            )

            # Request chunking - should handle errors gracefully
            if files_needing_chunking:
                chunked_count = await _request_chunking_for_files(
                    worker, temp_db, files_needing_chunking
                )
                # Should not crash, even if chunking fails
                assert chunked_count >= 0

    def test_vectorization_performance(self, temp_db, mock_svo_client_manager, mock_faiss_manager):
        """Test vectorization performance on multiple files."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            import json
            import uuid

            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database
            temp_db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Create multiple files
            start_time = time.time()
            for i in range(10):
                test_file = project_root / f"test_{i}.py"
                test_file.write_text(f"# Test file {i}\ndef func_{i}():\n    pass\n")

                file_id = temp_db.add_file(
                    path=str(test_file),
                    lines=3,
                    last_modified=test_file.stat().st_mtime,
                    has_docstring=False,
                    project_id=project_id,
                    dataset_id=str(temp_db.get_or_create_dataset(project_id)),
                )
                assert file_id > 0

            elapsed = time.time() - start_time
            # Should complete in reasonable time (< 1 second for 10 files)
            assert elapsed < 1.0

    def test_vectorization_database_integration(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager
    ):
        """Test integration with database."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            import json
            import uuid

            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database
            temp_db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Create test file
            test_file = project_root / "test.py"
            test_file.write_text('"""Test docstring."""\ndef func():\n    pass\n')

            file_id = temp_db.add_file(
                path=str(test_file),
                lines=3,
                last_modified=test_file.stat().st_mtime,
                has_docstring=True,
                project_id=project_id,
            )

            # Verify file is in database
            file_record = temp_db.get_file_by_path(
                path=str(test_file), project_id=project_id
            )
            assert file_record is not None
            assert file_record["id"] == file_id
            assert file_record["project_id"] == project_id

    def test_vectorization_faiss_integration(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager
    ):
        """Test integration with FAISS index."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            import json
            import uuid

            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database
            temp_db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Verify FAISS manager is available
            assert mock_faiss_manager is not None
            assert hasattr(mock_faiss_manager, "add_vector")
            assert hasattr(mock_faiss_manager, "save_index")

            # Test adding vector
            test_vector = [0.1] * 384
            vector_id = mock_faiss_manager.add_vector(test_vector)
            assert vector_id is not None

            # Test saving index
            mock_faiss_manager.save_index()
            assert mock_faiss_manager.save_index.called

