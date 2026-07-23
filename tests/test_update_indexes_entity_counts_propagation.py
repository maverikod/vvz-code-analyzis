"""
Per-category entity counts (classes/functions/methods/imports) must reach the
``update_indexes`` summary instead of being hardcoded to 0 (bug a525ec26).

Two links in the propagation chain are covered:
1. ``sync_file_to_db_atomic`` forwards ``build_file_data_atomic_batches``'s
   per-category counts (its ``meta`` dict) into its own result dict.
2. ``update_indexes_analyzer.analyze_file`` forwards those counts from
   ``sync_result`` into its returned per-file dict (previously hardcoded to 0
   here even though ``sync_file_to_db_atomic`` already had the real values in
   ``entities_updated``).

``code_mapper_mcp_command.py``'s batch aggregation already sums
``r.get("classes"/"functions"/"methods"/"imports", 0)`` over ``analyze_file``
results (verified by inspection, not re-tested here) - fixing these two links
is what makes the summary non-zero.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from code_analysis.core.database_client.file_data_batch import (
    build_file_data_atomic_batches,
)
from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic
from code_analysis.commands.update_indexes_analyzer import analyze_file

_FIXTURE_SOURCE = (
    "import os\n"
    "import sys\n"
    "\n"
    "\n"
    "def top_level_fn():\n"
    "    return 1\n"
    "\n"
    "\n"
    "class Foo:\n"
    "    def method_a(self):\n"
    "        return 1\n"
    "\n"
    "    def method_b(self):\n"
    "        return 2\n"
)


def _make_db_mock_for_sync() -> MagicMock:
    """Minimal driver mock exercising sync_file_to_db_atomic end-to-end
    (same shape as tests/test_cst_stable_ids.py's harness)."""
    db = MagicMock()
    db.get_file_by_path = MagicMock(return_value={"id": 1})
    db.begin_transaction = MagicMock(return_value="tid-mock")
    db.commit_transaction = MagicMock(return_value=True)
    db.rollback_transaction = MagicMock(return_value=True)

    def _exec(sql: str, params=None, transaction_id=None):
        """Return a placeholder row for SELECT (file-edit-lock check), else a no-op ack."""
        if (sql or "").strip().upper().startswith("SELECT"):
            return {"data": [{"editing_pid": None}], "affected_rows": 0}
        return {"affected_rows": 1, "data": None}

    db.execute = MagicMock(side_effect=_exec)

    def _batch(ops, transaction_id=None):
        """Ack every op in the batch."""
        return [{"affected_rows": 1, "data": None} for _ in ops]

    db.execute_batch = MagicMock(side_effect=_batch)
    db.execute_logical_write_operation = None  # force the execute_batch fallback path
    return db


def test_build_file_data_atomic_batches_meta_has_known_counts() -> None:
    """Sanity: the fixture source has exactly 1 class, 1 function, 2 methods, 2 imports."""
    _batches, meta = build_file_data_atomic_batches(
        file_id="f1",
        project_id="p1",
        source_code=_FIXTURE_SOURCE,
        file_path="fixture.py",
        file_mtime=0.0,
    )
    assert meta["success"] is True
    assert meta["classes"] == 1
    assert meta["functions"] == 1
    assert meta["methods"] == 2
    assert meta["imports"] == 2
    assert meta["entities_updated"] == 1 + 1 + 2 + 2


def test_sync_file_to_db_atomic_forwards_meta_counts_into_result() -> None:
    """sync_file_to_db_atomic's result must carry the same per-category counts as meta."""
    _batches, meta = build_file_data_atomic_batches(
        file_id="1",
        project_id="test-project",
        source_code=_FIXTURE_SOURCE,
        file_path="/tmp/fixture_sync.py",
        file_mtime=0.0,
    )

    db = _make_db_mock_for_sync()
    result = sync_file_to_db_atomic(
        database=db,
        project_id="test-project",
        absolute_path="/tmp/fixture_sync.py",
        source_code=_FIXTURE_SOURCE,
        file_mtime=0.0,
        file_id="1",
    )

    assert result["success"] is True
    assert result["classes"] == meta["classes"] == 1
    assert result["functions"] == meta["functions"] == 1
    assert result["methods"] == meta["methods"] == 2
    assert result["imports"] == meta["imports"] == 2
    assert result["entities_updated"] == meta["entities_updated"]


def test_analyze_file_propagates_real_entity_counts_not_hardcoded_zero() -> None:
    """analyze_file's success dict must use sync_result's counts, not literal 0s."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "fixture_analyze.py"
        path.write_text(_FIXTURE_SOURCE, encoding="utf-8")

        class _Db:
            """Minimal driver stub; sync_file_to_db_atomic itself is mocked below."""

            def get_file_by_path(self, p: str, pid: str):
                """Force the fast 'needs sync' path (no matching DB mtime)."""
                return {"id": 99, "last_modified": None}

            def add_file(self, *a, **k):
                """last_modified=None forces a row refresh; keep the same id."""
                return 99

            def add_usage(self, *a, **k):
                """No-op usage sink."""
                return None

            def mark_file_needs_chunking(self, *a, **k):
                """No-op chunking marker."""
                return None

        db = _Db()
        fake_sync_result = {
            "success": True,
            "entities_updated": 6,
            "classes": 1,
            "functions": 1,
            "methods": 2,
            "imports": 2,
        }
        with patch(
            "code_analysis.commands.update_indexes_analyzer.sync_file_to_db_atomic",
            return_value=fake_sync_result,
        ) as sync_mock, patch(
            "code_analysis.commands.update_indexes_analyzer.get_file_by_path",
            lambda driver, p, pid, include_deleted=False: driver.get_file_by_path(p, pid),
        ), patch(
            "code_analysis.commands.update_indexes_analyzer.add_file",
            lambda driver, *a, **k: driver.add_file(*a, **k),
        ), patch(
            "code_analysis.commands.update_indexes_analyzer.mark_file_needs_chunking",
            lambda driver, *a, **k: driver.mark_file_needs_chunking(*a, **k),
        ):
            out = analyze_file(
                database=db,
                file_path=path,
                project_id=project_id,
                root_path=temp_dir,
            )

        sync_mock.assert_called_once()
        assert out.get("status") == "success"
        assert out.get("classes") == 1
        assert out.get("functions") == 1
        assert out.get("methods") == 2
        assert out.get("imports") == 2
        assert out.get("entities_updated") == 6
