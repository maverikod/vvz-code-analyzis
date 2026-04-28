"""
Block B (step 05): core tables use logical UUID; SQLite TEXT; PostgreSQL native UUID DDL.

Does not substitute for Block C (mid FK types) or Block E (data migration).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.core.database.schema_definition_tables_core import get_tables_core
from code_analysis.core.database.schema_sync_sql import generate_create_table_sql
from code_analysis.core.database.schema_sync_sql_postgres import (
    generate_create_table_sql_postgres,
)


def _wrapped_core() -> dict:
    return {"tables": get_tables_core(), "indexes": [], "virtual_tables": []}


_UUID_CORE_TABLES = (
    "watch_dirs",
    "watch_dir_paths",
    "projects",
    "files",
    "classes",
    "methods",
    "functions",
    "entity_cross_ref",
)


def test_core_identity_columns_are_logical_uuid() -> None:
    tables = get_tables_core()
    for tname in _UUID_CORE_TABLES:
        tbl = tables[tname]
        for col in tbl["columns"]:
            if col["name"] == "id":
                assert col["type"] == "UUID", f"{tname}.id must be UUID, got {col!r}"
                assert not col.get(
                    "autoincrement"
                ), f"{tname}.id must not autoincrement"
    by_name = {c["name"]: c for c in tables["files"]["columns"]}
    assert by_name["project_id"]["type"] == "UUID"
    assert by_name["watch_dir_id"]["type"] == "UUID"
    by_name_c = {c["name"]: c for c in tables["classes"]["columns"]}
    assert by_name_c["file_id"]["type"] == "UUID"
    xref = tables["entity_cross_ref"]
    for col in xref["columns"]:
        if col["name"] in ("ref_type", "line", "created_at"):
            continue
        assert col["type"] == "UUID", f"entity_cross_ref.{col['name']}: {col!r}"


def test_projects_watch_dirs_logical_uuid_stable_no_autoincrement() -> None:
    tables = get_tables_core()
    p = tables["projects"]["columns"]
    w = tables["watch_dirs"]["columns"][0]
    assert any(c["name"] == "id" and c["type"] == "UUID" for c in p)
    assert w["type"] == "UUID" and not w.get("autoincrement")


def test_files_unique_project_path_preserved() -> None:
    uc = get_tables_core()["files"]["unique_constraints"]
    assert {"columns": ["project_id", "path"]} in uc


def test_core_fk_graph_uuid_targets() -> None:
    tables = get_tables_core()
    files_fk = {
        tuple(fk["columns"]): fk["references_table"]
        for fk in tables["files"]["foreign_keys"]
    }
    assert files_fk[("project_id",)] == "projects"
    assert files_fk[("watch_dir_id",)] == "watch_dirs"

    classes_fk = tables["classes"]["foreign_keys"][0]
    assert classes_fk["references_columns"] == ["id"]
    assert classes_fk["references_table"] == "files"

    ec = tables["entity_cross_ref"]
    targets = {fk["references_table"] for fk in ec["foreign_keys"]}
    assert targets == {"classes", "methods", "functions", "files"}


@pytest.mark.parametrize("table", _UUID_CORE_TABLES)
def test_sqlite_ddl_maps_uuid_to_text(table: str) -> None:
    sd = _wrapped_core()
    ddl = generate_create_table_sql(sd, table).upper()
    assert "UUID" not in ddl, ddl
    assert "TEXT" in ddl


@pytest.mark.parametrize(
    "table",
    ("files", "classes", "functions", "methods", "entity_cross_ref", "projects"),
)
def test_postgres_ddl_uses_native_uuid_not_integer_identity(table: str) -> None:
    sd = _wrapped_core()
    ddl = generate_create_table_sql_postgres(sd, table)
    up = ddl.upper()
    assert " UUID " in up or up.startswith("CREATE") and "UUID" in ddl
    assert "GENERATED" not in ddl and "IDENTITY" not in up
    assert "AUTOINCREMENT" not in up


def test_postgres_files_ddl_unique_and_fk() -> None:
    sd = _wrapped_core()
    ddl = generate_create_table_sql_postgres(sd, "files")
    assert "UNIQUE (project_id, path)" in ddl
    assert "REFERENCES projects(id)" in ddl
    assert "REFERENCES watch_dirs(id)" in ddl


def test_postgres_entity_cross_ref_fk_columns_uuid() -> None:
    sd = _wrapped_core()
    ddl = generate_create_table_sql_postgres(sd, "entity_cross_ref")
    for frag in (
        "REFERENCES classes(id)",
        "REFERENCES methods(id)",
        "REFERENCES functions(id)",
        "REFERENCES files(id)",
    ):
        assert frag in ddl
