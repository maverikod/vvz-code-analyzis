"""
Tests for projects_pending_sql() category breakdown and cat3 OR->AND alignment fix.

Verifies that:
1. cat1_count: files with docstrings but no code_chunks rows
2. cat2_count: chunks with embedding_vector but no vector_id/embedding_vec yet
3. cat3_count: chunks needing both embedding_vector AND embedding_model NULL
4. Rows with exactly one NULL (embedding_vector or embedding_model) are not
   counted as pending (regression check for OR->AND alignment fix)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Iterator

import pytest

from code_analysis.core.vectorization_worker_pkg.processing_cycle import \
    projects_pending_sql
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


@pytest.fixture
def pending_sql_db_client(tmp_path: Path) -> Iterator:
    """Fixture providing a full-schema SQLite database client for testing."""
    # Set up server_instance_id for the database
    server_instance_id = str(uuid.uuid4())
    original_sid = os.environ.get("CODE_ANALYSIS_SERVER_INSTANCE_ID")
    os.environ["CODE_ANALYSIS_SERVER_INSTANCE_ID"] = server_instance_id

    db_path = tmp_path / "pending_sql.db"
    backup_dir = tmp_path / "backups"
    client = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
    try:
        yield client
    finally:
        client.disconnect()
        if original_sid is None:
            os.environ.pop("CODE_ANALYSIS_SERVER_INSTANCE_ID", None)
        else:
            os.environ["CODE_ANALYSIS_SERVER_INSTANCE_ID"] = original_sid


def _insert_project(
    client, project_id: str, root_path: str, name: str, server_instance_id: str
) -> None:
    """Helper: insert a project row."""
    client.execute(
        "INSERT INTO projects "
        "(id, server_instance_id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, ?, julianday('now'))",
        (project_id, server_instance_id, root_path, name),
    )


def _get_current_server_instance_id() -> str:
    """Helper: get the server_instance_id from environment."""
    sid = os.environ.get("CODE_ANALYSIS_SERVER_INSTANCE_ID")
    if not sid:
        raise RuntimeError(
            "CODE_ANALYSIS_SERVER_INSTANCE_ID environment variable not set"
        )
    return sid


def _insert_file(
    client, file_id: str, project_id: str, path: str, has_docstring: int = 0
) -> None:
    """Helper: insert a file row."""
    client.execute(
        "INSERT INTO files "
        "(id, project_id, path, relative_path, lines, has_docstring, deleted, "
        "needs_chunking, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, julianday('now'), julianday('now'))",
        (
            file_id,
            project_id,
            path,
            path,  # relative_path
            1,  # lines
            has_docstring,
            0,  # deleted
            0,  # needs_chunking
        ),
    )


def _insert_code_chunk(
    client,
    chunk_id: str,
    file_id: str,
    project_id: str,
    chunk_uuid: str,
    embedding_vector=None,
    embedding_model=None,
    vector_id=None,
    vectorization_skipped=None,
) -> None:
    """Helper: insert a code_chunks row."""
    client.execute(
        "INSERT INTO code_chunks "
        "(id, file_id, project_id, chunk_uuid, chunk_type, chunk_text, "
        "chunk_ordinal, vector_id, embedding_model, embedding_vector, "
        "vectorization_skipped, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))",
        (
            chunk_id,
            file_id,
            project_id,
            chunk_uuid,
            "docstring",  # chunk_type
            "test chunk text",  # chunk_text
            1,  # chunk_ordinal
            vector_id,
            embedding_model,
            embedding_vector,
            vectorization_skipped,
        ),
    )


def test_cat1_files_with_docstring_no_chunks(pending_sql_db_client):
    """
    cat1: file has docstring but no code_chunks rows.
    Expected: cat1_count=1, cat2_count=0, cat3_count=0, pending_count=1.
    """
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    root_path = "/tmp/test_cat1"
    server_instance_id = _get_current_server_instance_id()

    _insert_project(
        pending_sql_db_client, project_id, root_path, "test_cat1", server_instance_id
    )
    # File with has_docstring=1, but no code_chunks rows
    _insert_file(
        pending_sql_db_client,
        file_id,
        project_id,
        "/tmp/test_cat1/mod.py",
        has_docstring=1,
    )

    sql = projects_pending_sql()
    result = pending_sql_db_client.execute(sql, None)
    rows = result.get("data", []) if isinstance(result, dict) else []

    # Find the row for our project
    project_row = next((row for row in rows if row["project_id"] == project_id), None)
    assert project_row is not None, f"Project {project_id} not found in results"
    assert project_row["cat1_count"] == 1
    assert project_row["cat2_count"] == 0
    assert project_row["cat3_count"] == 0
    assert project_row["pending_count"] == 1


def test_cat2_chunks_with_embedding_vector_no_vector_id(pending_sql_db_client):
    """
    cat2: chunk has embedding_vector computed but no vector_id yet.
    Expected: cat2_count=1, cat1_count=0, cat3_count=0, pending_count=1.
    """
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    chunk_uuid = str(uuid.uuid4())
    root_path = "/tmp/test_cat2"
    server_instance_id = _get_current_server_instance_id()

    _insert_project(
        pending_sql_db_client, project_id, root_path, "test_cat2", server_instance_id
    )
    _insert_file(
        pending_sql_db_client,
        file_id,
        project_id,
        "/tmp/test_cat2/mod.py",
        has_docstring=0,
    )
    # Chunk with embedding_vector set, but vector_id IS NULL
    _insert_code_chunk(
        pending_sql_db_client,
        chunk_id,
        file_id,
        project_id,
        chunk_uuid,
        embedding_vector="[0.1, 0.2, 0.3]",
        embedding_model="test-model-v1",
        vector_id=None,  # Key: no vector_id yet
    )

    sql = projects_pending_sql()
    result = pending_sql_db_client.execute(sql, None)
    rows = result.get("data", []) if isinstance(result, dict) else []

    project_row = next((row for row in rows if row["project_id"] == project_id), None)
    assert project_row is not None, f"Project {project_id} not found in results"
    assert project_row["cat2_count"] == 1
    assert project_row["cat1_count"] == 0
    assert project_row["cat3_count"] == 0
    assert project_row["pending_count"] == 1


def test_cat3_both_embedding_fields_null(pending_sql_db_client):
    """
    cat3: chunk has BOTH embedding_vector IS NULL AND embedding_model IS NULL.
    Expected: cat3_count=1, cat1_count=0, cat2_count=0, pending_count=1.
    """
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    chunk_uuid = str(uuid.uuid4())
    root_path = "/tmp/test_cat3"
    server_instance_id = _get_current_server_instance_id()

    _insert_project(
        pending_sql_db_client, project_id, root_path, "test_cat3", server_instance_id
    )
    _insert_file(
        pending_sql_db_client,
        file_id,
        project_id,
        "/tmp/test_cat3/mod.py",
        has_docstring=0,
    )
    # Chunk with BOTH embedding_vector and embedding_model NULL
    _insert_code_chunk(
        pending_sql_db_client,
        chunk_id,
        file_id,
        project_id,
        chunk_uuid,
        embedding_vector=None,  # Key: NULL
        embedding_model=None,  # Key: NULL
        vector_id=None,
        vectorization_skipped=None,
    )

    sql = projects_pending_sql()
    result = pending_sql_db_client.execute(sql, None)
    rows = result.get("data", []) if isinstance(result, dict) else []

    project_row = next((row for row in rows if row["project_id"] == project_id), None)
    assert project_row is not None, f"Project {project_id} not found in results"
    assert project_row["cat3_count"] == 1
    assert project_row["cat1_count"] == 0
    assert project_row["cat2_count"] == 0
    assert project_row["pending_count"] == 1


def test_or_to_and_alignment_one_null_not_counted(pending_sql_db_client):
    """
    Regression check for OR->AND alignment fix:
    Chunk with exactly one of embedding_vector/embedding_model NULL should NOT be
    counted as pending (cat3=0), because _CHUNK_SELECT_SQL requires both to be NULL.

    Test: embedding_vector IS NULL but embedding_model is NOT NULL.
    Expected: project absent from results OR (if rows exist) pending_count=0/cat3_count=0.
    """
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    chunk_uuid = str(uuid.uuid4())
    root_path = "/tmp/test_alignment"
    server_instance_id = _get_current_server_instance_id()

    _insert_project(
        pending_sql_db_client,
        project_id,
        root_path,
        "test_alignment",
        server_instance_id,
    )
    _insert_file(
        pending_sql_db_client,
        file_id,
        project_id,
        "/tmp/test_alignment/mod.py",
        has_docstring=0,
    )
    # Chunk with embedding_vector NULL but embedding_model SET (exactly one NULL)
    _insert_code_chunk(
        pending_sql_db_client,
        chunk_id,
        file_id,
        project_id,
        chunk_uuid,
        embedding_vector=None,  # One NULL
        embedding_model="model-v1",  # One NOT NULL
        vector_id=None,
        vectorization_skipped=None,
    )

    sql = projects_pending_sql()
    result = pending_sql_db_client.execute(sql, None)
    rows = result.get("data", []) if isinstance(result, dict) else []

    project_row = next((row for row in rows if row["project_id"] == project_id), None)

    # Either the project is not in the results at all (preferred)
    # or it's there with pending_count=0 and cat3_count=0
    if project_row is None:
        # This is the ideal case: project was filtered out because pending_count=0
        pass
    else:
        # If row is present, it must have no pending work
        assert project_row["pending_count"] == 0, (
            f"Project {project_id} should have pending_count=0 "
            f"when exactly one embedding field is NULL, got {project_row['pending_count']}"
        )
        assert project_row["cat3_count"] == 0, (
            f"Project {project_id} should have cat3_count=0 "
            f"when exactly one embedding field is NULL, got {project_row['cat3_count']}"
        )


def test_vectorization_skipped_chunks_excluded(pending_sql_db_client):
    """
    Chunks with vectorization_skipped=1 should not be counted as pending.
    """
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    chunk_uuid = str(uuid.uuid4())
    root_path = "/tmp/test_skipped"
    server_instance_id = _get_current_server_instance_id()

    _insert_project(
        pending_sql_db_client, project_id, root_path, "test_skipped", server_instance_id
    )
    _insert_file(
        pending_sql_db_client,
        file_id,
        project_id,
        "/tmp/test_skipped/mod.py",
        has_docstring=0,
    )
    # Chunk with both embedding fields NULL but vectorization_skipped=1
    _insert_code_chunk(
        pending_sql_db_client,
        chunk_id,
        file_id,
        project_id,
        chunk_uuid,
        embedding_vector=None,
        embedding_model=None,
        vector_id=None,
        vectorization_skipped=1,  # Key: marked as skipped
    )

    sql = projects_pending_sql()
    result = pending_sql_db_client.execute(sql, None)
    rows = result.get("data", []) if isinstance(result, dict) else []

    project_row = next((row for row in rows if row["project_id"] == project_id), None)
    # Project should not appear or should have pending_count=0
    if project_row is not None:
        assert project_row["pending_count"] == 0, (
            f"Skipped chunks should not be counted; "
            f"got pending_count={project_row['pending_count']}"
        )


def test_multiple_categories_same_project(pending_sql_db_client):
    """
    Project with items in multiple categories simultaneously.
    """
    project_id = str(uuid.uuid4())
    root_path = "/tmp/test_multi"
    server_instance_id = _get_current_server_instance_id()

    _insert_project(
        pending_sql_db_client, project_id, root_path, "test_multi", server_instance_id
    )

    # cat1: file with docstring, no chunks
    file_id_cat1 = str(uuid.uuid4())
    _insert_file(
        pending_sql_db_client,
        file_id_cat1,
        project_id,
        "/tmp/test_multi/cat1.py",
        has_docstring=1,
    )

    # cat2: file with chunk that has embedding_vector but no vector_id
    file_id_cat2 = str(uuid.uuid4())
    _insert_file(
        pending_sql_db_client,
        file_id_cat2,
        project_id,
        "/tmp/test_multi/cat2.py",
        has_docstring=0,
    )
    chunk_id_cat2 = str(uuid.uuid4())
    _insert_code_chunk(
        pending_sql_db_client,
        chunk_id_cat2,
        file_id_cat2,
        project_id,
        str(uuid.uuid4()),
        embedding_vector="[0.1]",
        embedding_model="m1",
        vector_id=None,
    )

    # cat3: file with chunk that has both embedding fields NULL
    file_id_cat3 = str(uuid.uuid4())
    _insert_file(
        pending_sql_db_client,
        file_id_cat3,
        project_id,
        "/tmp/test_multi/cat3.py",
        has_docstring=0,
    )
    chunk_id_cat3 = str(uuid.uuid4())
    _insert_code_chunk(
        pending_sql_db_client,
        chunk_id_cat3,
        file_id_cat3,
        project_id,
        str(uuid.uuid4()),
        embedding_vector=None,
        embedding_model=None,
        vector_id=None,
    )

    sql = projects_pending_sql()
    result = pending_sql_db_client.execute(sql, None)
    rows = result.get("data", []) if isinstance(result, dict) else []

    project_row = next((row for row in rows if row["project_id"] == project_id), None)
    assert project_row is not None
    assert project_row["cat1_count"] == 1
    assert project_row["cat2_count"] == 1
    assert project_row["cat3_count"] == 1
    assert project_row["pending_count"] == 3
