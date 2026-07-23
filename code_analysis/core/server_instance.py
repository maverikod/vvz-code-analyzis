"""
Current code-analysis server instance identity (shared-DB partition key).

Config is read from ``core`` only (never from ``commands``) so workers and the DB
driver process can resolve ``registration.instance_uuid`` without breaking the
command → DatabaseClient → driver → DB chain.

The config-file-backed resolution (``get_server_instance_id()`` called without an
explicit ``config``) is memoized for the process lifetime: ``registration.instance_uuid``
never changes without a process restart, but this function is called once per project
per file-watcher cycle (and from many other per-request call sites), so a naive
implementation re-parses ``config.json`` (commentjson + lark grammar) on every call —
observed as a 100% CPU config-reparse storm, amplified per-project-per-cycle
(bug 9f5d860e). Use ``reset_server_instance_id_cache()`` in tests / hot-reload paths
that must force a fresh disk load.

Deferred hardening (NOT implemented here): an mtime-keyed ``load_raw_config`` cache
that would auto-invalidate on config-file changes. Out of scope for this fix — see
bug 9f5d860e follow-up notes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def _resolve_active_config_path() -> Path:
    """Resolve server ``config.json`` (same rules as daemon / workers)."""
    try:
        from mcp_proxy_adapter.config import get_config

        cfg = get_config()
        cfg_path = getattr(cfg, "config_path", None)
        if isinstance(cfg_path, str) and cfg_path.strip():
            return Path(cfg_path).expanduser().resolve()
    except Exception:
        pass
    env_cfg = os.environ.get("CASMGR_CONFIG", "").strip()
    if env_cfg:
        return Path(env_cfg).expanduser().resolve()
    return (Path.cwd() / "config.json").resolve()


def server_instance_id_from_config(config: Mapping[str, Any]) -> str:
    """Return ``registration.instance_uuid`` from a loaded config mapping."""
    reg = config.get("registration")
    if not isinstance(reg, Mapping):
        return ""
    return str(reg.get("instance_uuid") or "").strip()


def _require_sid(sid: str) -> str:
    """Return ``sid`` unchanged, or raise if the resolved instance id is empty."""
    if not sid:
        raise RuntimeError(
            "registration.instance_uuid is required in server config "
            "(server instance partition key for watch_dirs and projects)"
        )
    return sid


# Process-lifetime memoization of the config-file-backed instance id (mirrors the
# runtime-state pattern in config_state.py: module-level lock + module-level state,
# reset via a dedicated hook, never via reaching into module globals directly).
_cache_lock = threading.Lock()
_cached_server_instance_id: Optional[str] = None
_config_load_count = 0
_cache_hit_count = 0


def get_server_instance_id_cache_diagnostics() -> Dict[str, int]:
    """
    Return counters for the config-file-backed instance-id cache.

    Queryable diagnostics surface (red/green gate for bug 9f5d860e): ``config_load_count``
    increments once per real ``config.json`` disk load (cache miss); ``cache_hit_count``
    increments once per call served from the in-process cache.
    """
    with _cache_lock:
        return {
            "config_load_count": _config_load_count,
            "cache_hit_count": _cache_hit_count,
        }


def reset_server_instance_id_cache() -> None:
    """Clear the memoized instance id and its counters (test / hot-reload hook)."""
    global _cached_server_instance_id, _config_load_count, _cache_hit_count
    with _cache_lock:
        _cached_server_instance_id = None
        _config_load_count = 0
        _cache_hit_count = 0


def get_server_instance_id(*, config: Optional[Mapping[str, Any]] = None) -> str:
    """
    Return this server's instance UUID (global partition key for watch_dirs/projects).

    Resolution order when ``config`` is omitted:
    1. ``CODE_ANALYSIS_SERVER_INSTANCE_ID`` environment variable (never loads/caches)
    2. ``registration.instance_uuid`` from active ``config.json`` — loaded from disk
       (commentjson + lark parse) at most ONCE per process; subsequent calls are
       served from an in-process cache. Use ``reset_server_instance_id_cache()`` to
       force a fresh load (tests, hot-reload).

    An explicit ``config`` argument ALWAYS bypasses the cache (used by callers that
    already hold a freshly loaded/validated config, e.g. config revalidation paths).
    """
    if config is not None:
        return _require_sid(server_instance_id_from_config(config))

    env_sid = os.environ.get("CODE_ANALYSIS_SERVER_INSTANCE_ID", "").strip()
    if env_sid:
        return env_sid

    global _cached_server_instance_id, _config_load_count, _cache_hit_count
    with _cache_lock:
        cached = _cached_server_instance_id
        if cached is not None:
            _cache_hit_count += 1
            return cached

    from code_analysis.core.storage_paths import load_raw_config

    loaded_config = load_raw_config(_resolve_active_config_path())
    sid = _require_sid(server_instance_id_from_config(loaded_config))

    with _cache_lock:
        _cached_server_instance_id = sid
        _config_load_count += 1
    return sid
