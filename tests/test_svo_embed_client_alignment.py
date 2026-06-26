"""
Unit tests for svo-client 3.x and embed-client response alignment in SVOClientManager helpers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.core.svo_client_manager_chunker import (
    _chunk_rpc_kwargs,
    _chunker_protocol_for_client,
    get_chunks,
    get_chunks_batch,
)
from code_analysis.core.svo_client_manager_embedding import (
    _normalize_embed_cmd_response,
    _unwrap_embed_execute_payload,
    get_embeddings,
)


def test_chunker_protocol_for_client() -> None:
    """Verify test chunker protocol for client."""
    assert _chunker_protocol_for_client("http") == "http"
    assert _chunker_protocol_for_client("HTTPS") == "https"
    assert _chunker_protocol_for_client("mtls") == "mtls"
    assert _chunker_protocol_for_client("unknown") == "https"


def test_unwrap_embed_execute_payload_promotes_result_data_result_data_results() -> (
    None
):
    """Queued job completion after normalize: vectors under ``result.data.result.data``."""
    raw: dict = {
        "result": {
            "success": True,
            "data": {
                "job_id": "job-1",
                "command": "embed",
                "status": "job_completed",
                "result": {
                    "data": {
                        "model": "queued-model",
                        "results": [
                            {"embedding": [0.1, 0.2], "body": "a"},
                        ],
                    }
                },
            },
        },
    }
    _unwrap_embed_execute_payload(raw)
    data = raw["result"]["data"]
    assert "result" not in data
    assert data["results"][0]["embedding"] == [0.1, 0.2]
    assert data["model"] == "queued-model"
    assert data["job_id"] == "job-1"
    assert data["status"] == "job_completed"


def test_normalize_embed_cmd_response_job_envelope_without_success_wrapper() -> None:
    """embed_client may return job completion at ``result`` without ``success``/``data``."""
    payload = {
        "result": {
            "job_id": "job-1",
            "command": "embed",
            "status": "job_completed",
            "result": {
                "data": {
                    "model": "m1",
                    "results": [{"embedding": [0.1, 0.2], "body": "a"}],
                }
            },
        }
    }
    out = _normalize_embed_cmd_response(payload)
    assert out["model"] == "m1"
    assert out["results"][0]["embedding"] == [0.1, 0.2]


def test_chunk_rpc_kwargs_maps_type_to_chunk_type() -> None:
    """Verify test chunk rpc kwargs maps type to chunk type."""
    assert _chunk_rpc_kwargs({"type": "DocBlock", "language": "Python"}) == {
        "chunk_type": "DocBlock",
        "language": "Python",
    }
    assert _chunk_rpc_kwargs({"timeout": 5.0, "type": "X"}) == {"chunk_type": "X"}


@pytest.mark.asyncio
async def test_get_chunks_uses_chunk_single_text_and_wait_for() -> None:
    """svo-client 3.x: single path uses ``chunk(text=...)`` (not ``texts=[...]``)."""
    chunks_out = [SimpleNamespace(embedding=[0.1])]
    mock_client = MagicMock()
    mock_client.chunk = AsyncMock(return_value=chunks_out)

    manager = SimpleNamespace(
        _maybe_transition=lambda: None,
        _chunker_client=mock_client,
        chunker_enabled=True,
        _min_chunk_length=5,
        _chunker_timeout=300.0,
        _root_dir=None,
        _log_chunker_trace=False,
        _chunker_available=True,
        _chunker_status_logged=False,
        _record_success=MagicMock(),
        _record_failure=MagicMock(),
    )
    text = "hello world" * 3
    with patch(
        "code_analysis.core.svo_client_manager_chunker._get_chunker_logger",
        return_value=MagicMock(),
    ):
        out = await get_chunks(manager, text, type="DocBlock", timeout=10.0)

    assert out is chunks_out
    mock_client.chunk.assert_called_once()
    call_kw = mock_client.chunk.call_args
    assert call_kw.kwargs.get("text") == text
    assert call_kw.kwargs.get("chunk_type") == "DocBlock"
    assert "texts" not in call_kw.kwargs


@pytest.mark.asyncio
async def test_get_chunks_batch_uses_chunk_batch() -> None:
    """Verify test get chunks batch uses chunk batch."""
    batch_out = [[SimpleNamespace(embedding=[0.2])]]
    mock_client = MagicMock()
    mock_client.chunk_batch = AsyncMock(return_value=batch_out)

    manager = SimpleNamespace(
        _maybe_transition=lambda: None,
        _chunker_client=mock_client,
        chunker_enabled=True,
        _min_chunk_length=5,
        _chunker_timeout=None,
        _root_dir=None,
        _log_chunker_trace=False,
        _chunker_available=False,
        _chunker_status_logged=False,
        _record_success=MagicMock(),
        _record_failure=MagicMock(),
    )
    texts = ["hello world " * 3]
    with patch(
        "code_analysis.core.svo_client_manager_chunker._get_chunker_logger",
        return_value=MagicMock(),
    ):
        out = await get_chunks_batch(manager, texts, type="DocBlock")

    mock_client.chunk_batch.assert_called_once()
    assert mock_client.chunk_batch.call_args.kwargs["texts"] == texts
    assert mock_client.chunk_batch.call_args.kwargs.get("chunk_type") == "DocBlock"
    assert out[0] == batch_out[0]


@pytest.mark.asyncio
async def test_get_embeddings_uses_extract_embeddings_adapter_shape() -> None:
    """embed-client parser accepts ``result.data.results[].embedding``."""
    raw_response = {
        "mode": "immediate",
        "result": {
            "success": True,
            "data": {
                "model": "test-model",
                "results": [
                    {"embedding": [1.0, 2.0], "body": "a"},
                ],
            },
        },
    }
    mock_embed = MagicMock()
    mock_embed.cmd = AsyncMock(return_value=raw_response)

    chunk = SimpleNamespace(body="hello")
    manager = SimpleNamespace(
        _maybe_transition=lambda: None,
        _embedding_client=mock_embed,
        embedding_enabled=True,
        _record_success=MagicMock(),
        _record_failure=MagicMock(),
        _embedding_available=True,
        _embedding_status_logged=False,
    )

    out = await get_embeddings(manager, [chunk])
    assert out[0] is chunk
    assert chunk.embedding == [1.0, 2.0]
    assert getattr(chunk, "embedding_model") == "test-model"


@pytest.mark.asyncio
async def test_get_embeddings_unwraps_embed_execute_nested_data_results() -> None:
    """Normalized responses may nest vectors under ``data.embed_execute.data.results``."""
    raw_response = {
        "mode": "immediate",
        "result": {
            "success": True,
            "data": {
                "embed_execute": {
                    "data": {
                        "model": "wrapped-model",
                        "results": [
                            {"embedding": [0.5, 0.25], "body": "a"},
                        ],
                    }
                }
            },
        },
    }
    mock_embed = MagicMock()
    mock_embed.cmd = AsyncMock(return_value=raw_response)

    chunk = SimpleNamespace(body="hello")
    manager = SimpleNamespace(
        _maybe_transition=lambda: None,
        _embedding_client=mock_embed,
        embedding_enabled=True,
        _record_success=MagicMock(),
        _record_failure=MagicMock(),
        _embedding_available=True,
        _embedding_status_logged=False,
    )

    out = await get_embeddings(manager, [chunk])
    assert out[0] is chunk
    assert chunk.embedding == [0.5, 0.25]
    assert getattr(chunk, "embedding_model") == "wrapped-model"


@pytest.mark.asyncio
async def test_get_embeddings_unwraps_result_data_result_data_results() -> None:
    """Same shape as after ``normalize_command_response`` for queued completion (no extra normalize)."""
    raw_response = {
        "result": {
            "success": True,
            "data": {
                "job_id": "job-1",
                "command": "embed",
                "status": "job_completed",
                "result": {
                    "data": {
                        "model": "norm-model",
                        "results": [
                            {"embedding": [9.0, 8.0], "body": "a"},
                        ],
                    }
                },
            },
        },
    }
    mock_embed = MagicMock()
    mock_embed.cmd = AsyncMock(return_value=raw_response)

    chunk = SimpleNamespace(body="hello")
    manager = SimpleNamespace(
        _maybe_transition=lambda: None,
        _embedding_client=mock_embed,
        embedding_enabled=True,
        _record_success=MagicMock(),
        _record_failure=MagicMock(),
        _embedding_available=True,
        _embedding_status_logged=False,
    )

    out = await get_embeddings(manager, [chunk])
    assert out[0] is chunk
    assert chunk.embedding == [9.0, 8.0]
    assert getattr(chunk, "embedding_model") == "norm-model"


@pytest.mark.asyncio
async def test_get_embeddings_accepts_queued_job_completed_despite_false_success_flag() -> (
    None
):
    """
    Queued embed normalizer sets success only for status completed/success;
    live services use job_completed, yielding success false with valid data.
    """
    raw_response = {
        "mode": "queued",
        "status": "job_completed",
        "job_id": "job-1",
        "result": {
            "model": "test-model",
            "results": [
                {"embedding": [1.0, 2.0], "body": "hello"},
            ],
        },
    }
    mock_embed = MagicMock()
    mock_embed.cmd = AsyncMock(return_value=raw_response)

    chunk = SimpleNamespace(body="hello")
    manager = SimpleNamespace(
        _maybe_transition=lambda: None,
        _embedding_client=mock_embed,
        embedding_enabled=True,
        _record_success=MagicMock(),
        _record_failure=MagicMock(),
        _embedding_available=True,
        _embedding_status_logged=False,
    )

    out = await get_embeddings(manager, [chunk])
    assert out[0] is chunk
    assert chunk.embedding == [1.0, 2.0]
    assert getattr(chunk, "embedding_model") == "test-model"
    manager._record_success.assert_called_once()


@pytest.mark.asyncio
async def test_get_embeddings_rejects_explicit_failure() -> None:
    """Verify test get embeddings rejects explicit failure."""
    raw_response = {
        "result": {
            "success": False,
            "error": {"message": "boom"},
        },
    }
    mock_embed = MagicMock()
    mock_embed.cmd = AsyncMock(return_value=raw_response)

    chunk = SimpleNamespace(body="x")
    manager = SimpleNamespace(
        _maybe_transition=lambda: None,
        _embedding_client=mock_embed,
        embedding_enabled=True,
        _record_success=MagicMock(),
        _record_failure=MagicMock(),
        _embedding_available=True,
        _embedding_status_logged=False,
    )

    with pytest.raises(ValueError, match="Embedding service error"):
        await get_embeddings(manager, [chunk])
    manager._record_failure.assert_called_once()
