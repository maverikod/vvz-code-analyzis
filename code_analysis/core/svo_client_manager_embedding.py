"""
Embedding (embed-client) operations for SVOClientManager.

Initialization, close, and get_embeddings. Manager is passed as first argument.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, cast

logger = logging.getLogger(__name__)

# region agent log
_AGENT_DEBUG_LOG = (
    "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-718d03.log"
)
_AGENT_SESSION = "718d03"


def _agent_debug_log(
    hypothesis_id: str, location: str, message: str, data: Dict[str, Any]
) -> None:
    try:
        payload = {
            "sessionId": _AGENT_SESSION,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_AGENT_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _summarize_embed_cmd_payload(r: Any) -> Dict[str, Any]:
    """Safe shape summary for embed ``cmd`` responses (no secrets)."""
    if not isinstance(r, dict):
        return {"payload_type": type(r).__name__}
    out: Dict[str, Any] = {"top_keys": list(r.keys())}
    if "mode" in r:
        out["mode"] = r.get("mode")
    top = r.get("result")
    if isinstance(top, dict):
        out["result_keys"] = list(top.keys())
        out["success"] = top.get("success")
        err = top.get("error")
        out["error_py_type"] = type(err).__name__
        if isinstance(err, dict):
            out["error_keys"] = list(err.keys())
        elif err is not None:
            out["error_preview"] = str(err)[:200]
        data = top.get("data")
        if isinstance(data, dict):
            out["data_keys"] = list(data.keys())[:40]
    return out


# endregion

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


def _unwrap_embed_execute_payload(raw: Dict[str, Any]) -> None:
    """
    In-place: promote ``result.data.result.data`` into ``result.data`` (queued embed jobs).
    """
    res = raw.get("result")
    if not isinstance(res, dict):
        return
    data = res.get("data")
    if not isinstance(data, dict):
        return
    nested = data.get("result")
    if not isinstance(nested, dict):
        return
    inner = nested.get("data")
    if not isinstance(inner, dict):
        return
    new_data = {k: v for k, v in data.items() if k != "result"}
    new_data.update(inner)
    res["data"] = new_data


def _try_extract_embed_from_job_envelope(top: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Extract ``{results|embeddings, model?}`` when ``result`` is a queued job dict
    without ``success``/``data`` wrapper, e.g. ``{job_id, command, status, result: ...}``.
    """
    inner = top.get("result")
    if not isinstance(inner, dict):
        return None
    d = inner.get("data")
    if isinstance(d, dict) and ("results" in d or "embeddings" in d):
        return dict(d)
    if "results" in inner or "embeddings" in inner:
        return dict(inner)
    synthetic = {"result": {"success": True, "data": dict(top)}}
    _unwrap_embed_execute_payload(synthetic)
    res = synthetic.get("result")
    if not isinstance(res, dict):
        return None
    ud = res.get("data")
    if isinstance(ud, dict) and ("results" in ud or "embeddings" in ud):
        return dict(ud)
    return None


def _normalize_embed_cmd_response(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce embed ``cmd`` response variants to a single dict with ``results`` and optional ``model``.
    """
    # region agent log
    _agent_debug_log(
        "A",
        "svo_client_manager_embedding._normalize_embed_cmd_response",
        "entry",
        {"summary": _summarize_embed_cmd_payload(result)},
    )
    # endregion
    # Queued completion: model/results at ``result`` without ``success`` envelope.
    if result.get("mode") == "queued" and isinstance(result.get("result"), dict):
        inner = result["result"]
        if "results" in inner:
            return dict(inner)

    if "result" not in result:
        raise ValueError(
            f"Invalid embedding service response: missing result (result={result})"
        )

    top = result["result"]
    if not isinstance(top, dict):
        raise ValueError("Invalid embedding service response: result is not a dict")

    # embed_client: job completion without top-level success (keys like job_id, status, result)
    if "job_id" in top and "result" in top and top.get("success") is None:
        from_job = _try_extract_embed_from_job_envelope(top)
        if from_job is not None:
            return from_job

    if top.get("success") is False:
        raw_err = top.get("error")
        if "error" in top:
            if isinstance(raw_err, dict):
                msg = (
                    raw_err.get("message")
                    or raw_err.get("code")
                    or raw_err.get("detail")
                )
                if msg is None:
                    msg = (
                        "embedding service reported failure (empty error object)"
                        if not raw_err
                        else str(raw_err)
                    )
            elif raw_err is not None:
                msg = str(raw_err)
            else:
                msg = "embedding service reported failure (error is null)"
            raise ValueError(f"Embedding service error: {msg}")
        raise ValueError("Embedding service error: success=false without error details")

    if top.get("success") is not True:
        data_probe = top.get("data")
        if isinstance(data_probe, dict) and (
            "results" in data_probe
            or "embeddings" in data_probe
            or "embed_execute" in data_probe
        ):
            pass
        else:
            # region agent log
            _agent_debug_log(
                "C",
                "svo_client_manager_embedding._normalize_embed_cmd_response",
                "falsy_success_fallback",
                {
                    "success_value": top.get("success"),
                    "error_present": top.get("error") is not None,
                    "error_repr_type": type(top.get("error")).__name__,
                    "top_keys": list(top.keys()),
                },
            )
            # endregion
            raise ValueError(
                "Embedding service error: expected success=true or data payload; "
                f"success={top.get('success')!r}, top_keys={list(top.keys())}"
            )

    data = top.get("data")
    if not isinstance(data, dict):
        raise ValueError("Embedding service response: missing data")
    data_dict: Dict[str, Any] = data

    ee = data_dict.get("embed_execute")
    if isinstance(ee, dict) and isinstance(ee.get("data"), dict):
        return cast(Dict[str, Any], ee["data"])

    if "result" in data_dict:
        _unwrap_embed_execute_payload(result)
        top2 = result.get("result")
        if isinstance(top2, dict):
            d2 = top2.get("data")
            if isinstance(d2, dict) and ("results" in d2 or "embeddings" in d2):
                return d2

    if "results" in data_dict or "embeddings" in data_dict:
        return data_dict

    # region agent log
    _agent_debug_log(
        "E",
        "svo_client_manager_embedding._normalize_embed_cmd_response",
        "unexpected_data_shape",
        {"data_keys": list(data_dict.keys())},
    )
    # endregion
    raise ValueError(
        "Embedding service returned unexpected data shape: keys="
        f"{list(data_dict.keys())}"
    )


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
    # region agent log
    _agent_debug_log(
        "B",
        "svo_client_manager_embedding.init_embedding",
        "embedding_client_ready",
        {
            "embedding_url": manager._embedding_url,
            "port": manager._embedding_port,
            "protocol": manager._embedding_protocol,
            "ssl_enabled": ssl_enabled,
            "has_embedding_client": manager._embedding_client is not None,
        },
    )
    # endregion
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
        # region agent log
        _agent_debug_log(
            "D",
            "svo_client_manager_embedding.get_embeddings",
            "after_embed_cmd",
            {"summary": _summarize_embed_cmd_payload(result), "texts_n": len(texts)},
        )
        # endregion
        if not result:
            raise ValueError(
                f"Invalid embedding service response: empty (result={result})"
            )
        data = _normalize_embed_cmd_response(result)
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
