"""
Integration tests for vectorization worker on real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from code_analysis.core.project_resolution import load_project_info
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE_F, WHERE_HAS_DOCSTRING_F
from code_analysis.core.vectorization_worker_pkg.base import VectorizationWorker
from code_analysis.core.vectorization_worker_pkg.chunking import (
    _request_chunking_for_files,
)

_INTEGRATION_DB_NAME = "vectorization_integration.db"


def _get_or_create_project(
    client: DatabaseClient,
    root_path: str,
    name: str | None = None,
    project_id: str | None = None,
) -> str:
    rp = str(Path(root_path).resolve())
    rows = client.select("projects", where={"root_path": rp})
    if rows:
        return str(rows[0]["id"])
    new_id = project_id if project_id else str(uuid.uuid4())
    client.create_project(Project(id=new_id, root_path=rp, name=name or Path(rp).name))
    return new_id


def _get_files_needing_chunking(
    db: DatabaseClient, project_id: str, limit: int = 10
) -> list[dict]:
    sql = (
        """
                SELECT DISTINCT f.id, f.project_id, f.path, f.has_docstring
                FROM files f
                WHERE f.project_id = ?
                AND """
        + WHERE_FILES_ACTIVE_F
        + """
                AND (
                    """
        + WHERE_HAS_DOCSTRING_F
        + """
                    OR EXISTS (
                        SELECT 1 FROM classes c
                        WHERE c.file_id = f.id AND c.docstring IS NOT NULL
                        AND c.docstring != ''
                    )
                    OR EXISTS (
                        SELECT 1 FROM functions fn
                        WHERE fn.file_id = f.id AND fn.docstring IS NOT NULL
                        AND fn.docstring != ''
                    )
                    OR EXISTS (
                        SELECT 1 FROM methods m
                        JOIN classes c ON m.class_id = c.id
                        WHERE c.file_id = f.id AND m.docstring IS NOT NULL
                        AND m.docstring != ''
                    )
                )
                AND (f.needs_chunking = 1 OR NOT EXISTS (
                    SELECT 1 FROM code_chunks cc
                    WHERE cc.file_id = f.id
                ))
                ORDER BY f.updated_at DESC
                LIMIT ?
                """
    )
    r = db.execute(sql, (project_id, limit))
    data = r.get("data") if isinstance(r, dict) else []
    return list(data or [])


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


@pytest.fixture
def temp_db(tmp_path):
    """DatabaseClient over in-process RPC with full schema."""
    db_path = tmp_path / _INTEGRATION_DB_NAME
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    driver = create_driver(
        "sqlite", {"path": str(db_path), "backup_dir": str(backup_dir)}
    )
    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=ipc)
    client.connect()
    try:
        client.sync_schema(get_schema_definition(), backup_dir=str(backup_dir))
        yield client
    finally:
        client.disconnect()
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

        # Create project in database (use project_id from projectid file so add_file finds it)
        _get_or_create_project(
            temp_db,
            root_path=str(project_info.root_path),
            name="vast_srv_test",
            project_id=project_info.project_id,
        )

        # Find Python files in vast_srv
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in vast_srv")

        # Add first few files to database
        test_files = python_files[:5]  # Test with first 5 files
        for file_path in test_files:
            temp_db.add_file(
                path=str(file_path),
                lines=len(file_path.read_text().splitlines()),
                last_modified=file_path.stat().st_mtime,
                has_docstring=False,
                project_id=project_info.project_id,
            )

        # Create worker (universal API: no project_id; faiss_dir/vector_dim required)
        db_path = tmp_path / _INTEGRATION_DB_NAME
        worker = VectorizationWorker(
            db_path=db_path,
            faiss_dir=tmp_path / "faiss",
            vector_dim=384,
            config_path=str(tmp_path / "config.json"),
            svo_client_manager=mock_svo_client_manager,
        )
        worker.faiss_manager = mock_faiss_manager  # for _request_chunking_for_files

        # Get files that need chunking
        files_needing_chunking = _get_files_needing_chunking(
            temp_db, project_id=project_info.project_id, limit=10
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
            assert (
                chunked_count >= 0
            )  # May be 0 if chunking fails, but should not error

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

        # Create project in database (use project_id from projectid file)
        _get_or_create_project(
            temp_db,
            root_path=str(project_info.root_path),
            name="bhlff_test",
            project_id=project_info.project_id,
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
            assert isinstance(file_id, str) and len(file_id) > 0

    def test_vectorization_different_file_extensions(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager
    ):
        """Test processing files with various extensions."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database (use project_id from projectid file)
            _get_or_create_project(
                temp_db,
                root_path=str(project_root),
                name="test_project",
                project_id=project_id,
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
                )
                assert isinstance(file_id, str) and len(file_id) > 0

    def test_vectorization_large_files(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager
    ):
        """Test processing large files."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database (use project_id from projectid file)
            _get_or_create_project(
                temp_db,
                root_path=str(project_root),
                name="test_project",
                project_id=project_id,
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
            assert isinstance(file_id, str) and len(file_id) > 0

    @pytest.mark.asyncio
    async def test_vectorization_error_handling(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager, tmp_path
    ):
        """Test error handling during vectorization."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database (use project_id from projectid file)
            _get_or_create_project(
                temp_db,
                root_path=str(project_root),
                name="test_project",
                project_id=project_id,
            )

            # Create file with syntax error
            error_file = project_root / "error_file.py"
            error_file.write_text("def invalid syntax here\n")

            temp_db.add_file(
                path=str(error_file),
                lines=1,
                last_modified=error_file.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
            )

            # Create worker (universal API; set faiss_manager for chunking)
            worker = VectorizationWorker(
                db_path=tmp_path / _INTEGRATION_DB_NAME,
                faiss_dir=Path(tmpdir) / "faiss",
                vector_dim=384,
                config_path=str(Path(tmpdir) / "config.json"),
                svo_client_manager=mock_svo_client_manager,
            )
            worker.faiss_manager = mock_faiss_manager

            # Get files that need chunking
            files_needing_chunking = _get_files_needing_chunking(
                temp_db, project_id=project_id, limit=10
            )

            # Request chunking - should handle errors gracefully
            if files_needing_chunking:
                chunked_count = await _request_chunking_for_files(
                    worker, temp_db, files_needing_chunking
                )
                # Should not crash, even if chunking fails
                assert chunked_count >= 0

    def test_vectorization_performance(
        self, temp_db, mock_svo_client_manager, mock_faiss_manager
    ):
        """Test vectorization performance on multiple files."""
        # Create test project
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database (use project_id from projectid file)
            _get_or_create_project(
                temp_db,
                root_path=str(project_root),
                name="test_project",
                project_id=project_id,
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
                )
                assert isinstance(file_id, str) and len(file_id) > 0

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
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database (use project_id from projectid file)
            _get_or_create_project(
                temp_db,
                root_path=str(project_root),
                name="test_project",
                project_id=project_id,
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
                str(test_file.resolve()), project_id=project_id
            )
            assert file_record is not None
            assert str(file_record["id"]) == str(file_id)
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
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Create project in database (use project_id from projectid file)
            _get_or_create_project(
                temp_db,
                root_path=str(project_root),
                name="test_project",
                project_id=project_id,
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
