"""
Bug a586efdb: update_indexes never cleared old usages before re-adding them.

``update_indexes_analyzer.analyze_file`` used to track usages via
``UsageTracker`` and call ``add_usage`` per record - a pure INSERT with no
preceding DELETE. Re-running ``update_indexes`` on an already-indexed file
therefore duplicated every usage row on each run, since the ``usages`` table
was never cleared for that ``file_id`` first (unlike classes/methods/
functions/imports/code_content, which ``build_file_data_atomic_batches``
always deletes-then-reinserts on every real reindex).

The fix wires the analyzer to ``core.database.entities.replace_usages_for_file``
(a delete-then-insert helper that already existed, unused, at the time of
this fix) instead of the per-record INSERT loop.

Covers two layers:
1. ``replace_usages_for_file`` itself always issues a DELETE for the file's
   usages before any INSERT, including the empty-rows case (a file whose
   usages became empty must end up with zero usage rows, not its previous,
   now-stale set) - both outside and inside an existing transaction.
2. ``update_indexes_analyzer.analyze_file`` calls ``replace_usages_for_file``
   exactly once per file (never the old per-record ``add_usage`` loop) with
   every usage record ``UsageTracker`` found, including the zero-usages case.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from unittest.mock import patch

from code_analysis.core.database.entities import replace_usages_for_file
from code_analysis.commands.update_indexes_analyzer import analyze_file

# entities.py's replace_usages_for_file still declares the pre-UUID-migration
# `int` hint for file_id (real callers pass UUID strings post-migration - see
# file_data_batch.py's own "UUID file ids at runtime; entity row objects still
# declare legacy int annotation" note); widen locally rather than weakening the
# real signature or using a type: ignore bypass.
_FILE_ID_1: Any = "file-1"
_FILE_ID_2: Any = "file-2"

_USAGE_ROWS = [
    {
        "line": 5,
        "usage_type": "call",
        "target_type": "function",
        "target_name": "helper",
        "target_class": None,
        "context": None,
    },
    {
        "line": 6,
        "usage_type": "call",
        "target_type": "function",
        "target_name": "helper",
        "target_class": None,
        "context": None,
    },
]


class _StandaloneDbStub:
    """Driver stub with NO ``_in_transaction`` attribute (standalone call).

    ``replace_usages_for_file`` defaults to ``False`` via
    ``getattr(self, "_in_transaction", lambda: False)()`` when the attribute
    is absent - this stub deliberately omits it to exercise that default,
    and records every ``submit_logical_write_or_fallback`` batch it is asked
    to run (patched at its entities.py import site, since a plain stub has
    no real ``execute_logical_write_operation``/``execute_batch`` backing).
    """


class _InTransactionDbStub:
    """Driver stub whose ``_in_transaction()`` reports True."""

    def __init__(self) -> None:
        """Record every ``execute_batch`` call for assertions."""
        self.execute_batch_calls: List[List[Tuple[str, tuple]]] = []

    def _in_transaction(self) -> bool:
        """Return True (this stub simulates being inside a caller-owned transaction)."""
        return True

    def execute_batch(self, ops: List[Tuple[str, tuple]]) -> List[Dict[str, Any]]:
        """Record ``ops`` and ack every one."""
        self.execute_batch_calls.append(list(ops))
        return [{"affected_rows": 1, "data": None} for _ in ops]


def test_replace_usages_for_file_standalone_deletes_then_inserts() -> None:
    """Outside a transaction: one DELETE batch, then one INSERT batch, in order."""
    db = _StandaloneDbStub()
    captured: List[List[List[Tuple[str, tuple]]]] = []

    def _fake_submit(database: Any, batches: Sequence[Sequence[Tuple[str, Any]]]) -> None:
        """Record the batches submit_logical_write_or_fallback was called with."""
        captured.append([list(b) for b in batches])

    with patch(
        "code_analysis.core.database.entities.submit_logical_write_or_fallback",
        side_effect=_fake_submit,
    ) as submit_mock:
        result = replace_usages_for_file(db, _FILE_ID_1, _USAGE_ROWS)

    assert result == len(_USAGE_ROWS)
    submit_mock.assert_called_once()
    (batches,) = captured
    assert len(batches) == 2, "expected exactly [delete_batch, insert_batch]"
    delete_batch, insert_batch = batches
    assert len(delete_batch) == 1
    delete_sql, delete_params = delete_batch[0]
    assert delete_sql.strip().upper().startswith("DELETE FROM USAGES")
    assert delete_params == (_FILE_ID_1,)
    assert len(insert_batch) == len(_USAGE_ROWS)
    for (insert_sql, insert_params), row in zip(insert_batch, _USAGE_ROWS):
        assert insert_sql.strip().upper().startswith("INSERT INTO USAGES")
        assert insert_params[0] == _FILE_ID_1
        assert insert_params[1] == row["line"]


def test_replace_usages_for_file_standalone_empty_rows_still_deletes() -> None:
    """A file with zero current usages must still clear any stale prior rows."""
    db = _StandaloneDbStub()
    captured: List[List[List[Tuple[str, tuple]]]] = []

    def _fake_submit(database: Any, batches: Sequence[Sequence[Tuple[str, Any]]]) -> None:
        """Record the batches submit_logical_write_or_fallback was called with."""
        captured.append([list(b) for b in batches])

    with patch(
        "code_analysis.core.database.entities.submit_logical_write_or_fallback",
        side_effect=_fake_submit,
    ):
        result = replace_usages_for_file(db, _FILE_ID_1, [])

    assert result == 0
    (batches,) = captured
    # Empty insert_ops must NOT append a second (empty) batch - only the delete.
    assert len(batches) == 1
    delete_batch = batches[0]
    assert len(delete_batch) == 1
    delete_sql, delete_params = delete_batch[0]
    assert delete_sql.strip().upper().startswith("DELETE FROM USAGES")
    assert delete_params == (_FILE_ID_1,)


def test_replace_usages_for_file_inside_transaction_single_batch() -> None:
    """Inside an existing transaction: one execute_batch call, delete THEN inserts."""
    db = _InTransactionDbStub()

    result = replace_usages_for_file(db, _FILE_ID_2, _USAGE_ROWS)

    assert result == len(_USAGE_ROWS)
    assert len(db.execute_batch_calls) == 1
    (ops,) = db.execute_batch_calls
    assert len(ops) == 1 + len(_USAGE_ROWS)
    delete_sql, delete_params = ops[0]
    assert delete_sql.strip().upper().startswith("DELETE FROM USAGES")
    assert delete_params == (_FILE_ID_2,)
    for (insert_sql, _params), row in zip(ops[1:], _USAGE_ROWS):
        assert insert_sql.strip().upper().startswith("INSERT INTO USAGES")


_ANALYZE_FIXTURE_WITH_USAGES = (
    "def helper() -> int:\n"
    '    """Helper function called by run()."""\n'
    "    return 1\n"
    "\n\n"
    "def run() -> int:\n"
    '    """Call helper twice."""\n'
    "    helper()\n"
    "    return helper()\n"
)

_ANALYZE_FIXTURE_NO_USAGES = (
    "def standalone() -> int:\n"
    '    """A function that calls nothing."""\n'
    "    return 1\n"
)


class _AnalyzeFileDbStub:
    """Minimal driver stub for analyze_file (sync_file_to_db_atomic itself is mocked)."""

    def get_file_by_path(self, path: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Force the 'needs sync' path (no matching DB mtime), same as the entity-counts test."""
        return {"id": "file-99", "last_modified": None}

    def add_file(self, *args: Any, **kwargs: Any) -> str:
        """last_modified=None forces a row refresh; keep the same id."""
        return "file-99"

    def mark_file_needs_chunking(self, *args: Any, **kwargs: Any) -> None:
        """No-op chunking marker."""
        return None


def _run_analyze_file(source: str) -> Tuple[Dict[str, Any], List[Any]]:
    """Run analyze_file against ``source`` with replace_usages_for_file patched.

    Returns:
        ``(result_dict, replace_usages_for_file.call_args_list)``.
    """
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "fixture_usages.py"
        path.write_text(source, encoding="utf-8")

        db = _AnalyzeFileDbStub()
        fake_sync_result = {
            "success": True,
            "entities_updated": 2,
            "classes": 0,
            "functions": 2,
            "methods": 0,
            "imports": 0,
        }
        with patch(
            "code_analysis.commands.update_indexes_analyzer.sync_file_to_db_atomic",
            return_value=fake_sync_result,
        ), patch(
            "code_analysis.commands.update_indexes_analyzer.get_file_by_path",
            lambda driver, p, pid, include_deleted=False: driver.get_file_by_path(p, pid),
        ), patch(
            "code_analysis.commands.update_indexes_analyzer.add_file",
            lambda driver, *a, **k: driver.add_file(*a, **k),
        ), patch(
            "code_analysis.commands.update_indexes_analyzer.mark_file_needs_chunking",
            lambda driver, *a, **k: driver.mark_file_needs_chunking(*a, **k),
        ), patch(
            "code_analysis.commands.update_indexes_analyzer.replace_usages_for_file",
            return_value=0,
        ) as replace_mock:
            out = analyze_file(
                database=db,
                file_path=path,
                project_id=project_id,
                root_path=temp_dir,
            )
        return out, replace_mock.call_args_list


def test_analyze_file_calls_replace_usages_for_file_once_with_real_usage_rows() -> None:
    """A file with two call-usages: replace_usages_for_file called once, with 2 rows."""
    out, calls = _run_analyze_file(_ANALYZE_FIXTURE_WITH_USAGES)

    assert out.get("status") == "success"
    assert len(calls) == 1, "must call replace_usages_for_file exactly once, never add_usage per record"
    args, _kwargs = calls[0]
    _database, file_id, rows = args
    assert file_id == "file-99"
    assert len(rows) == 2
    assert all(r["target_name"] == "helper" for r in rows)
    assert all(r["usage_type"] == "call" for r in rows)


def test_analyze_file_calls_replace_usages_for_file_with_empty_list_when_no_usages() -> None:
    """A file that calls nothing: replace_usages_for_file is still called, with an empty list.

    This is what makes a file whose usages became empty actually end up with
    zero usage rows in the DB (delete-only batch), instead of silently
    skipping the call and leaving stale rows from a previous version of the
    file untouched.
    """
    out, calls = _run_analyze_file(_ANALYZE_FIXTURE_NO_USAGES)

    assert out.get("status") == "success"
    assert len(calls) == 1
    args, _kwargs = calls[0]
    _database, file_id, rows = args
    assert file_id == "file-99"
    assert rows == []
