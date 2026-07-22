"""
Fail-loud regression test for run_migrate_schema (bug f6671fae).

``run_migrate_schema`` used to wrap each of the four per-migration submodule
calls (watch_dirs_server_instance, watch_dirs_deleted_column,
projects_root_segment_postgres, projects_root_path_per_server_instance) in a
blanket ``try/except Exception: logger.warning(...)`` — swallowing real
migration failures instead of surfacing them. This test proves a raising
migration now propagates instead of being silently logged away.

Uses a DB-free stub (no SQLite/PostgreSQL fixtures) so it stays independent
of the SQLite removal happening in parallel.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from code_analysis.core.database.schema_creation_migrate import run_migrate_schema


class _StubDbNoTables:
    """Minimal db-like stub satisfying run_migrate_schema's driver surface.

    All DDL/DML calls are no-ops; table introspection always reports "no
    columns / no matching row", so every idempotent ADD-COLUMN/CREATE-INDEX
    branch is exercised as a no-op without touching a real database.
    """

    driver_type = "postgres"

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """No-op DDL/DML execution."""
        return None

    def _commit(self) -> None:
        """No-op commit."""
        return None

    def _fetchone(self, sql: str, params: Optional[tuple] = None) -> Any:
        """Always report 'not found' (no index/table pre-exists)."""
        return None

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Report no columns for any table (every ADD COLUMN branch is a no-op)."""
        return []


def test_run_migrate_schema_propagates_watch_dirs_server_instance_error() -> None:
    """A raising watch_dirs_server_instance migration must NOT be swallowed."""
    db = _StubDbNoTables()
    boom = RuntimeError("simulated migration failure: watch_dirs_server_instance")

    with patch(
        "code_analysis.core.database.migrations.watch_dirs_server_instance."
        "migrate_watch_dirs_server_instance",
        side_effect=boom,
    ):
        with pytest.raises(RuntimeError, match="simulated migration failure"):
            run_migrate_schema(db)


def test_run_migrate_schema_propagates_watch_dirs_deleted_column_error() -> None:
    """A raising watch_dirs_deleted_column migration must NOT be swallowed."""
    db = _StubDbNoTables()
    boom = RuntimeError("simulated migration failure: watch_dirs_deleted_column")

    with patch(
        "code_analysis.core.database.migrations.watch_dirs_deleted_column."
        "migrate_watch_dirs_deleted_column",
        side_effect=boom,
    ):
        with pytest.raises(RuntimeError, match="simulated migration failure"):
            run_migrate_schema(db)


def test_run_migrate_schema_propagates_projects_root_segment_postgres_error() -> None:
    """A raising projects_root_segment_postgres migration must NOT be swallowed."""
    db = _StubDbNoTables()
    boom = RuntimeError("simulated migration failure: projects_root_segment_postgres")

    with patch(
        "code_analysis.core.database.migrations.projects_root_segment_postgres."
        "migrate_projects_root_segment_postgres",
        side_effect=boom,
    ):
        with pytest.raises(RuntimeError, match="simulated migration failure"):
            run_migrate_schema(db)


def test_run_migrate_schema_propagates_projects_root_path_per_server_instance_error() -> None:
    """A raising projects_root_path_per_server_instance migration must NOT be swallowed."""
    db = _StubDbNoTables()
    boom = RuntimeError(
        "simulated migration failure: projects_root_path_per_server_instance"
    )

    with patch(
        "code_analysis.core.database.migrations.projects_root_path_per_server_instance."
        "migrate_projects_root_path_per_server_instance",
        side_effect=boom,
    ):
        with pytest.raises(RuntimeError, match="simulated migration failure"):
            run_migrate_schema(db)
