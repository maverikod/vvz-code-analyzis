"""
Bootstrap mcp-proxy-adapter logging before any adapter import.

The adapter's ``setup_logging()`` defaults to ``./logs``. Production configs set
``server.log_dir`` (e.g. ``/var/log/casmgr``). Resolve that path from
``CASMGR_LOG``, ``--config``, or ``CASMGR_CONFIG`` **before** any
``mcp_proxy_adapter`` import.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path

_PATCHED = False


def _resolve_log_dir() -> str | None:
    from code_analysis.core.server_log_dir import (
        append_server_startup_log,
        resolve_server_log_dir,
    )

    log_dir = resolve_server_log_dir()
    if log_dir is None:
        return None
    append_server_startup_log(
        log_dir,
        f"bootstrap: redirecting mcp-proxy-adapter logs to {log_dir}",
    )
    return str(log_dir)


def _install_os_log_dir_hooks(log_root_abs: str) -> None:
    """Redirect adapter-relative ``./logs`` paths to ``log_root_abs``."""
    if getattr(os, "_ca_log_dir_hooks", False):
        return

    orig_join = os.path.join
    orig_exists = os.path.exists
    orig_makedirs = os.makedirs

    def join(first: str, *parts: str) -> str:
        if first in ("./logs", "logs"):
            return orig_join(log_root_abs, *parts)
        return orig_join(first, *parts)

    def exists(path: object) -> bool:
        if path in ("./logs", "logs"):
            return orig_exists(log_root_abs)
        return orig_exists(path)  # type: ignore[arg-type]

    def makedirs(name: object, *margs: object, **mkwargs: object) -> None:
        if name in ("./logs", "logs"):
            orig_makedirs(log_root_abs, *margs, **mkwargs)  # type: ignore[arg-type]
            return
        orig_makedirs(name, *margs, **mkwargs)  # type: ignore[arg-type]

    os.path.join = join  # type: ignore[assignment]
    os.path.exists = exists
    os.makedirs = makedirs
    os._ca_log_dir_hooks = True  # type: ignore[attr-defined]


def install_mcp_adapter_log_dir() -> None:
    """
    Patch ``os.path`` helpers so adapter ``setup_logging()`` uses the configured log dir.

    Must run before **any** ``mcp_proxy_adapter`` import. Idempotent.
    """
    global _PATCHED
    if _PATCHED:
        return

    log_root = _resolve_log_dir()
    if not log_root:
        return

    log_root_abs = os.path.abspath(log_root)
    try:
        os.makedirs(log_root_abs, exist_ok=True)
    except OSError as exc:
        from code_analysis.core.server_log_dir import append_server_startup_log

        append_server_startup_log(
            Path(log_root_abs).parent,
            f"bootstrap: FAILED to create log dir {log_root_abs}: {exc}",
        )
        return

    _install_os_log_dir_hooks(log_root_abs)
    _PATCHED = True
