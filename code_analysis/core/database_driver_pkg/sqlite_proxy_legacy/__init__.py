"""
Legacy SQLite proxy (former ``core.db_driver`` IPC stack).

In-process worker SQLite for schema tests: import
``sqlite_proxy_legacy.legacy_sqlite`` (``SQLiteDriver``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .sqlite_proxy import SQLiteDriverProxy

__all__ = ["SQLiteDriverProxy"]
