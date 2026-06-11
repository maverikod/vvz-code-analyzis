"""PostgreSQL migration SQL uses ``?`` placeholders (driver translates to ``%s``)."""

from __future__ import annotations

import inspect

from code_analysis.core.database.migrations import watch_dirs_server_instance as mod


def test_postgres_primary_key_query_uses_sqlite_qmark_placeholder() -> None:
    source = inspect.getsource(mod._postgres_primary_key_columns)
    assert "relname = ?" in source
    assert "relname = %s" not in source
