"""
Chunker (SVO) client operations for SVOClientManager.

Initialization, close, get_chunks, get_chunks_batch, and fetch_chunk_limits.
Manager is passed as first argument; attributes and circuit callbacks are used.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, List

from .svo_client_manager_logging import (
    TRACE_PREVIEW_LEN as _TRACE_PREVIEW_LEN,
    _get_chunker_logger,
    log_vectorization_trace,
)

logger = logging.getLogger(__name__)

try:
    from svo_client import ChunkerClient

    CHUNKER_CLIENT_AVAILABLE = True
except ImportError:
    ChunkerClient = None
    CHUNKER_CLIENT_AVAILABLE = False


async def init_chunker(manager: Any) -> None:
    """Create and attach ChunkerClient to manager. Raises on failure if enabled."""
    if not manager.chunker_enabled or not CHUNKER_CLIENT_AVAILABLE:
        if manager.chunker_enabled and not CHUNKER_CLIENT_AVAILABLE:
            raise RuntimeError(
                "svo_client library is not available. Install it to use chunker service."
            )
        return
    chunker_kwargs: dict[str, Any] = {
        "host": manager._chunker_url,
        "port": manager._chunker_port,
        "check_hostname": manager._chunker_check_hostname,
        "timeout": manager._chunker_timeout,
    }
    if manager._chunker_protocol in ("mtls", "https"):
        root = manager._root_path
        if manager._chunker_cert_file:
            p = Path(manager._chunker_cert_file)
            if not p.is_absolute() and root:
                p = root / p
            chunker_kwargs["cert"] = str(p.resolve())
        if manager._chunker_key_file:
            p = Path(manager._chunker_key_file)
            if not p.is_absolute() and root:
                p = root / p
            chunker_kwargs["key"] = str(p.resolve())
        if manager._chunker_ca_cert_file:
            p = Path(manager._chunker_ca_cert_file)
            if not p.is_absolute() and root:
                p = root / p
            chunker_kwargs["ca"] = str(p.resolve())
    manager._chunker_client = ChunkerClient(**chunker_kwargs)
    await manager._chunker_client.__aenter__()
    await fetch_chunk_limits(manager)
    logger.info(
        "SVOClientManager initialized with real chunker service "
        "(url=%s:%s, protocol=%s)",
        manager._chunker_url,
        manager._chunker_port,
        manager._chunker_protocol,
    )


async def close_chunker(manager: Any) -> None:
    """Close chunker client and set manager._chunker_client to None."""
    if not manager._chunker_client:
        return
    try:
        await manager._chunker_client.__aexit__(None, None, None)
    except Exception as e:
        logger.warning("Error closing chunker client: %s", e, exc_info=True)
    finally:
        manager._chunker_client = None


async def get_chunks(manager: Any, text: str, **kwargs: Any) -> List[Any]:
    """Get chunks with embeddings from chunker service (WebSocket)."""
    manager._maybe_transition()
    if not manager._chunker_client or not manager.chunker_enabled:
        raise RuntimeError(
            "Chunker service is not available or not enabled. "
            "Ensure code_analysis.chunker.enabled=true and service is running."
        )
    min_len = manager._min_chunk_length if manager._min_chunk_length is not None else 15
    if len(text) < min_len:
        logger.debug(
            "Text length (%d) is below chunker minimum (%d). Skipping chunker.",
            len(text),
            min_len,
        )
        return []
    chunker_log = _get_chunker_logger(manager._root_dir)
    request_start_time = time.time()
    text_preview = text[:200] + "..." if len(text) > 200 else text
    chunker_log.info(
        "REQUEST | text_length=%d | text_preview=%r | kwargs=%s",
        len(text),
        text_preview,
        kwargs,
    )
    try:
        chunk_timeout = kwargs.get("timeout") or manager._chunker_timeout or 0.0
        chunk_kwargs = {k: v for k, v in kwargs.items() if k != "timeout"}
        batch = await manager._chunker_client.chunk(
            texts=[text], timeout=float(chunk_timeout), **chunk_kwargs
        )
        chunks = batch[0] if batch else []
        request_duration = time.time() - request_start_time
        chunks_count = len(chunks) if chunks else 0
        has_embeddings = False
        if chunks:
            first = chunks[0]
            emb = getattr(first, "embedding", None)
            has_embeddings = emb is not None and (
                (isinstance(emb, list) and len(emb) > 0)
                or (getattr(first, "vector", None) is not None)
            )
        chunker_log.info(
            "SUCCESS | duration=%.3fs | chunks_count=%d | has_embeddings=%s",
            request_duration,
            chunks_count,
            has_embeddings,
        )
        if manager._log_chunker_trace:
            log_vectorization_trace(
                text_preview, has_embeddings, error="", root_dir=manager._root_dir
            )
        was_unavailable = not manager._chunker_available
        manager._record_success()
        if was_unavailable:
            logger.info("✅ Chunker service is now available")
            manager._chunker_available = True
            manager._chunker_status_logged = True
            asyncio.create_task(fetch_chunk_limits(manager))
        else:
            manager._chunker_status_logged = False
        return chunks
    except Exception as e:
        request_duration = time.time() - request_start_time
        chunker_log.error(
            "ERROR | duration=%.3fs | error_type=%s | error=%s",
            request_duration,
            type(e).__name__,
            str(e),
        )
        if manager._log_chunker_trace:
            log_vectorization_trace(
                text_preview,
                False,
                error=f"{type(e).__name__}: {str(e)}",
                root_dir=manager._root_dir,
            )
        manager._record_failure()
        err_str = str(e).lower()
        is_unavailable = (
            "model rpc server failed" in err_str
            or "connection" in err_str
            or "timeout" in err_str
            or "unavailable" in err_str
            or "failed after" in err_str
        )
        if is_unavailable:
            if manager._chunker_available:
                logger.warning("⚠️  Chunker service is now unavailable: %s", e)
                manager._chunker_available = False
                manager._chunker_status_logged = True
            elif not manager._chunker_status_logged:
                logger.warning("⚠️  Chunker service is unavailable: %s", e)
                manager._chunker_status_logged = True
            else:
                manager._chunker_status_logged = False
        else:
            logger.error(
                "Failed to get chunks from chunker service: %s", e, exc_info=True
            )
        raise


async def get_chunks_batch(
    manager: Any, texts: List[str], **kwargs: Any
) -> List[List[Any]]:
    """Get chunks with embeddings for multiple texts via WebSocket."""
    manager._maybe_transition()
    if not manager._chunker_client or not manager.chunker_enabled:
        raise RuntimeError(
            "Chunker service is not available or not enabled. "
            "Ensure code_analysis.chunker.enabled=true and service is running."
        )
    if not texts:
        return []
    min_len = manager._min_chunk_length if manager._min_chunk_length is not None else 15
    valid_indices: List[int] = []
    valid_texts: List[str] = []
    for i, text in enumerate(texts):
        if len(text) >= min_len:
            valid_indices.append(i)
            valid_texts.append(text)
    result: List[List[Any]] = [[] for _ in texts]
    if not valid_texts:
        return result
    chunker_log = _get_chunker_logger(manager._root_dir)
    request_start_time = time.time()
    chunker_log.info(
        "BATCH REQUEST | texts_count=%d | kwargs=%s", len(valid_texts), kwargs
    )
    try:
        chunk_timeout = kwargs.get("timeout") or manager._chunker_timeout or 0.0
        chunk_kwargs = {k: v for k, v in kwargs.items() if k != "timeout"}
        batch = await manager._chunker_client.chunk(
            texts=valid_texts, timeout=float(chunk_timeout), **chunk_kwargs
        )
        request_duration = time.time() - request_start_time
        for k, idx in enumerate(valid_indices):
            if k < len(batch):
                result[idx] = batch[k]
        if manager._log_chunker_trace:
            for k, text in enumerate(valid_texts):
                chunks_k = batch[k] if k < len(batch) else []
                has_emb = False
                if chunks_k:
                    ch = chunks_k[0]
                    emb = getattr(ch, "embedding", None) or getattr(ch, "vector", None)
                    has_emb = emb is not None and (
                        (not isinstance(emb, list))
                        or (isinstance(emb, list) and len(emb) > 0)
                    )
                log_vectorization_trace(
                    text[:_TRACE_PREVIEW_LEN] if text else "",
                    has_emb,
                    error=(
                        ""
                        if has_emb
                        else "no embedding from chunker (empty or no model)"
                    ),
                    root_dir=manager._root_dir,
                )
        chunker_log.info(
            "BATCH SUCCESS | duration=%.3fs | texts_count=%d",
            request_duration,
            len(valid_texts),
        )
        manager._record_success()
        if not manager._chunker_available:
            manager._chunker_available = True
            manager._chunker_status_logged = True
            asyncio.create_task(fetch_chunk_limits(manager))
        return result
    except Exception as e:
        request_duration = time.time() - request_start_time
        chunker_log.error(
            "BATCH ERROR | duration=%.3fs | error_type=%s | error=%s",
            request_duration,
            type(e).__name__,
            str(e),
        )
        if manager._log_chunker_trace:
            err_msg = f"{type(e).__name__}: {str(e)}"
            for text in valid_texts:
                log_vectorization_trace(
                    text[:_TRACE_PREVIEW_LEN] if text else "",
                    False,
                    error=err_msg,
                    root_dir=manager._root_dir,
                )
        manager._record_failure()
        raise


async def fetch_chunk_limits(manager: Any) -> None:
    """Fetch chunk size limits from chunker service and set on manager."""
    if not manager._chunker_client:
        return
    get_chunk_config = getattr(manager._chunker_client, "get_chunk_config", None)
    if not callable(get_chunk_config):
        logger.debug("Chunker client has no get_chunk_config; skipping chunk limits.")
        return
    try:
        config_result = await get_chunk_config()
        if not isinstance(config_result, dict):
            logger.warning(
                "get_chunk_config returned non-dict: %s", type(config_result)
            )
            return
        config = config_result.get("config")
        if config is None:
            data = config_result.get("data", {})
            if isinstance(data, dict):
                config = data.get("config")
        if config is None:
            result = config_result.get("result", {})
            if isinstance(result, dict):
                data = result.get("data", {})
                if isinstance(data, dict):
                    config = data.get("config")
        if config and isinstance(config, dict):
            chunk_size = config.get("chunk_size", {})
            if isinstance(chunk_size, dict):
                manager._min_chunk_length = chunk_size.get("min_chunk_length")
                manager._max_chunk_length = chunk_size.get("max_chunk_length")
                logger.info(
                    "Chunker limits fetched: min=%s, max=%s",
                    manager._min_chunk_length,
                    manager._max_chunk_length,
                )
            else:
                logger.warning("chunk_size is not a dict: %s", type(chunk_size))
        else:
            logger.warning(
                "Could not extract config from get_chunk_config response. Keys: %s",
                list(config_result.keys()),
            )
    except Exception as e:
        logger.warning(
            "Failed to fetch chunk limits from chunker service: %s. Using defaults.",
            e,
            exc_info=True,
        )
