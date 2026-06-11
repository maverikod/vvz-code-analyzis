"""
Bootstrap mcp-proxy-adapter logging before any adapter import.

The adapter's ``setup_logging()`` defaults to ``./logs``. Under systemd
(``ProtectSystem=strict``, cwd ``/usr/lib/casmgr-server``) that path is not
writable. Redirect to ``CASMGR_LOG`` (production) **before** any
``mcp_proxy_adapter`` import — including ``import mcp_proxy_adapter.core.logging``,
which loads the package ``__init__`` and triggers ``CommandRegistry`` first.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os

_PATCHED = False


def _resolve_log_dir() -> str | None:
    explicit = os.environ.get("CASMGR_LOG") or os.environ.get("MCP_ADAPTER_LOG_DIR")
    if explicit:
        return explicit
    if os.environ.get("CASMGR_CONFIG"):
        return "/var/log/casmgr"
    return None


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
    Patch ``os.path`` helpers so adapter ``setup_logging()`` uses ``CASMGR_LOG``.

    Must run before **any** ``mcp_proxy_adapter`` import. Does not import the
    adapter package (importing ``mcp_proxy_adapter.core.logging`` loads
    ``CommandRegistry`` and calls ``setup_logging()`` too early).

    No-op in development when neither ``CASMGR_LOG`` nor ``CASMGR_CONFIG`` is set.
    Idempotent.
    """
    global _PATCHED
    if _PATCHED:
        return

    log_root = _resolve_log_dir()
    if not log_root:
        return

    log_root_abs = os.path.abspath(log_root)
    os.makedirs(log_root_abs, exist_ok=True)
    _install_os_log_dir_hooks(log_root_abs)
    _PATCHED = True
