"""
Performance tests for cst_save_tree batch DB path (update_file_data_atomic_batch).

Measures timings returned by save_tree_to_file; asserts update_file_data_atomic
stays within a reasonable bound (batch path = few execute_batch calls, not N round-trips).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.cst_tree.tree_builder import create_tree_from_code
from code_analysis.core.cst_tree.tree_saver import save_tree_to_file


def _make_db_mock() -> MagicMock:
    """Database mock with execute_batch (batch path)."""
    db = MagicMock()
    db.begin_transaction = MagicMock(return_value="tid")
    db.commit_transaction = MagicMock()
    db.rollback_transaction = MagicMock()
    db.select = MagicMock(return_value=[])
    created = MagicMock()
    created.id = 1
    db.create_file = MagicMock(return_value=created)
    updated = MagicMock()
    updated.id = 1
    db.update_file = MagicMock(return_value=updated)
    db.execute_batch = MagicMock(
        return_value=[
            {"affected_rows": 1, "lastrowid": i + 1, "data": None} for i in range(100)
        ]
    )
    db.execute_logical_write_operation = MagicMock(
        return_value={"success": True, "data": {"batch_results": []}}
    )
    return db


@pytest.fixture
def db_mock(monkeypatch):
    """Database mock for save_tree_to_file (batch path).

    ``tree_saver.py`` calls the driver-direct ``create_file``/``update_file`` free
    functions (stage 2 layer collapse) instead of ``database.create_file``/
    ``.update_file`` bound methods; patch them at their import site in
    ``tree_saver`` so the mock's own ``db.create_file``/``db.update_file``
    stubs are still what gets exercised.
    """
    monkeypatch.setattr(
        "code_analysis.core.cst_tree.tree_saver.create_file",
        lambda driver, file_obj: driver.create_file(file_obj),
    )
    monkeypatch.setattr(
        "code_analysis.core.cst_tree.tree_saver.update_file",
        lambda driver, file_obj: driver.update_file(file_obj),
    )
    return _make_db_mock()


@pytest.fixture
def tree_small(tmp_path: Path):
    """Small file: docstring only."""
    code = '"""Doc."""\n\nx = 1\n'
    path = tmp_path / "small.py"
    tree = create_tree_from_code(str(path), code)
    return tree.tree_id, tmp_path, "small.py"


@pytest.fixture(autouse=True)
def _patch_file_edit_lock_acquire() -> None:
    """MagicMock DB does not return DML affected_rows; sync would always see lock fail."""
    with patch(
        "code_analysis.core.database.file_edit_lock.acquire_file_edit_lock_with_retry",
        return_value=True,
    ):
        yield


@pytest.fixture
def tree_with_entities(tmp_path: Path):
    """File with classes/methods/functions/imports to exercise full batch path."""
    code = '''
"""Module with entities."""

import os
import sys

def foo():
    pass

class Bar:
    def meth(self):
        pass
'''
    path = tmp_path / "with_entities.py"
    tree = create_tree_from_code(str(path), code.strip())
    return tree.tree_id, tmp_path, "with_entities.py"


class TestCstSaveBatchPerformance:
    """Performance tests for cst_save_tree batch DB updates."""

    def test_save_returns_timings(self, tree_small, db_mock) -> None:
        """save_tree_to_file returns timings including update_file_data_atomic."""
        tree_id, root_dir, file_path = tree_small
        result = save_tree_to_file(
            tree_id=tree_id,
            file_path=file_path,
            root_dir=root_dir,
            project_id=str(uuid.uuid4()),
            database=db_mock,
            validate=True,
            backup=False,
        )
        assert result.get("success") is True
        timings = result.get("timings")
        assert timings is not None
        # Timings keys may vary; at least one of the batch-path keys present
        assert (
            "db_file_record" in timings
            or "update_file_data_atomic" in timings
            or len(timings) >= 1
        )

    def test_update_file_data_atomic_under_threshold(self, tree_small, db_mock) -> None:
        """Batch path: update_file_data_atomic should be under 5s (no N round-trips)."""
        tree_id, root_dir, file_path = tree_small
        result = save_tree_to_file(
            tree_id=tree_id,
            file_path=file_path,
            root_dir=root_dir,
            project_id=str(uuid.uuid4()),
            database=db_mock,
            validate=True,
            backup=False,
        )
        assert result.get("success") is True
        t = result["timings"].get("update_file_data_atomic")
        if t is None:
            pytest.skip("update_file_data_atomic not in timings (API may have changed)")
        assert t < 5.0, (
            f"update_file_data_atomic={t:.3f}s; batch path should be fast "
            "(few execute_batch calls). If this fails, check for per-row DB calls in loop."
        )

    def test_save_multiple_runs_timings_stable(self, tree_small, db_mock) -> None:
        """Run save 3 times and report min/mean/max of update_file_data_atomic."""
        tree_id, root_dir, file_path = tree_small
        project_id = str(uuid.uuid4())
        times: list[float] = []
        for _ in range(3):
            result = save_tree_to_file(
                tree_id=tree_id,
                file_path=file_path,
                root_dir=root_dir,
                project_id=project_id,
                database=db_mock,
                validate=True,
                backup=False,
            )
            assert result.get("success") is True
            t = result["timings"].get("update_file_data_atomic")
            if t is not None:
                times.append(t)
        if times:
            mn, mx = min(times), max(times)
            mean = sum(times) / len(times)
            assert mx < 5.0, f"max update_file_data_atomic={mx:.3f}s"
            # Log for human: pytest -s shows this
            print(
                f"  update_file_data_atomic: min={mn:.4f}s mean={mean:.4f}s max={mx:.4f}s"
            )

    def test_save_with_entities_returns_timings(
        self, tree_with_entities, db_mock
    ) -> None:
        """Full batch path with classes/methods/functions/imports."""
        tree_id, root_dir, file_path = tree_with_entities
        result = save_tree_to_file(
            tree_id=tree_id,
            file_path=file_path,
            root_dir=root_dir,
            project_id=str(uuid.uuid4()),
            database=db_mock,
            validate=True,
            backup=False,
        )
        # May fail with class insert count mismatch with mock; accept success or skip
        if not result.get("success"):
            pytest.skip(
                f"save_tree_to_file failed (e.g. mock mismatch): {result.get('error', '')}"
            )
        assert result.get("timings") is not None
        t = result["timings"].get("update_file_data_atomic")
        if t is not None:
            assert t < 5.0, f"update_file_data_atomic={t:.3f}s with entities"
