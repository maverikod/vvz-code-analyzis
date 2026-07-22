"""
Block C (step 06): mid tables use logical UUID; SQLite TEXT; PostgreSQL native UUID DDL.

Polymorphic Option A: ``entity_type`` + ``entity_id`` (UUID) without FK on ``entity_id``.
Does not substitute for Block E (data migration).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.core.database.schema_definition_tables_mid import get_tables_mid
from code_analysis.core.database.schema_sync_sql_postgres import (
    generate_create_table_sql_postgres,
)


def _wrapped(table_name: str) -> dict:
    """Return wrapped."""
    return {
        "tables": {table_name: get_tables_mid()[table_name]},
        "indexes": [],
        "virtual_tables": [],
    }


_UUID_MID_TABLES = (
    "imports",
    "issues",
    "usages",
    "code_content",
    "ast_trees",
    "cst_trees",
    "vector_index",
    "code_chunks",
)


def test_mid_primary_keys_are_logical_uuid_without_autoincrement() -> None:
    """Verify test mid primary keys are logical uuid without autoincrement."""
    tables = get_tables_mid()
    for tname in _UUID_MID_TABLES:
        tbl = tables[tname]
        id_col = next(c for c in tbl["columns"] if c["name"] == "id")
        assert id_col["type"] == "UUID", f"{tname}.id must be UUID, got {id_col!r}"
        assert not id_col.get("autoincrement"), f"{tname}.id must not autoincrement"


def test_mid_foreign_key_columns_to_core_are_uuid() -> None:
    """Verify test mid foreign key columns to core are uuid."""
    tables = get_tables_mid()
    imp = {c["name"]: c for c in tables["imports"]["columns"]}
    assert imp["file_id"]["type"] == "UUID"

    iss = {c["name"]: c for c in tables["issues"]["columns"]}
    for name in ("file_id", "project_id", "class_id", "function_id", "method_id"):
        assert iss[name]["type"] == "UUID", iss[name]

    chunk = {c["name"]: c for c in tables["code_chunks"]["columns"]}
    assert chunk["file_id"]["type"] == "UUID"
    assert chunk["project_id"]["type"] == "UUID"
    for name in ("class_id", "function_id", "method_id"):
        assert chunk[name]["type"] == "UUID", chunk[name]

    ast_t = {c["name"]: c for c in tables["ast_trees"]["columns"]}
    assert ast_t["file_id"]["type"] == "UUID"
    assert ast_t["project_id"]["type"] == "UUID"


def test_polymorphic_entity_id_option_a_uuid_no_entity_fk() -> None:
    """Option A: entity_id is UUID; interpretation is via entity_type (no FK on entity_id)."""
    tables = get_tables_mid()
    cc = tables["code_content"]
    cc_fk_cols = {tuple(fk["columns"]) for fk in cc["foreign_keys"]}
    assert cc_fk_cols == {("file_id",)}
    ent = next(c for c in cc["columns"] if c["name"] == "entity_id")
    assert ent["type"] == "UUID"

    vi = tables["vector_index"]
    vi_fk_cols = {tuple(fk["columns"]) for fk in vi["foreign_keys"]}
    assert vi_fk_cols == {("project_id",)}
    vi_ent = next(c for c in vi["columns"] if c["name"] == "entity_id")
    assert vi_ent["type"] == "UUID"


def test_vector_id_stays_integer() -> None:
    """Verify test vector id stays integer."""
    tables = get_tables_mid()
    v = {c["name"]: c for c in tables["vector_index"]["columns"]}
    assert v["vector_id"]["type"] == "INTEGER"
    c = {c["name"]: c for c in tables["code_chunks"]["columns"]}
    assert c["vector_id"]["type"] == "INTEGER"


def test_step_06_unique_constraints_preserved() -> None:
    """Verify test step 06 unique constraints preserved."""
    tables = get_tables_mid()
    assert {"columns": ["file_id", "ast_hash"]} in tables["ast_trees"][
        "unique_constraints"
    ]
    assert {"columns": ["file_id", "cst_hash"]} in tables["cst_trees"][
        "unique_constraints"
    ]
    assert {"columns": ["project_id", "entity_type", "entity_id"]} in tables[
        "vector_index"
    ]["unique_constraints"]
    assert {"columns": ["chunk_uuid"]} in tables["code_chunks"]["unique_constraints"]


@pytest.mark.parametrize(
    "table",
    (
        "imports",
        "issues",
        "code_chunks",
        "vector_index",
        "code_content",
        "ast_trees",
    ),
)
def test_postgres_ddl_uses_native_uuid_primary_key(table: str) -> None:
    """Verify test postgres ddl uses native uuid primary key."""
    sd = _wrapped(table)
    ddl = generate_create_table_sql_postgres(sd, table)
    up = ddl.upper()
    assert " UUID " in up or "UUID PRIMARY KEY" in up
    assert "AUTOINCREMENT" not in up
    assert "GENERATED" not in ddl


def test_postgres_code_chunks_file_id_uuid_and_chunk_uuid_unique() -> None:
    """Verify test postgres code chunks file id uuid and chunk uuid unique."""
    sd = _wrapped("code_chunks")
    ddl = generate_create_table_sql_postgres(sd, "code_chunks")
    assert "file_id UUID" in ddl
    assert "UNIQUE (chunk_uuid)" in ddl


def test_postgres_vector_index_entity_triple_unique() -> None:
    """Verify test postgres vector index entity triple unique."""
    sd = _wrapped("vector_index")
    ddl = generate_create_table_sql_postgres(sd, "vector_index")
    assert "UNIQUE (project_id, entity_type, entity_id)" in ddl
    assert "entity_id UUID" in ddl
