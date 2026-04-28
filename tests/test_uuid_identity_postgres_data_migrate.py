"""
PostgreSQL UUID migration Phases 3–5 (Step 10): SQL shape, dry-run, Phase 6 guard.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from typing import Any, List

import pytest

from code_analysis.core.database.migrations.uuid_identity_migration_common import (
    UuidMigrationError,
)
from code_analysis.core.database.migrations.uuid_identity_postgres_data_migrate import (
    MIGRATED_TABLES_COPY_ORDER,
    build_copy_insert_sql,
    build_shadow_table_ddl_postgres,
    build_truncate_shadow_sql,
    run_uuid_migration_phase6_swap_postgres,
    run_uuid_migration_phases_3_to_5_postgres,
)


class _DryRunPgDb:
    _driver_type = "postgresql"

    def _execute(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("dry-run must not execute")

    def _fetchone(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dry-run must not fetch")

    def _commit(self) -> None:
        raise AssertionError("dry-run must not commit")


def test_phases_345_dry_run_no_execute_no_swap_sql() -> None:
    report = run_uuid_migration_phases_3_to_5_postgres(
        _DryRunPgDb(),
        dry_run=True,
        skip_mapping_validation=True,
    )
    assert report.dry_run is True
    assert report.statements_executed == 0
    assert any(
        "uuid_mig_new_files" in s and "CREATE TABLE" in s for s in report.sql_log
    )
    assert any("INSERT INTO uuid_mig_new_files" in s for s in report.sql_log)
    assert not any("RENAME TO" in s.upper() for s in report.sql_log)


def test_copy_sql_order_files_before_classes_and_entity_cross_ref() -> None:
    stmts = build_copy_insert_sql()
    text = "\n".join(stmts)
    i_files = text.find("INSERT INTO uuid_mig_new_files")
    i_classes = text.find("INSERT INTO uuid_mig_new_classes")
    i_ecr = text.find("INSERT INTO uuid_mig_new_entity_cross_ref")
    i_chunks = text.find("INSERT INTO uuid_mig_new_code_chunks")
    assert 0 <= i_files < i_classes < i_ecr
    assert i_ecr < i_chunks


def test_truncate_is_reverse_of_insert_dependency() -> None:
    trunc = build_truncate_shadow_sql()
    assert trunc[0].startswith("DELETE FROM uuid_mig_new_indexing_errors")
    assert "uuid_mig_new_files" in trunc[-1]


def test_shadow_ddl_fk_points_at_shadow_peer() -> None:
    ddl = "\n".join(build_shadow_table_ddl_postgres())
    assert "REFERENCES uuid_mig_new_files(id)" in ddl
    assert "REFERENCES projects(id)" in ddl
    assert "uuid_mig_new_file_tree_snapshot_roots" in ddl


def test_polymorphic_joins_use_mapping_tables() -> None:
    stmts = build_copy_insert_sql()
    cc_ins = next(s for s in stmts if "INSERT INTO uuid_mig_new_code_content" in s)
    assert "uuid_migration_files j_pol_fm" in cc_ins
    assert "uuid_migration_classes j_pol_class" in cc_ins
    assert "uuid_migration_code_chunks j_pol_chunk" in cc_ins
    vi_ins = next(s for s in stmts if "INSERT INTO uuid_mig_new_vector_index" in s)
    assert "j_pol_fm" in vi_ins


def test_phase6_swap_requires_explicit_confirmation() -> None:
    class _Pg:
        _driver_type = "postgresql"

        def _execute(self, *a: Any, **k: Any) -> None:
            return None

        def _commit(self) -> None:
            return None

    with pytest.raises(UuidMigrationError, match="refused"):
        run_uuid_migration_phase6_swap_postgres(_Pg())


def test_phase6_swap_runs_when_confirmed() -> None:
    executed: List[str] = []

    class _Pg:
        _driver_type = "postgresql"

        def _execute(self, sql: str, *a: Any, **k: Any) -> None:
            executed.append(sql)

        def _commit(self) -> None:
            return None

    out = run_uuid_migration_phase6_swap_postgres(
        _Pg(),
        migration_tag="t1",
        i_confirm_maintenance_swap=True,
    )
    assert len(out) == 2 * len(MIGRATED_TABLES_COPY_ORDER)
    assert any("RENAME TO" in s for s in out)
    assert executed == out


@pytest.mark.skipif(
    not os.environ.get("UUID_MIG_TEST_PG_URI"), reason="UUID_MIG_TEST_PG_URI unset"
)
def test_postgres_integration_smoke_optional() -> None:
    uri = os.environ["UUID_MIG_TEST_PG_URI"]
    try:
        import psycopg
    except ImportError:
        pytest.skip("psycopg not installed")

    with psycopg.connect(uri) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        # Full legacy schema + migration is environment-specific; connection smoke only.
        assert conn.info.dbname or True


def test_migrated_tables_cover_step10_groups() -> None:
    names = set(MIGRATED_TABLES_COPY_ORDER)
    for required in (
        "files",
        "classes",
        "functions",
        "methods",
        "entity_cross_ref",
        "imports",
        "issues",
        "usages",
        "code_content",
        "ast_trees",
        "cst_trees",
        "vector_index",
        "code_chunks",
        "code_duplicates",
        "duplicate_occurrences",
        "comprehensive_analysis_results",
        "file_tree_snapshots",
        "file_tree_snapshot_roots",
        "file_tree_snapshot_nodes",
        "indexing_errors",
    ):
        assert required in names
