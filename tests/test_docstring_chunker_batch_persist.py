"""
Tests for DocstringChunker batch persist: ``upsert_code_chunks_batch`` / shared upsert SQL.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from unittest.mock import Mock

import pytest

from code_analysis.core.database.code_chunk_sql import (
    CODE_CHUNK_UPSERT_PARAM_COUNT,
    CODE_CHUNK_UPSERT_SQL,
    build_code_chunk_upsert_batch,
)
from code_analysis.core.docstring_chunker_pkg.docstring_chunker import DocstringChunker


@pytest.fixture
def mock_db_with_execute_batch():
    """Database mock that records upsert + execute_batch (mirrors CodeDatabase)."""
    mock = Mock()
    mock.execute_batch_calls = []
    mock.upsert_code_chunks_batch_calls: list = []

    def execute_batch(operations):
        mock.execute_batch_calls.append(operations)
        return [{"affected_rows": 1, "lastrowid": i} for i in range(len(operations))]

    def upsert_code_chunks_batch(param_rows):
        mock.upsert_code_chunks_batch_calls.append(list(param_rows))
        return execute_batch(build_code_chunk_upsert_batch(param_rows))

    mock.execute_batch = execute_batch
    mock.upsert_code_chunks_batch = upsert_code_chunks_batch
    mock.execute = Mock(
        return_value={"data": [{}], "affected_rows": 0, "lastrowid": None}
    )
    return mock


@pytest.fixture
def minimal_python_with_docstrings():
    """Minimal Python source with module and class docstrings (2 chunks)."""
    return '''"""Module docstring."""
class A:
    """Class docstring."""
    pass
'''


class TestDocstringChunkerBatchPersist:
    """DocstringChunker persists via ``upsert_code_chunks_batch`` and shared upsert SQL."""

    @pytest.mark.asyncio
    async def test_process_file_calls_execute_batch_once(
        self, mock_db_with_execute_batch, minimal_python_with_docstrings
    ):
        """process_file calls upsert_code_chunks_batch once; driver uses shared upsert SQL."""
        chunker = DocstringChunker(
            database=mock_db_with_execute_batch,
            svo_client_manager=None,
            embedding_model=None,
        )
        source = minimal_python_with_docstrings
        tree = ast.parse(source)

        written = await chunker.process_file(
            file_id="00000000-0000-0000-0000-000000000001",
            project_id="test-project-id",
            file_path="test.py",
            tree=tree,
            file_content=source,
        )

        assert len(mock_db_with_execute_batch.upsert_code_chunks_batch_calls) == 1
        upsert_rows = mock_db_with_execute_batch.upsert_code_chunks_batch_calls[0]
        assert len(upsert_rows) == 2
        for row in upsert_rows:
            assert len(row) == CODE_CHUNK_UPSERT_PARAM_COUNT

        assert len(mock_db_with_execute_batch.execute_batch_calls) == 1
        insert_ops = mock_db_with_execute_batch.execute_batch_calls[0]
        assert len(insert_ops) == 2, "Expected 2 docstring chunks (module + class)"
        assert written == 2

        expected_sql = CODE_CHUNK_UPSERT_SQL.strip()
        for sql, params in insert_ops:
            assert sql == expected_sql
            assert len(params) == CODE_CHUNK_UPSERT_PARAM_COUNT
            assert isinstance(params[0], str) and len(params[0]) >= 32
            assert params[1] == "00000000-0000-0000-0000-000000000001"
            assert params[2] == "test-project-id"

    @pytest.mark.asyncio
    async def test_process_file_execute_batch_result_shape(
        self, mock_db_with_execute_batch, minimal_python_with_docstrings
    ):
        """execute_batch is called with list of (sql, params); driver returns one dict per op."""
        chunker = DocstringChunker(
            database=mock_db_with_execute_batch,
            svo_client_manager=None,
            embedding_model=None,
        )
        source = minimal_python_with_docstrings
        tree = ast.parse(source)

        await chunker.process_file(
            file_id="00000000-0000-0000-0000-000000000042",
            project_id="proj-uuid",
            file_path="x.py",
            tree=tree,
            file_content=source,
        )

        insert_ops = mock_db_with_execute_batch.execute_batch_calls[0]
        for sql, params in insert_ops:
            assert isinstance(sql, str)
            assert isinstance(params, (tuple, list))
            assert params[1] == "00000000-0000-0000-0000-000000000042"
            assert params[2] == "proj-uuid"
            assert params[6] in (1, 2)

    @pytest.mark.asyncio
    async def test_process_file_no_chunks_does_not_call_execute_batch(
        self, mock_db_with_execute_batch
    ):
        """When there are no docstrings, insert_ops is empty and execute_batch is not called."""
        source = "x = 1"
        tree = ast.parse(source)
        chunker = DocstringChunker(
            database=mock_db_with_execute_batch,
            svo_client_manager=None,
            embedding_model=None,
        )

        written = await chunker.process_file(
            file_id="00000000-0000-0000-0000-000000000001",
            project_id="p",
            file_path="nodoc.py",
            tree=tree,
            file_content=source,
        )

        assert written == 0
        assert len(mock_db_with_execute_batch.execute_batch_calls) == 0
