"""
Embedding (embed-client) operations for SVOClientManager.

Initialization, close, and get_embeddings. Manager is passed as first argument.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Iterable, List

logger = logging.getLogger(__name__)

# Max seconds to wait for an in-process embed_execute batch to complete.
EMBED_WAIT_TIMEOUT_SECONDS = 120

try:
    from embed_client.client_factory import ClientFactory
except ImportError as exc:
    _msg = (
        "FATAL: required package `embed_client` (PyPI name: embed-client) is missing. "
        "Install project dependencies, e.g. `pip install -e .`"
    )
    try:
        logging.basicConfig(level=logging.CRITICAL, force=True)
    except TypeError:
        logging.basicConfig(level=logging.CRITICAL)
    logger.critical("%s ImportError: %s", _msg, exc)
    print(_msg, file=sys.stderr)
    print(f"ImportError: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


def get_chunk_text(chunk: Any) -> str:
    """Extract text from chunk-like object (body or text attribute)."""
    if hasattr(chunk, "body") and getattr(chunk, "body") is not None:
        return str(getattr(chunk, "body"))
    if hasattr(chunk, "text") and getattr(chunk, "text") is not None:
        return str(getattr(chunk, "text"))
    return str(chunk)


async def init_embedding(manager: Any) -> None:
    """Create and attach embedding client to manager. Raises on failure if enabled."""
    if not manager.embedding_enabled:
        return
    from .svo_client_manager_ssl import embedding_client_ssl_kwargs, service_use_tls

    root = manager._root_path
    ssl_enabled = service_use_tls(
        manager._embedding_protocol,
        root=root,
        cert_file=manager._embedding_cert_file,
        key_file=manager._embedding_key_file,
        ca_cert_file=manager._embedding_ca_cert_file,
        crl_file=manager._embedding_crl_file,
    )
    base_url = (
        f"https://{manager._embedding_url}"
        if ssl_enabled
        else f"http://{manager._embedding_url}"
    )
    client_kwargs: dict[str, Any] = {}
    if manager._embedding_timeout:
        client_kwargs["timeout"] = manager._embedding_timeout
    client_kwargs.update(
        embedding_client_ssl_kwargs(
            root=root,
            protocol=manager._embedding_protocol,
            cert_file=manager._embedding_cert_file,
            key_file=manager._embedding_key_file,
            ca_cert_file=manager._embedding_ca_cert_file,
            crl_file=manager._embedding_crl_file,
            check_hostname=manager._embedding_check_hostname,
        )
    )
    manager._embedding_client = ClientFactory.create_client(
        base_url=base_url,
        port=manager._embedding_port,
        auth_method="none",
        ssl_enabled=ssl_enabled,
        **client_kwargs,
    )
    await manager._embedding_client.__aenter__()
    logger.info(
        "SVOClientManager initialized with real embedding service "
        "(url=%s:%s, protocol=%s, vector_dim=%s)",
        manager._embedding_url,
        manager._embedding_port,
        manager._embedding_protocol,
        manager.vector_dim,
    )


async def close_embedding(manager: Any) -> None:
    """Close embedding client and set manager._embedding_client to None."""
    if not manager._embedding_client:
        return
    try:
        await manager._embedding_client.__aexit__(None, None, None)
    except Exception as e:
        logger.warning("Error closing embedding client: %s", e, exc_info=True)
    finally:
        manager._embedding_client = None


async def get_embeddings(
    manager: Any, chunks: Iterable[Any], **kwargs: Any
) -> List[Any]:
    """Get embeddings for chunks using embedding service; mutates chunks with .embedding."""
    manager._maybe_transition()
    chunks_list = list(chunks)
    if not chunks_list:
        return []
    if not manager._embedding_client or not manager.embedding_enabled:
        raise RuntimeError(
            "Embedding service is not available or not enabled. "
            "Ensure code_analysis.embedding.enabled=true and service is running."
        )
    try:
        texts: list[str] = [get_chunk_text(ch) for ch in chunks_list]
        # Use the embed_client high-level ``embed(wait=True)``: it runs the embed
        # in-process on the service (``embed_execute`` — no queue, no WS command
        # session) and returns ``{"results": [{"embedding": [...], "body": ...}],
        # "model", "dimension"}``. This parses multi-text BATCHES correctly and
        # avoids the per-call queued-command latency that tripped the server
        # sync-cap on large revectorize runs. (Previously this used the low-level
        # ``cmd`` + a home-grown normalizer that only handled single-text.)
        resp = await manager._embedding_client.embed(
            texts, wait=True, wait_timeout=EMBED_WAIT_TIMEOUT_SECONDS
        )
        if not isinstance(resp, dict):
            raise ValueError(
                f"Invalid embedding service response: not a dict (resp={resp!r})"
            )
        results = resp.get("results")
        if isinstance(results, list):
            embeddings = [
                r.get("embedding") if isinstance(r, dict) else None for r in results
            ]
        elif isinstance(resp.get("embeddings"), list):
            embeddings = resp["embeddings"]
        else:
            raise ValueError(
                "Embedding service returned no results/embeddings: "
                f"keys={list(resp.keys())}"
            )
        if len(embeddings) != len(chunks_list):
            raise ValueError(
                "Embedding service returned unexpected count: "
                f"expected {len(chunks_list)}, got {len(embeddings)}"
            )
        model = resp.get("model")
        for ch, emb in zip(chunks_list, embeddings):
            if emb is not None:
                setattr(ch, "embedding", emb)
                if model is not None:
                    setattr(ch, "embedding_model", model)
        manager._record_success()
        return chunks_list
    except Exception as e:
        manager._record_failure()
        err_str = str(e).lower()
        is_unavailable = (
            "connection" in err_str
            or "timeout" in err_str
            or "unavailable" in err_str
            or "failed after" in err_str
        )
        if is_unavailable:
            if manager._embedding_available:
                logger.warning("⚠️  Embedding service is now unavailable: %s", e)
                manager._embedding_available = False
                manager._embedding_status_logged = True
            elif not manager._embedding_status_logged:
                logger.warning("⚠️  Embedding service is unavailable: %s", e)
                manager._embedding_status_logged = True
            else:
                manager._embedding_status_logged = False
        else:
            logger.error(
                "Failed to get embeddings from real service: %s", e, exc_info=True
            )
        raise
