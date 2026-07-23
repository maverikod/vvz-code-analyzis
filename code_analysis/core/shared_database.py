"""
Thread-safe holder for the long-lived database connection in the MCP server process.

One connection for the whole application; it is closed only when the application
shuts down (via close_shared_database()). Commands must not close it.

get_shared_database() returns a proxy that forwards all calls to the real client
except disconnect(), which is a no-op so command code can keep calling
database.disconnect() in finally blocks without closing the shared connection.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional, cast

# Driver-direct (stage 2): DatabaseClient class removed; the shared object held
# here is a duck-typed driver-shaped instance (PostgreSQLDriver in production).
# Kept as an ``Any`` alias so existing type annotations do not need per-site rewrites.
DatabaseClient = Any

_lock = threading.Lock()
_client: Optional[DatabaseClient] = None
_owner_pid: Optional[int] = None


class SharedDatabaseNotInitializedError(Exception):
    """Raised when get_shared_database() is called but no client has been set.

    The shared database must be set at server startup before any command runs.
    """

    def __init__(self, message: str = "Shared database is not initialized") -> None:
        """Initialize the instance."""
        super().__init__(message)


class _SharedDatabaseProxy:
    """Proxy that forwards all attribute/method access to the real client except disconnect().

    disconnect() is a no-op so that command code can call database.disconnect()
    in finally blocks without closing the long-lived shared connection.
    """

    __slots__ = ("_client",)

    def __init__(self, client: DatabaseClient) -> None:
        """Initialize the instance."""
        self._client = client

    def disconnect(self) -> None:
        """No-op: do not close the shared connection when commands call disconnect()."""
        pass

    def __getattr__(self, name: str) -> Any:
        """Forward all other attribute and method access to the wrapped client."""
        return getattr(self._client, name)


def set_shared_database(client: DatabaseClient) -> None:
    """Store the long-lived database client in the thread-safe holder.

    Called once at server startup after the connection is opened.
    Thread-safe; overwrites if already set.

    Args:
        client: The real DatabaseClient instance (not a proxy).
    """
    global _client, _owner_pid
    with _lock:
        _client = client
        _owner_pid = os.getpid()


def is_shared_database_current_process() -> bool:
    """Return True when shared DB is initialized for the current process."""
    with _lock:
        return _client is not None and _owner_pid == os.getpid()


def get_shared_database() -> DatabaseClient:
    """Return a proxy to the shared database client.

    The proxy forwards all methods to the real client except disconnect(),
    which is a no-op. Commands can safely call database.disconnect() in finally.

    Returns:
        A proxy implementing the DatabaseClient interface (disconnect is no-op).

    Raises:
        SharedDatabaseNotInitializedError: If no client has been set (e.g. before
            startup completed or after shutdown).
    """
    with _lock:
        if _client is None:
            raise SharedDatabaseNotInitializedError()
        if _owner_pid != os.getpid():
            raise SharedDatabaseNotInitializedError(
                "Shared database is initialized in a different process"
            )
        return cast(DatabaseClient, _SharedDatabaseProxy(_client))


def shared_database_status() -> str:
    """Return ``"ok"`` when the shared DB is set for this process, else ``"unavailable"``.

    Bug c5e8fb49 (boot race): health visibility. Before this, ``health`` had no
    way to reflect a shared DB that failed to bootstrap (or was never set) — it
    reported ``ok`` while ``get_shared_database()`` would raise
    ``SharedDatabaseNotInitializedError`` for every command. Cheap, read-only
    (reuses ``is_shared_database_current_process()``'s own check), safe to call
    from a health probe on every request.
    """
    return "ok" if is_shared_database_current_process() else "unavailable"


def close_shared_database() -> None:
    """Disconnect the real shared client and clear the holder.

    Called at server shutdown. Idempotent: safe to call when already closed/cleared.
    """
    global _client, _owner_pid
    with _lock:
        if _client is not None:
            try:
                _client.disconnect()
            except Exception:
                pass
            _client = None
        _owner_pid = None
