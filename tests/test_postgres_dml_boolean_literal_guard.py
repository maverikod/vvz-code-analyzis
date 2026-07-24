"""
Static, DB-free regression coverage for boolean-literal-in-DML (incident #3,
1.6.77 deploy: ``UPDATE files SET content_stale = 0`` -> ``operator does not
exist: boolean = integer`` / ``column "content_stale" is of type boolean but
expression is of type integer``).

This is the DML-side sibling of ``test_postgres_index_boolean_where_rewrite.py``
(1a29738f, which guards the partial-index WHERE-clause DDL side; incident #2).
Same methodology: derive the authoritative BOOLEAN-column set from the schema
definition (not a hand-maintained name list) and assert every chokepoint that
touches boolean columns in DML agrees with it.

Two independent chokepoints turned out to need this discipline:

1. ``postgres_run._BOOL_COL_INT_ASSIGN`` -- the column allowlist
   ``_adapt_sqlite_bool_int_assignments_for_postgres`` rewrites ``<col> = 0/1``
   for, inside ``_adapt_sqlite_dml_for_postgres``. EVERY statement passed to
   ``driver.execute()`` / ``driver.execute_batch()`` (``run_execute`` /
   ``run_execute_batch``) is routed through this exactly once before reaching
   PostgreSQL -- this is the actual incident #3 root cause: ``content_stale``
   (added later, for bug 56c23bd9) was BOOLEAN in the schema but missing from
   this allowlist.

2. ``postgres_operations._PG_BOOL_COLUMNS`` -- the analogous allowlist for the
   dict-based ``driver.insert()`` / ``.update()`` / ``.select()`` API
   (``_coerce_pg_boolean_values`` / ``_postgres_where_clauses``). Had the same
   gap, latent (no live caller currently passes a bare 0/1 for those columns
   through this path), fixed defensively in the same change.

These tests run in every environment, including sandboxes without a live
PostgreSQL server, and complement (do not replace)
``tests/test_postgres_file_sync_dml_real_pg.py``'s live-PostgreSQL end-to-end
coverage, which proves the reproduction and the fix against a real server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, Set

from code_analysis.core.database.schema_definition import get_schema_definition

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CODE_ROOT = _REPO_ROOT / "code_analysis"

# schema_definition_indexes.py legitimately keeps the pre-rewrite SQLite-integer
# shape (e.g. ``"where_clause": "deleted = 1"``) as INPUT that
# generate_create_index_sql_postgres / _index_where_sqlite_to_pg rewrite at
# generation time (see test_postgres_index_boolean_where_rewrite.py) -- not raw
# SQL ever handed to a database connection, so it is intentionally excluded here.
_EXCLUDED_FILES = {_CODE_ROOT / "core" / "database" / "schema_definition_indexes.py"}

# Calls whose first positional argument is raw SQL text handed to the database.
_EXEC_CALL_NAMES = {"execute", "execute_batch", "_execute"}


def _schema_boolean_columns() -> Set[str]:
    """Every column the schema definition marks BOOLEAN, across all tables."""
    schema = get_schema_definition()
    cols: Set[str] = set()
    for table_def in schema.get("tables", {}).values():
        for col in table_def.get("columns", []):
            if (col.get("type") or "").upper().strip() in ("BOOLEAN", "BOOL"):
                cols.add(col["name"])
    return cols


def test_schema_boolean_columns_includes_all_seven_known_columns() -> None:
    """Pin down the root-cause premise: these seven columns are BOOLEAN in the
    schema (incident #3 -- content_stale, is_abstract, has_pass,
    has_not_implemented -- plus the three already covered by incident #1/#2's
    fixes -- deleted, has_docstring, processing_paused)."""
    cols = _schema_boolean_columns()
    assert cols == {
        "deleted",
        "has_docstring",
        "processing_paused",
        "content_stale",
        "is_abstract",
        "has_pass",
        "has_not_implemented",
    }


def test_postgres_run_bool_col_int_assign_covers_every_schema_boolean_column() -> (
    None
):
    """``postgres_run._BOOL_COL_INT_ASSIGN`` (the execute()/execute_batch()
    chokepoint allowlist) must cover every BOOLEAN column in the schema. This is
    the exact set that was incomplete for incident #3: content_stale was BOOLEAN
    in the schema but absent from this tuple, so raw ``content_stale = 0/1`` DML
    was never rewritten before hitting PostgreSQL."""
    from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
        _BOOL_COL_INT_ASSIGN,
    )

    schema_cols = _schema_boolean_columns()
    allowlist = set(_BOOL_COL_INT_ASSIGN)
    missing = schema_cols - allowlist
    assert missing == set(), (
        f"BOOLEAN column(s) in the schema but missing from "
        f"postgres_run._BOOL_COL_INT_ASSIGN (will NOT be rewritten before "
        f"execute()/execute_batch() -- incident #3 class): {sorted(missing)}"
    )


def test_postgres_operations_bool_columns_covers_every_schema_boolean_column() -> (
    None
):
    """``postgres_operations._PG_BOOL_COLUMNS`` (the insert()/update()/select()
    dict-API chokepoint allowlist) must cover every BOOLEAN column in the
    schema, for the same reason as the execute() allowlist above."""
    from code_analysis.core.database_driver_pkg.drivers.postgres_operations import (
        _PG_BOOL_COLUMNS,
    )

    schema_cols = _schema_boolean_columns()
    missing = schema_cols - set(_PG_BOOL_COLUMNS)
    assert missing == set(), (
        f"BOOLEAN column(s) in the schema but missing from "
        f"postgres_operations._PG_BOOL_COLUMNS (will NOT be coerced by "
        f"insert()/update()/select()): {sorted(missing)}"
    )


def test_adapt_bool_int_assignments_rewrites_every_schema_boolean_column() -> None:
    """Functional check (not just set membership): the adapter actually rewrites
    ``<col> = 0`` / ``<col> = 1`` to ``FALSE``/``TRUE`` for EVERY schema BOOLEAN
    column, proving the allowlist is wired to real rewrite behavior, not just
    present as an unused constant."""
    from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
        _adapt_sqlite_bool_int_assignments_for_postgres,
    )

    for col in sorted(_schema_boolean_columns()):
        false_sql = _adapt_sqlite_bool_int_assignments_for_postgres(
            f"UPDATE t SET {col} = 0 WHERE id = ?"
        )
        true_sql = _adapt_sqlite_bool_int_assignments_for_postgres(
            f"UPDATE t SET {col} = 1 WHERE id = ?"
        )
        assert f"{col} = FALSE" in false_sql, (col, false_sql)
        assert f"{col} = TRUE" in true_sql, (col, true_sql)


def _iter_repo_py_files() -> Any:
    for path in sorted(_CODE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path in _EXCLUDED_FILES:
            continue
        yield path


def _find_boolean_literal_dml_offenders(bool_cols: Set[str]) -> list:
    """Scan every ``.execute()``/``.execute_batch()``/``._execute()`` call's first
    (SQL) argument across the whole ``code_analysis/`` tree via the AST (not raw
    text grep -- avoids false positives on comments/docstrings that merely
    *mention* SQL shapes, e.g. ``"deleted=1 are NOT marked..."`` in a docstring)
    for a bare ``<bool_col> = 0`` / ``= 1`` literal. f-strings are unparsed back
    to their literal source shape (``ast.unparse``), so ``f"...{expr}..."``
    interpolation holes do not themselves false-positive, while any *literal*
    ``col = 0`` text embedded around them still matches.
    """
    pat = re.compile(
        r"\b(" + "|".join(re.escape(c) for c in sorted(bool_cols)) + r")\s*=\s*[01]\b"
    )
    offenders = []
    for path in _iter_repo_py_files():
        try:
            src = path.read_text()
            tree = ast.parse(src, filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None
            )
            if name not in _EXEC_CALL_NAMES or not node.args:
                continue
            try:
                text = ast.unparse(node.args[0])
            except Exception:
                continue
            for m in pat.finditer(text):
                offenders.append((str(path.relative_to(_REPO_ROOT)), node.lineno, m.group(0)))
    return offenders


def test_no_boolean_column_literal_in_any_execute_call_across_the_codebase() -> None:
    """Class-level permanent guard (mirrors the index-DDL guard from 1a29738f,
    extended to DML): scan EVERY ``execute()``/``execute_batch()``/``_execute()``
    call site across the whole ``code_analysis/`` tree and fail loudly if any
    schema BOOLEAN column is still assigned/compared to a bare integer 0/1
    literal. Catches this bug class for any future call site, not just the ones
    fixed for incident #3."""
    offenders = _find_boolean_literal_dml_offenders(_schema_boolean_columns())
    assert offenders == [], (
        "BOOLEAN column(s) compared/assigned to a bare integer literal in a "
        f"raw SQL execute() call (incident #3 class): {offenders}"
    )


def test_guard_scanner_detects_a_synthetic_offender() -> None:
    """Prove the scanner in the test above is not vacuously passing: a
    synthetic ``driver.execute(f"UPDATE files SET content_stale = 0 ...")``
    call must be detected by the same regex/AST logic."""
    pat = re.compile(r"\bcontent_stale\s*=\s*[01]\b")
    src = (
        "def f(driver, file_id):\n"
        '    driver.execute(f"UPDATE files SET content_stale = 0 WHERE id = ?", (file_id,))\n'
    )
    tree = ast.parse(src)
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _EXEC_CALL_NAMES
            and node.args
        ):
            found.extend(pat.findall(ast.unparse(node.args[0])))
    assert found == ["content_stale = 0"]
