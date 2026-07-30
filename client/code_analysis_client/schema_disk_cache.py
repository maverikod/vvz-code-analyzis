"""
Cross-process on-disk cache for per-command JSON schemas (bug 8e6acb34, Fix 1).

Root cause this addresses: :meth:`CodeAnalysisAsyncClient.get_command_schema`
already memoizes a schema for the lifetime of one client instance
(``self._command_schema_cache``), but that in-memory cache starts empty on
every new process. Most real callers (one-shot CLI invocations, the
``pipeline`` live checks, individual agent tool calls) construct a fresh
:class:`~code_analysis_client.client.CodeAnalysisAsyncClient`, call a command
once, and exit -- so the in-memory cache never pays for itself and every
single ``call_validated``/``commands.<name>()`` invocation pays a full extra
``help(cmdname)`` network round trip before the actual command call.

Measured on the deployed server (192.168.254.26:15010), warm TCP connection,
first ``call_validated("health", {})`` on a fresh client instance (schema
cache miss) vs the same call with schema already cached in memory: the
``help`` round trip costs ~2.7ms median -- matching bug 8e6acb34's reported
~3.0ms "our own wrapper" figure almost exactly. This module removes that
network round trip on repeat runs by persisting each fetched schema to a
small JSON file on local disk, keyed by (server base URL, command name),
with a bounded TTL so a stale schema is never trusted for long after a
server-side deploy changes it.

This does NOT weaken validation: the exact same schema shape is used either
way, just fetched from local disk instead of the network when it is still
fresh. ``refresh=True`` (existing :meth:`get_command_schema` parameter) and
:meth:`CodeAnalysisAsyncClient.clear_command_schema_cache` (which now also
purges the on-disk entries for that server) remain the explicit invalidation
paths for when a caller knows the server's command schemas changed (e.g.
after ``reload``).

Configuration (env vars, all optional):
    ``CODE_ANALYSIS_CLIENT_SCHEMA_CACHE_DIR`` -- override the cache root
        (default: ``~/.cache/code_analysis_client/schema``).
    ``CODE_ANALYSIS_CLIENT_SCHEMA_CACHE_TTL_SECONDS`` -- override the
        freshness window (default: 300 seconds -- long enough to amortize
        the round trip across a short-lived process's calls and across
        back-to-back process invocations, short enough that a schema change
        shipped by a deploy is picked up within five minutes without any
        explicit action).
    ``CODE_ANALYSIS_CLIENT_DISABLE_SCHEMA_CACHE`` -- set to ``1``/``true`` to
        disable on-disk caching entirely and fall back to the original
        per-instance-only, always-network behavior.

Every function here is best-effort: any I/O or (de)serialization failure is
swallowed and treated as a cache miss / no-op. A broken or unwritable cache
directory must never break a command call, only forfeit the speedup.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

_ENV_CACHE_DIR = "CODE_ANALYSIS_CLIENT_SCHEMA_CACHE_DIR"
_ENV_TTL_SECONDS = "CODE_ANALYSIS_CLIENT_SCHEMA_CACHE_TTL_SECONDS"
_ENV_DISABLE = "CODE_ANALYSIS_CLIENT_DISABLE_SCHEMA_CACHE"

_DEFAULT_TTL_SECONDS = 300.0
_TRUTHY = {"1", "true", "yes", "on"}


def _disabled() -> bool:
    """Return True when on-disk schema caching is disabled via env var."""
    return os.environ.get(_ENV_DISABLE, "").strip().lower() in _TRUTHY


def _cache_root() -> Optional[Path]:
    """Return the configured cache root directory, or None when disabled."""
    if _disabled():
        return None
    override = os.environ.get(_ENV_CACHE_DIR)
    if override:
        return Path(override)
    return Path.home() / ".cache" / "code_analysis_client" / "schema"


def _ttl_seconds() -> float:
    """Return the configured freshness window in seconds."""
    raw = os.environ.get(_ENV_TTL_SECONDS)
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_TTL_SECONDS


def _server_dir(root: Path, base_url: str) -> Path:
    """Return the per-server subdirectory for ``base_url`` under ``root``."""
    server_key = hashlib.sha256(base_url.encode("utf-8")).hexdigest()[:16]
    return root / server_key


def _safe_command_filename(command: str) -> str:
    """Return a filesystem-safe file name for ``command``."""
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in command)
    return f"{safe}.json"


def _entry_path(base_url: str, command: str) -> Optional[Path]:
    """Return the cache file path for (base_url, command), or None if disabled/invalid.

    ``base_url`` must be a real string (a mock or other stand-in used by
    tests is not, and is deliberately treated as "caching unavailable" so
    unit tests exercising a mocked transport never touch the filesystem).
    """
    if not isinstance(base_url, str) or not base_url or not isinstance(command, str):
        return None
    root = _cache_root()
    if root is None:
        return None
    return _server_dir(root, base_url) / _safe_command_filename(command)


def load_cached_schema(base_url: str, command: str) -> Optional[Dict[str, Any]]:
    """Return a fresh-enough disk-cached schema for (base_url, command), else None.

    Args:
        base_url: The server's base URL (``JsonRpcClient.base_url``), used as
            the cache partition key.
        command: Command name whose schema is wanted.

    Returns:
        The cached schema dict when a readable, unexpired entry exists;
        ``None`` on any cache miss, staleness, or I/O/parse failure.
    """
    path = _entry_path(base_url, command)
    if path is None:
        return None
    try:
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    fetched_at = raw.get("fetched_at")
    schema = raw.get("schema")
    if not isinstance(fetched_at, (int, float)) or not isinstance(schema, dict):
        return None
    if (time.time() - fetched_at) > _ttl_seconds():
        return None
    return schema


def store_cached_schema(base_url: str, command: str, schema: Dict[str, Any]) -> None:
    """Best-effort persist ``schema`` for (base_url, command) to local disk.

    Writes to a process-unique temp file first and renames it over the final
    path (atomic on the same filesystem) so a concurrent reader never sees a
    partially written file. Never raises: a write failure only forfeits the
    speedup, it must not break the calling command.

    Args:
        base_url: The server's base URL, used as the cache partition key.
        command: Command name the schema belongs to.
        schema: The schema dict to persist (as returned by the server's
            ``help`` command for this command name).
    """
    path = _entry_path(base_url, command)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp_path.write_text(
            json.dumps({"fetched_at": time.time(), "schema": schema}),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except OSError:
        return


def clear_cached_schemas(base_url: str) -> None:
    """Best-effort delete every on-disk cached schema entry for ``base_url``.

    Args:
        base_url: The server's base URL whose cached entries should be
            forgotten (e.g. after the caller learns the server reloaded its
            command definitions).
    """
    if not isinstance(base_url, str) or not base_url:
        return
    root = _cache_root()
    if root is None:
        return
    server_dir = _server_dir(root, base_url)
    try:
        if not server_dir.exists():
            return
        for entry in server_dir.iterdir():
            try:
                entry.unlink()
            except OSError:
                continue
    except OSError:
        return
