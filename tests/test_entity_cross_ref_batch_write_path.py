"""
Bug 3e7177d6: the CST-write/batch path never built entity_cross_ref.

Before this fix, only ``sync_file_to_db_atomic`` (the ``update_indexes``
path) ever called ``entity_cross_ref_builder.build_entity_cross_ref_for_file``.
``update_file_data_atomic_batch`` (``core/database_client/file_data_batch.py``)
and its callers - ``compose_cst_writer.apply_changes`` (any OVERWRITE of an
already-indexed ``.py`` file, including a plain CST-editor commit) and
``restore_backup_file`` - built classes/methods/functions rows but never
touched ``entity_cross_ref`` at all, so entity cross-references were
silently missing for files written through those paths.

The fix introduces one shared helper,
``core.entity_cross_ref_builder.rebuild_entity_cross_ref_for_file``, and
wires it into every write path that persists entities for a file:

- ``update_file_data_atomic_batch``'s STANDALONE branch (no caller-owned
  transaction) calls it directly, right after its own write commits.
- ``update_file_data_atomic_batch``'s CALLER-OWNED-TRANSACTION branch
  (``transaction_id`` set + ``skip_file_edit_lock=True``, used by
  ``compose_cst_writer`` / ``restore_backup_file``) must NOT call it itself
  - the entity rows it just wrote are not yet durably visible to a plain
  non-transactional read until the CALLER's own ``commit_transaction``
  runs. Those callers call the helper themselves, right after their own
  commit succeeds.

This module covers: (1) the standalone branch calling the helper with the
right arguments, (2) the caller-owned-transaction branch NOT calling it
itself, and (3) ``compose_cst_writer.apply_changes`` calling it AFTER
``commit_transaction``, proving the ordering constraint from point 2.

Also covers the removal of ``update_file_data_atomic`` (the legacy,
CodeDatabase-bound updater in ``core/database/files/atomic.py``) as dead
code: zero callers anywhere in the repo, confirmed by grep before removal.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_client.file_data_batch import (
    update_file_data_atomic_batch,
)

_SOURCE = (
    "class XRefBase:\n"
    '    """Base fixture class."""\n'
    "\n"
    "    pass\n"
)


def _make_db_mock() -> MagicMock:
    """Generic driver mock: acks every execute/execute_batch call.

    Same shape as ``tests/test_update_indexes_entity_counts_propagation.py``'s
    ``_make_db_mock_for_sync`` (this project's established convention for a
    minimal driver stub exercising the real batch-build/write code, not a
    real database).
    """
    db = MagicMock()
    db._driver_type = "postgres"

    def _execute(sql: str, params: Any = None, transaction_id: Any = None) -> Dict[str, Any]:
        if (sql or "").strip().upper().startswith("SELECT"):
            return {"data": [{"editing_pid": None}], "affected_rows": 0}
        return {"affected_rows": 1, "data": None}

    db.execute = MagicMock(side_effect=_execute)

    def _execute_batch(ops: List[Any], transaction_id: Any = None) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for op in ops:
            sql = op[0] if isinstance(op, (tuple, list)) and op else ""
            if str(sql).strip().upper().startswith("SELECT"):
                results.append({"data": []})
            else:
                results.append({"affected_rows": 1, "data": None})
        return results

    db.execute_batch = MagicMock(side_effect=_execute_batch)
    db.execute_logical_write_operation = None  # force the execute_batch fallback path
    db.begin_transaction = MagicMock(return_value="tid-mock")
    db.commit_transaction = MagicMock(return_value=True)
    db.rollback_transaction = MagicMock(return_value=True)
    return db


def test_standalone_branch_calls_rebuild_entity_cross_ref_after_write() -> None:
    """No caller-owned transaction: the batch write commits, then cross-ref rebuilds."""
    db = _make_db_mock()
    with patch(
        "code_analysis.core.entity_cross_ref_builder.rebuild_entity_cross_ref_for_file",
        return_value=1,
    ) as rebuild_mock:
        result = update_file_data_atomic_batch(
            database=db,
            file_id="file-1",
            project_id="project-1",
            source_code=_SOURCE,
            file_path="xref_base.py",
            file_mtime=0.0,
            transaction_id=None,
            skip_file_edit_lock=True,
        )

    assert result["success"] is True
    rebuild_mock.assert_called_once()
    args, kwargs = rebuild_mock.call_args
    assert args[0] is db
    assert args[1] == "file-1"
    assert args[2] == "project-1"
    assert args[3] == _SOURCE
    assert "context" in kwargs


def test_caller_owned_transaction_branch_does_not_call_rebuild_itself() -> None:
    """update_file_data_atomic_batch must not rebuild cross-ref before the caller commits.

    The caller-owned-transaction branch (transaction_id set AND
    skip_file_edit_lock=True - the shape compose_cst_writer.apply_changes
    and restore_backup_file use) only runs the batch SQL and returns; the
    entity rows are not durably visible outside that still-open transaction
    yet, so rebuilding cross-ref here would read a stale snapshot. The
    caller must do it after its own commit_transaction instead (see the
    apply_changes test below).
    """
    db = _make_db_mock()
    with patch(
        "code_analysis.core.entity_cross_ref_builder.rebuild_entity_cross_ref_for_file",
    ) as rebuild_mock:
        result = update_file_data_atomic_batch(
            database=db,
            file_id="file-1",
            project_id="project-1",
            source_code=_SOURCE,
            file_path="xref_base.py",
            file_mtime=0.0,
            transaction_id="tid-caller-owned",
            skip_file_edit_lock=True,
        )

    assert result["success"] is True
    rebuild_mock.assert_not_called()


def test_apply_changes_calls_rebuild_after_commit_transaction() -> None:
    """compose_cst_writer.apply_changes rebuilds cross-ref AFTER its own commit.

    Exercises the real defect's primary named path: an OVERWRITE of an
    already-indexed .py file through compose_cst_writer -> the CST/batch
    write path. Patches rebuild_entity_cross_ref_for_file to record the
    order of calls relative to database.commit_transaction, proving the
    ordering constraint (must run after commit, not before/inside the
    caller-owned-transaction branch tested above).
    """
    from code_analysis.commands.compose_cst_writer import apply_changes

    # apply_changes still declares the pre-UUID-migration `Optional[int]` hint for
    # file_id (see file_data_batch.py's own "UUID file ids at runtime; entity row
    # objects still declare legacy int annotation" note) - widen locally rather
    # than weakening the real signature or using a type: ignore bypass.
    file_id_for_apply: Any = "file-1"

    db = _make_db_mock()
    call_order: List[str] = []
    db.commit_transaction = MagicMock(
        side_effect=lambda *a, **k: call_order.append("commit_transaction")
    )

    def _record_rebuild(*_args: Any, **_kwargs: Any) -> int:
        call_order.append("rebuild_entity_cross_ref_for_file")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        root_path = Path(tmp)
        target_path = root_path / "xref_base.py"
        temp_file = root_path / "xref_base.py.tmp"
        temp_file.write_text(_SOURCE, encoding="utf-8")
        target_path.write_text("old content\n", encoding="utf-8")

        with patch(
            "code_analysis.core.entity_cross_ref_builder.rebuild_entity_cross_ref_for_file",
            side_effect=_record_rebuild,
        ) as rebuild_mock:
            result = apply_changes(
                database=db,
                transaction_id="tid-apply",
                project_id="project-1",
                root_path=root_path,
                target_path=target_path,
                source_code=_SOURCE,
                file_id=file_id_for_apply,
                file_data_backup=None,
                backup_uuid=None,
                backup_manager=None,
                temp_file=temp_file,
                _commit_message=None,
                skip_file_edit_lock=True,
            )

    assert result.__class__.__name__ == "SuccessResult", result
    rebuild_mock.assert_called_once()
    args, kwargs = rebuild_mock.call_args
    assert args[0] is db
    assert args[1] == "file-1"
    assert args[2] == "project-1"
    assert args[3] == _SOURCE
    assert call_order == ["commit_transaction", "rebuild_entity_cross_ref_for_file"]


def test_update_file_data_atomic_removed_as_dead_code() -> None:
    """update_file_data_atomic (core/database/files/atomic.py) no longer exists.

    Confirmed dead (zero callers anywhere in the repo besides its own def
    and the files/__init__.py re-export) before removal; CodeDatabase, the
    class its ``self``-bound signature targeted, no longer exists post the
    SQLite/DB-layer collapse either.
    """
    with pytest.raises(ModuleNotFoundError):
        import code_analysis.core.database.files.atomic  # noqa: F401

    import code_analysis.core.database.files as files_pkg

    assert not hasattr(files_pkg, "update_file_data_atomic")
    assert "update_file_data_atomic" not in files_pkg.__all__
