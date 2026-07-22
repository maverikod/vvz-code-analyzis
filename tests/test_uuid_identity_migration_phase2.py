"""
Block E step 09: Phase 1-2 UUID migration mapping.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid

from code_analysis.core.database.migrations.uuid_identity_migration_postgres import (
    create_mapping_tables_postgres,
)


def test_postgres_migration_ddl_contains_uuid_columns() -> None:
    """Verify test postgres migration ddl contains uuid columns."""
    ddl = "\n".join(create_mapping_tables_postgres())
    assert "uuid_migration_files" in ddl
    assert "uuid_migration_indexing_errors" in ddl
    assert " UUID " in ddl


def test_preflight_execute_only_db_like_rpc_client() -> None:
    """Preflight must rely on generic ``execute`` only (no private ``_fetchone`` on RPC clients)."""
    from code_analysis.core.database.migrations.uuid_identity_migration_common import (
        run_uuid_migration_preflight_phase1,
    )

    pid = str(uuid.uuid4())
    wid = str(uuid.uuid4())

    class _ExecuteOnlyDb:
        """Represent ExecuteOnlyDb."""

        _driver_type = "postgresql"

        def execute(self, sql: str, params=None):
            """Execute the command."""
            s = " ".join(sql.split()).lower()
            if "count(*)" in s and " from projects" in s and "files" not in s:
                return {"data": [{"n": 1}]}
            if "count(*)" in s and " from watch_dirs" in s:
                return {"data": [{"n": 1}]}
            if "select id from projects" in s:
                return {"data": [{"id": pid}]}
            if "select id from watch_dirs" in s:
                return {"data": [{"id": wid}]}
            if "from files f" in s and "left join projects" in s:
                return {"data": [{"n": 0}]}
            raise AssertionError(f"unexpected sql in fake db: {sql!r}")

    rep = run_uuid_migration_preflight_phase1(_ExecuteOnlyDb(), check_orphan_fks=True)
    assert rep.projects_uuid_ok is True
    assert rep.watch_dirs_uuid_ok is True
    assert not any("Skipping UUID" in w for w in rep.warnings)
    assert not any("_fetchone" in w for w in rep.warnings)
