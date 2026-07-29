"""
Bug d4cd9525: entity ``end_line`` was never populated by the indexer.

``build_file_data_atomic_batches`` (``core/database_client/file_data_batch.py``
- the single shared entity-row builder used by both the ``update_indexes``
path, via ``sync_file_to_db_atomic``, and the CST/batch write path, via
``update_file_data_atomic_batch``) constructed ``Class``/``Method``/
``Function`` rows with no ``end_line``, even though the ``classes``/
``methods``/``functions`` tables already had a nullable ``end_line`` column
and ``entity_cross_ref_builder.resolve_caller`` already read it for span
matching. Consequence: every indexed entity's span collapsed to its single
``line``, breaking span-based caller resolution for any multi-line entity.

Covers two layers of the fix:
1. The ``Class``/``Function``/``Method`` dataclasses (``core/database_client/
   objects/class_function.py`` and ``.../method_import.py``) now carry an
   ``end_line`` field that round-trips through ``to_db_row``/``from_dict``/
   ``from_db_row``, with backward compatibility for rows that have no
   ``end_line`` key (existing pre-fix data).
2. ``build_file_data_atomic_batches`` populates ``end_line`` from the AST
   node's ``end_lineno`` for every class, function, and method it indexes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Sequence, Tuple

from code_analysis.core.database_client.file_data_batch import (
    build_file_data_atomic_batches,
)
from code_analysis.core.database_client.objects.class_function import Class, Function
from code_analysis.core.database_client.objects.method_import import Method

_FIXTURE_SOURCE = (
    "def multi_line_function(a: int, b: int) -> int:\n"
    '    """Multi-line function body."""\n'
    "    total = a + b\n"
    "    total += 1\n"
    "    return total\n"
    "\n\n"
    "class MultiLineClass:\n"
    '    """Multi-line class body."""\n'
    "\n"
    "    def multi_line_method(self) -> str:\n"
    '        """Multi-line method body."""\n'
    '        value = "one"\n'
    '        value += "-two"\n'
    "        return value\n"
)


def _parse_insert_columns(sql: str) -> List[str]:
    """Parse the column-name list out of an ``INSERT INTO <table> (a, b, ...)`` statement."""
    inside = sql.split("(", 1)[1].split(")", 1)[0]
    return [c.strip() for c in inside.split(",")]


def _find_insert_row(
    batches: Sequence[Sequence[Tuple[str, Any]]], table: str, *, name_value: str
) -> Dict[str, Any]:
    """Find the single INSERT row for ``table`` whose ``name`` column equals ``name_value``.

    Args:
        batches: The ``(sql, params)`` op batches returned by
            :func:`build_file_data_atomic_batches`.
        table: Target table name (e.g. ``"classes"``).
        name_value: Expected value of that row's ``name`` column.

    Returns:
        Mapping of column name to bound param value for the matching row.

    Raises:
        AssertionError: If no matching row is found.
    """
    prefix = f"INSERT INTO {table} ("
    for batch in batches:
        for sql, params in batch:
            if not sql.strip().startswith(prefix):
                continue
            cols = _parse_insert_columns(sql)
            row = dict(zip(cols, params))
            if row.get("name") == name_value:
                return row
    raise AssertionError(
        f"No INSERT INTO {table} row with name={name_value!r} found in batches"
    )


def test_build_file_data_atomic_batches_populates_end_line_for_all_entity_kinds() -> (
    None
):
    """class/function/method rows all carry end_line matching the real AST span."""
    tree = ast.parse(_FIXTURE_SOURCE)
    func_node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "multi_line_function"
    )
    class_node = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    method_node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "multi_line_method"
    )

    batches, meta = build_file_data_atomic_batches(
        file_id="f1",
        project_id="p1",
        source_code=_FIXTURE_SOURCE,
        file_path="fixture_end_line.py",
        file_mtime=0.0,
    )
    assert meta["success"] is True

    class_row = _find_insert_row(batches, "classes", name_value="MultiLineClass")
    func_row = _find_insert_row(
        batches, "functions", name_value="multi_line_function"
    )
    method_row = _find_insert_row(
        batches, "methods", name_value="multi_line_method"
    )

    assert class_row["end_line"] == class_node.end_lineno
    assert func_row["end_line"] == func_node.end_lineno
    assert method_row["end_line"] == method_node.end_lineno

    # Real multi-line bodies: end_line must be strictly past the start line,
    # not just "not None" (a same-line collapse would be an equally broken fix).
    assert class_row["line"] == class_node.lineno
    assert class_row["end_line"] > class_row["line"]
    assert func_row["line"] == func_node.lineno
    assert func_row["end_line"] > func_row["line"]
    assert method_row["line"] == method_node.lineno
    assert method_row["end_line"] > method_row["line"]


def test_build_file_data_atomic_batches_single_line_def_has_consistent_span() -> None:
    """A single-line function/class still gets a real (non-collapsed) end_line.

    Not a regression case for the fix itself, but documents the boundary:
    end_line always reflects the AST's real end_lineno, single-line or not
    (never silently omitted), which is what downstream span consumers
    (entity_cross_ref_builder.resolve_caller) rely on.
    """
    source = "def one_liner(): return 1\n"
    tree = ast.parse(source)
    func_node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))

    batches, meta = build_file_data_atomic_batches(
        file_id="f1",
        project_id="p1",
        source_code=source,
        file_path="fixture_one_liner.py",
        file_mtime=0.0,
    )
    assert meta["success"] is True
    row = _find_insert_row(batches, "functions", name_value="one_liner")
    assert row["end_line"] == func_node.end_lineno == func_node.lineno == row["line"]


def test_class_object_end_line_round_trips_through_db_row() -> None:
    """Class.to_db_row()/from_dict() preserve end_line when set."""
    obj = Class(file_id=1, name="C", line=5, end_line=12)
    row = obj.to_db_row()
    assert row["end_line"] == 12

    restored = Class.from_dict(row)
    assert restored.end_line == 12


def test_class_object_end_line_omitted_when_none_backward_compatible() -> None:
    """Rows written before this fix (no end_line key) must still parse cleanly."""
    obj = Class(file_id=1, name="C", line=5)
    row = obj.to_db_row()
    assert "end_line" not in row

    restored = Class.from_dict({"file_id": 1, "name": "C", "line": 5})
    assert restored.end_line is None


def test_function_object_end_line_round_trips_through_db_row() -> None:
    """Function.to_db_row()/from_dict() preserve end_line when set."""
    obj = Function(file_id=1, name="fn", line=1, end_line=3)
    row = obj.to_db_row()
    assert row["end_line"] == 3
    restored = Function.from_dict(row)
    assert restored.end_line == 3


def test_method_object_end_line_round_trips_through_db_row() -> None:
    """Method.to_db_row()/from_dict() preserve end_line when set."""
    obj = Method(class_id=1, name="m", line=2, end_line=9)
    row = obj.to_db_row()
    assert row["end_line"] == 9
    restored = Method.from_dict(row)
    assert restored.end_line == 9
