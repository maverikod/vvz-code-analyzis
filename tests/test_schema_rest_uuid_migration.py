"""
Block D (steps 07–08): rest tables logical UUID; indexes; PostgreSQL partial predicates.

Does not substitute Block E (data migration) or runtime CRUD (Block F).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database.schema_definition_indexes import (
    get_schema_indexes,
    get_schema_virtual_tables,
)
from code_analysis.core.database.schema_definition_tables_rest import get_tables_rest
from code_analysis.core.database.schema_sync_models import IndexDef
from code_analysis.core.database.schema_sync_sql_postgres import (
    _index_where_sqlite_to_pg,
    generate_create_index_sql_postgres,
    generate_create_table_sql_postgres,
)


def _wrapped(table_name: str) -> dict:
    """Return wrapped."""
    return {
        "tables": {table_name: get_tables_rest()[table_name]},
        "indexes": [],
        "virtual_tables": [],
    }


_UUID_REST_TABLES = (
    "code_duplicates",
    "duplicate_occurrences",
    "comprehensive_analysis_results",
    "indexing_errors",
    "file_tree_snapshots",
    "file_tree_snapshot_roots",
    "file_tree_snapshot_nodes",
)

_REST_TABLES_WITH_ROW_ID = (
    "code_duplicates",
    "duplicate_occurrences",
    "comprehensive_analysis_results",
    "indexing_errors",
    "file_tree_snapshots",
    "file_tree_snapshot_nodes",
)


def test_rest_identity_and_core_fk_columns_are_logical_uuid() -> None:
    """Verify test rest identity and core fk columns are logical uuid."""
    tables = get_tables_rest()
    for tname in _REST_TABLES_WITH_ROW_ID:
        tbl = tables[tname]
        id_col = next(c for c in tbl["columns"] if c["name"] == "id")
        assert id_col["type"] == "UUID", f"{tname}.id: {id_col!r}"
        assert not id_col.get("autoincrement"), f"{tname}.id must not autoincrement"

    dup_o = {c["name"]: c for c in tables["duplicate_occurrences"]["columns"]}
    assert dup_o["duplicate_id"]["type"] == "UUID"
    assert dup_o["file_id"]["type"] == "UUID"
    assert dup_o["ast_node_id"]["type"] == "INTEGER"

    car = {c["name"]: c for c in tables["comprehensive_analysis_results"]["columns"]}
    assert car["file_id"]["type"] == "UUID"
    assert car["project_id"]["type"] == "UUID"

    fts_tbl = {c["name"]: c for c in tables["file_tree_snapshots"]["columns"]}
    assert fts_tbl["file_id"]["type"] == "UUID"
    assert fts_tbl["project_id"]["type"] == "UUID"

    roots = tables["file_tree_snapshot_roots"]["columns"]
    assert next(c for c in roots if c["name"] == "snapshot_id")["type"] == "UUID"

    nodes = {c["name"]: c for c in tables["file_tree_snapshot_nodes"]["columns"]}
    assert nodes["snapshot_id"]["type"] == "UUID"
    assert nodes["node_id"]["type"] == "TEXT"
    assert nodes["parent_node_id"]["type"] == "TEXT"

    ierr = {c["name"]: c for c in tables["indexing_errors"]["columns"]}
    assert ierr["id"]["type"] == "UUID"
    assert ierr["project_id"]["type"] == "UUID"


def test_stats_and_lock_tables_no_unnecessary_uuid_migration() -> None:
    """Verify test stats and lock tables no unnecessary uuid migration."""
    tables = get_tables_rest()
    for tname in (
        "file_watcher_stats",
        "vectorization_stats",
        "indexing_worker_stats",
    ):
        cols = {c["name"]: c for c in tables[tname]["columns"]}
        assert cols["cycle_id"]["type"] == "TEXT"
        assert cols["cycle_id"]["primary_key"] is True
    pal = {c["name"]: c for c in tables["project_activity_locks"]["columns"]}
    assert pal["project_id"]["type"] == "TEXT"
    assert pal["owner_id"]["type"] == "TEXT"


def test_step_07_unique_constraints_preserved() -> None:
    """Verify test step 07 unique constraints preserved."""
    tables = get_tables_rest()
    assert {"columns": ["project_id", "duplicate_hash"]} in tables["code_duplicates"][
        "unique_constraints"
    ]
    assert {"columns": ["file_id", "file_mtime"]} in tables[
        "comprehensive_analysis_results"
    ]["unique_constraints"]
    assert {"columns": ["file_id"]} in tables["file_tree_snapshots"][
        "unique_constraints"
    ]
    assert {"columns": ["snapshot_id", "node_id"]} in tables[
        "file_tree_snapshot_nodes"
    ]["unique_constraints"]
    assert {"columns": ["snapshot_id", "parent_node_id", "child_index"]} in tables[
        "file_tree_snapshot_nodes"
    ]["unique_constraints"]
    assert {"columns": ["project_id", "file_path"]} in tables["indexing_errors"][
        "unique_constraints"
    ]


def test_snapshot_fk_graph_targets_uuid_columns() -> None:
    """Verify test snapshot fk graph targets uuid columns."""
    tables = get_tables_rest()
    snap_fk = {
        tuple(fk["columns"]): fk for fk in tables["file_tree_snapshots"]["foreign_keys"]
    }
    assert snap_fk[("file_id",)]["references_table"] == "files"
    assert snap_fk[("project_id",)]["references_table"] == "projects"

    root_fk = tables["file_tree_snapshot_roots"]["foreign_keys"][0]
    assert root_fk["references_table"] == "file_tree_snapshots"
    assert root_fk["references_columns"] == ["id"]

    node_fk = tables["file_tree_snapshot_nodes"]["foreign_keys"][0]
    assert node_fk["references_columns"] == ["id"]


@pytest.mark.parametrize(
    "table",
    (
        "code_duplicates",
        "duplicate_occurrences",
        "comprehensive_analysis_results",
        "file_tree_snapshots",
        "file_tree_snapshot_roots",
        "file_tree_snapshot_nodes",
        "indexing_errors",
    ),
)
def test_postgres_ddl_uses_native_uuid_where_expected(table: str) -> None:
    """Verify test postgres ddl uses native uuid where expected."""
    sd = _wrapped(table)
    ddl = generate_create_table_sql_postgres(sd, table)
    up = ddl.upper()
    assert "UUID" in up
    assert "AUTOINCREMENT" not in up
    assert "GENERATED" not in ddl


def test_postgres_duplicate_occurrences_fk_columns_uuid() -> None:
    """Verify test postgres duplicate occurrences fk columns uuid."""
    sd = _wrapped("duplicate_occurrences")
    ddl = generate_create_table_sql_postgres(sd, "duplicate_occurrences")
    assert "duplicate_id UUID" in ddl
    assert "file_id UUID" in ddl
    assert "REFERENCES code_duplicates(id)" in ddl
    assert "REFERENCES files(id)" in ddl


def test_postgres_comprehensive_analysis_unique_file_mtime() -> None:
    """Verify test postgres comprehensive analysis unique file mtime."""
    sd = _wrapped("comprehensive_analysis_results")
    ddl = generate_create_table_sql_postgres(sd, "comprehensive_analysis_results")
    assert "UNIQUE (file_id, file_mtime)" in ddl
    assert "file_id UUID" in ddl


def test_idx_code_chunks_not_vectorized_uses_created_at_not_uuid_order_alone() -> None:
    """Verify test idx code chunks not vectorized uses created at not uuid order alone."""
    indexes = {i["name"]: i for i in get_schema_indexes()}
    idx = indexes["idx_code_chunks_not_vectorized"]
    assert idx["columns"] == ["project_id", "created_at", "id"]
    assert idx["where_clause"] == "vector_id IS NULL"


@pytest.mark.parametrize(
    ("where_sqlite", "expected_substrings"),
    [
        ("deleted = 1", ["deleted IS TRUE"]),
        (
            "(deleted = 0 OR deleted IS NULL) AND needs_chunking = 1",
            ["deleted IS FALSE", "needs_chunking = 1"],
        ),
    ],
)
def test_postgres_partial_index_predicate_maps_boolean_literals(
    where_sqlite: str, expected_substrings: list[str]
) -> None:
    """Verify test postgres partial index predicate maps boolean literals."""
    pg = _index_where_sqlite_to_pg(where_sqlite)
    for s in expected_substrings:
        assert s in pg
    assert "deleted = 1" not in pg
    assert "deleted = 0" not in pg


def test_postgres_partial_index_sql_uses_translated_predicate() -> None:
    """Verify test postgres partial index sql uses translated predicate."""
    idef = IndexDef(
        name="idx_files_deleted",
        table="files",
        columns=["deleted"],
        where_clause="deleted = 1",
    )
    sql = generate_create_index_sql_postgres(idef)
    assert "WHERE deleted IS TRUE" in sql
    assert "deleted = 1" not in sql


def test_postgres_idx_files_needs_indexing_where_clause() -> None:
    """Verify test postgres idx files needs indexing where clause."""
    indexes = {i["name"]: i for i in get_schema_indexes()}
    raw = indexes["idx_files_needs_indexing"]
    idef = IndexDef(
        name=raw["name"],
        table=raw["table"],
        columns=list(raw["columns"]),
        unique=bool(raw.get("unique")),
        where_clause=raw.get("where_clause"),
    )
    sql = generate_create_index_sql_postgres(idef)
    assert "deleted IS FALSE" in sql
    assert "needs_chunking = 1" in sql
    assert "deleted = 0" not in sql


def test_postgres_not_vectorized_index_includes_created_at_in_column_list() -> None:
    """Verify test postgres not vectorized index includes created at in column list."""
    indexes = {i["name"]: i for i in get_schema_indexes()}
    raw = indexes["idx_code_chunks_not_vectorized"]
    idef = IndexDef(
        name=raw["name"],
        table=raw["table"],
        columns=list(raw["columns"]),
        unique=bool(raw.get("unique")),
        where_clause=raw.get("where_clause"),
    )
    sql = generate_create_index_sql_postgres(idef)
    compact = sql.replace(" ", "").lower()
    assert "project_id,created_at,id" in compact
    assert "WHEREvector_idISNULL" in compact or "WHERE vector_id IS NULL" in sql


def test_fts_policy_sqlite_virtual_table_not_ported_to_postgres_ddl_path() -> None:
    """Step 08 Option B/C: FTS5 + rowid stays SQLite-side; PG DDL helpers emit indexes only."""
    vts = get_schema_virtual_tables()
    assert len(vts) == 1
    assert vts[0]["type"] == "fts5"
    assert vts[0]["options"].get("content_rowid") == "rowid"
    idef = IndexDef(
        name="idx_code_content_file",
        table="code_content",
        columns=["file_id"],
        where_clause=None,
    )
    pg_idx = generate_create_index_sql_postgres(idef)
    assert "fts5" not in pg_idx.lower()
    assert "rowid" not in pg_idx.lower()


def test_full_schema_definition_merges_rest_uuid_tables() -> None:
    """Verify test full schema definition merges rest uuid tables."""
    sd = get_schema_definition()
    assert sd["tables"]["code_duplicates"]["columns"][0]["type"] == "UUID"
