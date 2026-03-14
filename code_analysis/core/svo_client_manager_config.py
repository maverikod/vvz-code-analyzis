"""
SVO client manager configuration.

Builds configuration dict for SVOClientManager from server config.
Extracts chunker/embedding/circuit-breaker settings and certificate paths.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def to_dict(cfg: Any) -> dict[str, Any]:
    """Convert config model/dict into a plain dict."""
    if cfg is None:
        return {}
    if isinstance(cfg, dict):
        return cfg
    if hasattr(cfg, "to_dict") and callable(getattr(cfg, "to_dict")):
        try:
            return dict(cfg.to_dict())
        except Exception:
            pass
    if hasattr(cfg, "dict") and callable(getattr(cfg, "dict")):
        try:
            return dict(cfg.dict())
        except Exception:
            pass
    try:
        return dict(vars(cfg))
    except Exception:
        return {}


def build_config(
    server_config: Any, root_dir: None | Path | str = None
) -> dict[str, Any]:
    """
    Build SVOClientManager attribute dict from server config.

    Args:
        server_config: Parsed config model or dict (code_analysis section).
        root_dir: Optional root directory for resolving relative paths.

    Returns:
        Dict of attribute names to values for SVOClientManager.__init__.
    """
    cfg = to_dict(server_config)
    if "code_analysis" in cfg:
        ca_cfg = cfg.get("code_analysis") or {}
    else:
        ca_cfg = cfg

    if hasattr(ca_cfg, "chunker") and hasattr(ca_cfg, "embedding"):
        chunker_cfg = to_dict(ca_cfg.chunker) if ca_cfg.chunker else {}
        emb_cfg = to_dict(ca_cfg.embedding) if ca_cfg.embedding else {}
    else:
        chunker_cfg = (
            (ca_cfg.get("chunker") or {}).copy() if isinstance(ca_cfg, dict) else {}
        )
        emb_cfg = (
            (ca_cfg.get("embedding") or {}).copy() if isinstance(ca_cfg, dict) else {}
        )

    if not isinstance(chunker_cfg, dict):
        chunker_cfg = to_dict(chunker_cfg) if chunker_cfg else {}
    if not isinstance(emb_cfg, dict):
        emb_cfg = to_dict(emb_cfg) if emb_cfg else {}

    worker_dict = (
        to_dict(ca_cfg.worker) if hasattr(ca_cfg, "worker") and ca_cfg.worker else {}
    )
    if not isinstance(worker_dict, dict):
        worker_dict = to_dict(worker_dict) if worker_dict else {}
    worker_cfg = (worker_dict.get("circuit_breaker") or {}).copy()

    vector_dim_raw = (
        getattr(ca_cfg, "vector_dim", None)
        if not isinstance(ca_cfg, dict)
        else ca_cfg.get("vector_dim")
    )
    vector_dim = int(vector_dim_raw or 384)
    chunker_enabled = bool(chunker_cfg.get("enabled", False))
    embedding_enabled = bool(emb_cfg.get("enabled", False))
    log_chunker_trace = bool(
        getattr(ca_cfg, "log_vectorization_chunker_trace", False)
        if not isinstance(ca_cfg, dict)
        else ca_cfg.get("log_vectorization_chunker_trace", False)
    )

    root_path: Path | None = None
    if root_dir:
        root_path = Path(root_dir)
    elif "code_analysis" in cfg:
        db_path = (
            getattr(ca_cfg, "db_path", None)
            if not isinstance(ca_cfg, dict)
            else ca_cfg.get("db_path")
        )
        if db_path:
            root_path = Path(db_path).parent.parent
        else:
            log_path = (
                getattr(ca_cfg, "log", None)
                if not isinstance(ca_cfg, dict)
                else ca_cfg.get("log")
            )
            if log_path:
                root_path = Path(log_path).parent.parent

    chunker_timeout_val = chunker_cfg.get("timeout")
    chunker_timeout = float(
        chunker_timeout_val if chunker_timeout_val is not None else 120.0
    )

    return {
        "_root_dir": Path(root_dir) if root_dir else None,
        "vector_dim": vector_dim,
        "chunker_enabled": chunker_enabled,
        "embedding_enabled": embedding_enabled,
        "_log_chunker_trace": log_chunker_trace,
        "failure_threshold": int(worker_cfg.get("failure_threshold", 5)),
        "recovery_timeout": float(worker_cfg.get("recovery_timeout", 60.0)),
        "success_threshold": int(worker_cfg.get("success_threshold", 2)),
        "initial_backoff": float(worker_cfg.get("initial_backoff", 5.0)),
        "max_backoff": float(worker_cfg.get("max_backoff", 300.0)),
        "backoff_multiplier": float(worker_cfg.get("backoff_multiplier", 2.0)),
        "_config": cfg,
        "_chunker_url": str(
            chunker_cfg.get("url") or chunker_cfg.get("host") or "localhost"
        ),
        "_chunker_port": int(chunker_cfg.get("port", 8009)),
        "_chunker_protocol": str(chunker_cfg.get("protocol", "http")),
        "_chunker_cert_file": chunker_cfg.get("cert_file"),
        "_chunker_key_file": chunker_cfg.get("key_file"),
        "_chunker_ca_cert_file": chunker_cfg.get("ca_cert_file"),
        "_chunker_crl_file": chunker_cfg.get("crl_file"),
        "_chunker_timeout": chunker_timeout,
        "_chunker_check_hostname": bool(chunker_cfg.get("check_hostname", False)),
        "_embedding_url": str(emb_cfg.get("url") or emb_cfg.get("host") or "localhost"),
        "_embedding_port": int(emb_cfg.get("port", 8001)),
        "_embedding_protocol": str(emb_cfg.get("protocol", "http")),
        "_embedding_cert_file": emb_cfg.get("cert_file"),
        "_embedding_key_file": emb_cfg.get("key_file"),
        "_embedding_ca_cert_file": emb_cfg.get("ca_cert_file"),
        "_embedding_crl_file": emb_cfg.get("crl_file"),
        "_embedding_timeout": emb_cfg.get("timeout"),
        "_embedding_check_hostname": bool(emb_cfg.get("check_hostname", False)),
        "_root_path": root_path,
    }
