"""
Watcher vs indexer project-scoped coordination (Step 25).

PostgreSQL parity when CODE_ANALYSIS_POSTGRES_TEST_DSN is set, plus pure-function
and source-inspection tests. Never uses vast_srv.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database_client.transient import is_structured_retryable_error
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
    _adapt_sqlite_dml_for_postgres,
)
from code_analysis.core.path_normalization import NormalizedPath, normalize_file_path
from code_analysis.core.worker_project_activity import (
    release_project_activity,
    try_acquire_project_activity,
)

# Project A = busy (UUID v4-form strings for projectid files)
PA = "11111111-1111-4111-8111-1111111111a1"

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


def _create_projectid(root: Path, pid: str) -> None:
    """Return create projectid."""
    (root / "projectid").write_text(
        json.dumps({"id": pid, "description": "wic test"}), encoding="utf-8"
    )


# --- Group 3: staging / paths / ignore (feasible slice) ---


def test_project_relative_path_is_posix_style(tmp_path: Path) -> None:
    """Verify test project relative path is posix style."""
    pr = tmp_path / "pr"
    pr.mkdir()
    _create_projectid(pr, PA)
    fp = pr / "sub" / "f.py"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("x", encoding="utf-8")
    n = normalize_file_path(fp, watch_dirs=[tmp_path], project_root=pr)
    assert isinstance(n, NormalizedPath)
    assert (
        n.relative_path == "sub/f.py"
        or n.relative_path.replace("\\", "/") == "sub/f.py"
    )


# --- Group 5: idempotency and retry contract ---


def test_unknown_commit_outcome_is_not_treated_as_safe_logical_retry() -> None:
    """Verify test unknown commit outcome is not treated as safe logical retry."""
    assert (
        is_structured_retryable_error(
            {"retryable": True, "commit_outcome_unknown": True}
        )
        is False
    )


# --- Group 6: backend equivalence (optional Postgres) ---


@pytest.mark.skipif(
    not os.environ.get(_PG_ENV),
    reason=f"PostgreSQL DSN not set ({_PG_ENV})",
)
def test_postgres_try_acquire_lock_if_dsn_configured() -> None:
    """When a test Postgres URL exists, the same try_acquire contract applies."""
    dsn = os.environ[_PG_ENV].strip()
    d = create_driver("postgres", {"dsn": dsn})
    try:
        pid = f"pg-wic-{uuid.uuid4().hex[:12]}"
        assert try_acquire_project_activity(
            d, pid, "watcher", "w1", "watcher_staging", 30.0
        )
        assert release_project_activity(d, pid, "watcher", "w1")
    finally:
        d.disconnect()


def test_postgres_adapter_rewrites_julianday() -> None:
    """Verify test postgres adapter rewrites julianday."""
    out = _adapt_sqlite_dml_for_postgres(
        "UPDATE t SET x = 1, updated_at = julianday('now') WHERE id = ?"
    )
    assert "julianday" not in out.lower()
    assert "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)" in out


# --- Group 7: auto-created project / no watcher daemon indexing ---


def test_watcher_scan_source_has_no_update_indexes_thread() -> None:
    """Verify test watcher scan source has no update indexes thread."""
    here = Path(__file__).resolve().parent.parent
    src = here / "code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py"
    text = src.read_text(encoding="utf-8")
    assert "UpdateIndexesMCPCommand" not in text
    assert "threading" not in text
    assert "Thread(" not in text


def test_auto_indexing_not_allowed_owner() -> None:
    """Verify test auto indexing not allowed owner."""
    from code_analysis.core import worker_project_activity as wpa

    assert "auto_indexing" not in wpa.ALLOWED_OWNER_TYPES


def test_watcher_log_documents_normal_indexer_path_for_new_projects() -> None:
    """Verify test watcher log documents normal indexer path for new projects."""
    here = Path(__file__).resolve().parent.parent
    p = here / "code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py"
    t = p.read_text(encoding="utf-8")
    assert "normal indexer" in t
    assert "auto_indexing" in t  # "no ... auto_indexing" log line


# --- Logging: WORKER_COORD ---


def test_indexer_skip_message_in_indexing_worker_source() -> None:
    """Verify test indexer skip message in indexing worker source."""
    here = Path(__file__).resolve().parent.parent
    p = here / "code_analysis/core/indexing_worker_pkg/processing.py"
    t = p.read_text(encoding="utf-8")
    assert "[WORKER_COORD] indexer skip" in t
    assert "indexer_processing" in t
