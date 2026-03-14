"""
Embedding (embed-client) operations for SVOClientManager.

Initialization, close, and get_embeddings. Manager is passed as first argument.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, List

logger = logging.getLogger(__name__)

try:
    from embed_client.client_factory import ClientFactory

    EMBED_CLIENT_AVAILABLE = True
except ImportError:
    ClientFactory = None
    EMBED_CLIENT_AVAILABLE = False


def get_chunk_text(chunk: Any) -> str:
    """Extract text from chunk-like object (body or text attribute)."""
    if hasattr(chunk, "body") and getattr(chunk, "body") is not None:
        return str(getattr(chunk, "body"))
    if hasattr(chunk, "text") and getattr(chunk, "text") is not None:
        return str(getattr(chunk, "text"))
    return str(chunk)


async def init_embedding(manager: Any) -> None:
    """Create and attach embedding client to manager. Raises on failure if enabled."""
    if not manager.embedding_enabled or not EMBED_CLIENT_AVAILABLE:
        if not manager.embedding_enabled:
            raise RuntimeError(
                "Embedding service is disabled in configuration. "
                "Set code_analysis.embedding.enabled=true to enable."
            )
        raise RuntimeError(
            "embed_client library is not available. Install it to use embedding service."
        )
    root = manager._root_path
    if manager._embedding_protocol in ("mtls", "https"):
        base_url = f"https://{manager._embedding_url}"
    else:
        base_url = f"http://{manager._embedding_url}"
    client_kwargs: dict[str, Any] = {}
    if manager._embedding_timeout:
        client_kwargs["timeout"] = manager._embedding_timeout
    ssl_enabled = manager._embedding_protocol in ("mtls", "https")
    if ssl_enabled and manager._embedding_protocol == "mtls":
        if manager._embedding_cert_file and manager._embedding_key_file:
            cert_path = Path(manager._embedding_cert_file)
            key_path = Path(manager._embedding_key_file)
            if not cert_path.is_absolute() and root:
                cert_path = root / cert_path
            if not key_path.is_absolute() and root:
                key_path = root / key_path
            client_kwargs["cert_file"] = str(cert_path.resolve())
            client_kwargs["key_file"] = str(key_path.resolve())
        if manager._embedding_ca_cert_file:
            ca = Path(manager._embedding_ca_cert_file)
            if not ca.is_absolute() and root:
                ca = root / ca
            client_kwargs["ca_cert_file"] = str(ca.resolve())
        if manager._embedding_crl_file:
            crl = Path(manager._embedding_crl_file)
            if not crl.is_absolute() and root:
                crl = root / crl
            client_kwargs["crl_file"] = str(crl.resolve())
    elif ssl_enabled and manager._embedding_ca_cert_file:
        ca = Path(manager._embedding_ca_cert_file)
        if not ca.is_absolute() and root:
            ca = root / ca
        client_kwargs["ca_cert_file"] = str(ca.resolve())
    if ssl_enabled:
        client_kwargs["verify"] = manager._embedding_check_hostname
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
        result = await manager._embedding_client.cmd(
            command="embed", params={"texts": texts}
        )
        if not result or "result" not in result:
            raise ValueError(
                f"Invalid embedding service response: result structure is invalid (result={result})"
            )
        result_data = result["result"]
        if not result_data.get("success") or "data" not in result_data:
            err = result_data.get("error", "Unknown error")
            raise ValueError(f"Embedding service error: {err}")
        data = result_data["data"]
        embeddings = None
        if "embeddings" in data:
            embeddings = data["embeddings"]
        elif "results" in data:
            embeddings = [
                r.get("embedding") if isinstance(r, dict) else None
                for r in data["results"]
            ]
        if not embeddings or len(embeddings) != len(chunks_list):
            raise ValueError(
                "Embedding service returned unexpected format or count mismatch: "
                f"expected {len(chunks_list)} embeddings, got {len(embeddings) if embeddings else 0}"
            )
        for ch, emb in zip(chunks_list, embeddings):
            if emb is not None:
                setattr(ch, "embedding", emb)
                if isinstance(data, dict) and "model" in data:
                    setattr(ch, "embedding_model", data["model"])
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
