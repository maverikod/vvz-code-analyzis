"""
Tests for integrity analysis (eligibility, SQL batch helpers, path trimming).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import pytest

from code_analysis.core.integrity_analysis.eligibility import (
    is_project_available_for_integrity_scan,
)
from code_analysis.core.integrity_analysis.import_cycles_sql import (
    build_import_cycle_detection_batch,
    build_step1_create_edges_sql,
    build_step3_select_cycles_sql,
    _dedupe_cycle_paths,
    _trim_path_at_first_duplicate,
)


class _FakeDB:
    def __init__(self, lock_row: Optional[Dict[str, Any]] = None) -> None:
        self.lock_row = lock_row
        self.executed: List[Tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Dict[str, Any]:
        self.executed.append((sql.strip(), params))
        return {"data": [], "affected_rows": 0}


def test_eligibility_no_lock() -> None:
    db = _FakeDB()

    def _get(_db: Any, _pid: str) -> None:
        return None

    import code_analysis.core.integrity_analysis.eligibility as mod

    orig = mod.get_project_activity
    mod.get_project_activity = _get
    try:
        ok, reason = is_project_available_for_integrity_scan(db, "p1")
        assert ok is True
        assert reason == "no_activity_lock"
    finally:
        mod.get_project_activity = orig


def test_eligibility_watcher_active() -> None:
    db = _FakeDB()
    row = {
        "owner_type": "watcher",
        "lease_until": time.time() + 300,
    }

    import code_analysis.core.integrity_analysis.eligibility as mod

    orig = mod.get_project_activity
    mod.get_project_activity = lambda _db, _pid: row
    try:
        ok, reason = is_project_available_for_integrity_scan(db, "p1")
        assert ok is False
        assert reason == "watcher_active"
    finally:
        mod.get_project_activity = orig


def test_step1_creates_indexes_and_excludes_self_loops() -> None:
    ops = build_step1_create_edges_sql("proj-uuid")
    sql_blob = "\n".join(s for s, _ in ops)
    assert "CREATE INDEX idx_integrity_ie_from" in sql_blob
    assert "CREATE INDEX idx_integrity_ie_to" in sql_blob
    assert "CREATE INDEX idx_integrity_fm_mod" in sql_blob
    # self-loop filter casts the UUID side to TEXT (PostgreSQL has no uuid<>text)
    assert "CAST(i.file_id AS TEXT) <> fm.file_id" in sql_blob
    assert ops[-1][1] == ("proj-uuid",)


def test_parametrized_statements_have_no_literal_percent() -> None:
    """Regression: a literal ``%`` in a parametrized statement makes psycopg treat
    ``%/`` / ``%.`` as an invalid placeholder ("only '%s','%b','%t' allowed").
    LIKE patterns must be bound as parameters, so no parametrized SQL may contain
    a bare ``%``.
    """
    ops = build_step1_create_edges_sql("proj-uuid")
    for sql, params in ops:
        if params:
            assert "%" not in sql, f"literal % in parametrized statement: {sql!r}"
    # The init/.py LIKE patterns must instead appear as bound parameters.
    flat_params = [p for _, params in ops for p in params]
    assert "%/__init__.py" in flat_params
    assert "%.py" in flat_params


def test_step3_rejects_f0_equals_f1() -> None:
    sql, _ = build_step3_select_cycles_sql(4)
    assert "f0 <> f1" in sql
    assert "f2 = f0" in sql or "f2 = f0 OR f2 = f1" in sql


def test_batch_has_three_stages() -> None:
    batch = build_import_cycle_detection_batch("pid", max_depth=3)
    assert len(batch) >= 10
    select_sql = batch[-1][0]
    assert select_sql.strip().startswith("SELECT")


def test_trim_path_at_duplicate() -> None:
    assert _trim_path_at_first_duplicate(["a", "b", "c", "b"]) == ["a", "b", "c", "b"]
    assert _trim_path_at_first_duplicate(["a", "b", "a"]) == ["a", "b", "a"]


def test_batch_summary_includes_integrity() -> None:
    from code_analysis.commands.comprehensive_analysis_mcp.batch_summary import (
        build_batch_summary,
    )

    results = {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "long_files": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [],
        "missing_docstrings": [],
        "project_integrity": {
            "skipped": False,
            "missing_files_count": 2,
            "circular_imports_count": 1,
            "cleared_issues": 3,
        },
    }
    summary = build_batch_summary(results, 1, 0, 1)
    assert summary["total_missing_files_on_disk"] == 2
    assert summary["total_circular_imports"] == 1


def test_comprehensive_schema_has_integrity_params() -> None:
    from code_analysis.commands.comprehensive_analysis_mcp.command import (
        ComprehensiveAnalysisMCPCommand,
    )

    schema = ComprehensiveAnalysisMCPCommand.get_schema()
    props = schema["properties"]
    assert "check_missing_files_on_disk" in props
    assert "check_circular_imports" in props
    assert "max_import_chain_depth" in props


def test_docker_watch_root_constant() -> None:
    from code_analysis.core.constants import CASMGR_DOCKER_WATCH_ROOT

    assert CASMGR_DOCKER_WATCH_ROOT == "/watched"


def test_docker_server_dockerfile_exists() -> None:
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    assert (repo / "docker/casmgr-server/Dockerfile").is_file()
    assert (repo / "docker/docker-compose.yml").is_file()


def test_dedupe_cycle_rotations() -> None:
    a = ["id1", "id2", "id3", "id1"]
    b = ["id2", "id3", "id1", "id2"]
    out = _dedupe_cycle_paths([a, b])
    assert len(out) == 1
