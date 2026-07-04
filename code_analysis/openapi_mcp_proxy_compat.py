"""
Normalize OpenAPI 3.1 schemas for MCP Proxy command discovery.

The proxy's JsonRpcClient schema parser (mcp_proxy_adapter) expects ``type`` to be
a string. Pydantic/FastAPI can emit nullable unions as ``type: ["string", "null"]``,
which makes ``_map_type`` use the list as a dict key and raises
``TypeError: unhashable type: 'list'``, so registration fails with
"returned no commands via get_methods()".

Concurrent ``GET /openapi.json`` calls used to invoke CustomOpenAPIGenerator on
every request (no lock, no cache). That race could corrupt POST /api/jsonrpc body
validation (HTTP 422 with app config in Pydantic ``input``). Generation is now
serialized and cached per app instance.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
import threading
from typing import Any

_openapi_lock = threading.Lock()
_cached_openapi_by_app: dict[int, dict[str, Any]] = {}


def normalize_openapi_types_for_mcp_proxy(obj: Any) -> Any:
    """
    Recursively rewrite ``type`` keys that are lists (nullable unions) to a single
    OpenAPI 3.0-style string (first non-``null`` entry, else ``string``).
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if key == "type" and isinstance(val, list):
                non_null = [x for x in val if x != "null"]
                out[key] = non_null[0] if non_null else "string"
            else:
                out[key] = normalize_openapi_types_for_mcp_proxy(val)
        return out
    if isinstance(obj, list):
        return [normalize_openapi_types_for_mcp_proxy(x) for x in obj]
    return obj


def invalidate_openapi_cache(app: Any | None = None) -> None:
    """Drop cached OpenAPI schema (all apps, or one app after command reload)."""
    with _openapi_lock:
        if app is None:
            _cached_openapi_by_app.clear()
        else:
            _cached_openapi_by_app.pop(id(app), None)
        if app is not None and hasattr(app, "openapi_schema"):
            app.openapi_schema = None


def patch_app_openapi_for_mcp_proxy(app: Any) -> None:
    """Wrap ``app.openapi``: thread-safe cache + MCP Proxy type normalization."""
    orig = app.openapi

    def _wrapped() -> Any:
        """Return wrapped."""
        app_id = id(app)
        with _openapi_lock:
            cached = _cached_openapi_by_app.get(app_id)
            if cached is not None:
                return copy.deepcopy(cached)
            schema = orig()
            normalized = normalize_openapi_types_for_mcp_proxy(schema)
            stored = copy.deepcopy(normalized)
            _cached_openapi_by_app[app_id] = stored
            app.openapi_schema = stored
            return copy.deepcopy(stored)

    app.openapi = _wrapped


def prime_openapi_cache(app: Any) -> None:
    """Generate and cache the normalized OpenAPI schema during app construction."""
    app.openapi()
