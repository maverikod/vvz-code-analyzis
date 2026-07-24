"""
Static regression coverage for boolean-literal rewriting in PostgreSQL partial-index
WHERE clauses (1.6.76 deploy incident #2).

The incident: ``psycopg.errors.UndefinedFunction: operator does not exist: boolean =
integer`` on ``idx_files_content_stale`` (WHERE ``... AND content_stale = 1``).
``content_stale`` is a BOOLEAN column (``schema_definition_tables_core.py``), but its
partial-index WHERE clause used the SQLite-integer-literal shape ``content_stale = 1``
(``schema_definition_indexes.py``). ``_index_where_sqlite_to_pg`` already rewrote
``deleted = 0/1`` for PostgreSQL but did not generalize to other BOOLEAN columns, so a
fresh PostgreSQL bootstrap (not just an upgrade) crash-looped on this index.

Fix: ``_index_where_sqlite_to_pg`` now rewrites ``<col> = 0/1`` for ANY column that
``_boolean_columns_for_table`` reports as BOOLEAN for the index's table (derived from
the schema definition, not a hardcoded column-name list), while leaving genuinely
INTEGER columns using the same textual shape (``needs_chunking = 1``) untouched.

These tests are static (no database) and run in every environment, including sandboxes
without a live PostgreSQL server. They complement, and do not replace,
``test_postgres_schema_bootstrap_real_pg.py``'s live-PostgreSQL end-to-end coverage
(gated on ``CODE_ANALYSIS_POSTGRES_TEST_DSN``): a fake/mocked connection like the one
in ``test_postgres_schema_bootstrap_upgrade_path.py`` only tracks column EXISTENCE, so
it is structurally blind to this class of bug (a TYPE mismatch) -- it would accept
``content_stale = 1`` against a real BOOLEAN column without complaint. Only asserting
against the actual generated DDL text (here) or a real PostgreSQL server (the other
file) can catch it.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Any, Dict

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database.schema_sync_models import IndexDef
from code_analysis.core.database.schema_sync_sql_postgres import (
    _boolean_columns_for_table,
    _index_where_sqlite_to_pg,
    generate_create_index_sql_postgres,
)

# Any bare `<identifier> = 0` / `<identifier> = 1` left in generated PostgreSQL DDL.
_BOOL_EQ_INT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(0|1)\b")


def _schema() -> Dict[str, Any]:
    return get_schema_definition()


def test_content_stale_is_boolean_typed_in_the_files_table() -> None:
    """Pin down the root-cause premise: content_stale really is BOOLEAN."""
    schema = _schema()
    bool_cols = _boolean_columns_for_table(schema, "files")
    assert "content_stale" in bool_cols
    assert "deleted" in bool_cols


def test_content_stale_index_where_clause_rewritten_for_postgres() -> None:
    """The exact incident index: content_stale = 1 -> content_stale IS TRUE."""
    schema = _schema()
    idx = next(
        i for i in schema["indexes"] if i["name"] == "idx_files_content_stale"
    )
    idef = IndexDef(
        name=idx["name"],
        table=idx["table"],
        columns=list(idx["columns"]),
        unique=bool(idx.get("unique")),
        where_clause=idx.get("where_clause"),
    )
    sql = generate_create_index_sql_postgres(idef, schema)

    assert "content_stale = 1" not in sql
    assert "content_stale IS TRUE" in sql


def test_needs_chunking_integer_literal_is_left_unchanged() -> None:
    """needs_chunking is INTEGER (not BOOLEAN): `= 1` must survive the rewrite."""
    schema = _schema()
    idx = next(
        i for i in schema["indexes"] if i["name"] == "idx_files_needs_indexing"
    )
    idef = IndexDef(
        name=idx["name"],
        table=idx["table"],
        columns=list(idx["columns"]),
        unique=bool(idx.get("unique")),
        where_clause=idx.get("where_clause"),
    )
    sql = generate_create_index_sql_postgres(idef, schema)

    assert "needs_chunking = 1" in sql
    assert "needs_chunking IS TRUE" not in sql


def test_no_boolean_column_compared_to_integer_literal_in_any_generated_index() -> (
    None
):
    """Class-level guard: scan EVERY schema-definition index's generated PostgreSQL
    DDL and fail loudly if any column known to be BOOLEAN for that index's table is
    still compared to a bare 0/1 literal after the rewrite. Catches this bug class
    for any future partial index, not just the two indexes named above."""
    schema = _schema()
    offenders = []
    for idx in schema["indexes"]:
        if not idx.get("where_clause"):
            continue
        idef = IndexDef(
            name=idx["name"],
            table=idx["table"],
            columns=list(idx["columns"]),
            unique=bool(idx.get("unique")),
            where_clause=idx["where_clause"],
        )
        sql = generate_create_index_sql_postgres(idef, schema)
        bool_cols = _boolean_columns_for_table(schema, idx["table"])
        for match in _BOOL_EQ_INT_RE.finditer(sql):
            col = match.group(1)
            if col in bool_cols:
                offenders.append((idx["name"], sql))

    assert offenders == [], (
        "BOOLEAN column(s) still compared to an integer literal in generated "
        f"PostgreSQL index DDL: {offenders}"
    )


def test_generalized_rewrite_handles_an_arbitrary_boolean_column_name() -> None:
    """Direct unit check that the rewrite is column-set-driven, not name-hardcoded:
    an unrelated made-up boolean column name is rewritten just like `deleted` /
    `content_stale`, proving there is no hardcoded second column name to keep in
    sync by hand."""
    where = "(some_other_flag = 0 OR some_other_flag IS NULL) AND counter = 1"
    rewritten = _index_where_sqlite_to_pg(where, boolean_columns={"some_other_flag"})

    assert "some_other_flag IS FALSE" in rewritten
    assert "counter = 1" in rewritten  # counter is not in boolean_columns: unchanged


def test_legacy_call_without_schema_definition_still_handles_deleted() -> None:
    """Back-compat: a caller that has not been updated to pass schema_definition
    still gets the pre-fix `deleted` rewrite (documented fallback), so this change
    is non-breaking for any not-yet-migrated caller."""
    idef = IndexDef(
        name="idx_x",
        table="files",
        columns=["project_id"],
        unique=False,
        where_clause="deleted = 1",
    )
    sql = generate_create_index_sql_postgres(idef)  # no schema_definition passed
    assert "deleted IS TRUE" in sql
