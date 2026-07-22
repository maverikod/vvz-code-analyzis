"""
Tests for project_scoped activity coordinator (Step 13 / Step 24).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import time
from typing import Any, Iterator, Tuple

import pytest

from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.drivers.base import BaseDatabaseDriver
from code_analysis.core.worker_project_activity import (
    get_project_activity,
    heartbeat_project_activity,
    release_project_activity,
    try_acquire_project_activity,
)

# PostgreSQL parity: set CODE_ANALYSIS_POSTGRES_TEST_DSN (e.g. postgresql://user:pass@host/db)
_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"

_PG_PARITY = pytest.param(
    "postgres",
    marks=pytest.mark.skipif(
        not os.environ.get(_PG_ENV),
        reason=(
            f"PostgreSQL test DSN not set ({_PG_ENV} unset); set it to run DB parity tests"
        ),
    ),
)

PA = "A"
PB = "B"


def _count_table(driver: BaseDatabaseDriver, table: str) -> int:
    """Return count table."""
    r = driver.execute(f"SELECT COUNT(*) AS c FROM {table}", None, transaction_id=None)
    if not isinstance(r, dict):
        return 0
    data = r.get("data")
    if not data or not isinstance(data, list):
        return 0
    row0 = data[0]
    if isinstance(row0, dict):
        v = list(row0.values())
        return int(v[0]) if v else 0
    return 0


def _pg_driver() -> BaseDatabaseDriver:
    """Return pg driver."""
    dsn = os.environ.get(_PG_ENV, "").strip()
    if not dsn:
        raise RuntimeError("dsn")
    return create_driver("postgres", {"dsn": dsn})


@pytest.fixture
def wdb(request: Any) -> Iterator[BaseDatabaseDriver]:
    """Return wdb."""
    d: BaseDatabaseDriver = _pg_driver()
    try:
        yield d
    finally:
        d.disconnect()


def _lock_counts(driver: BaseDatabaseDriver) -> Tuple[int, int]:
    """Return lock counts."""
    return (
        _count_table(driver, "project_activity_locks"),
        _count_table(driver, "files"),
    )


# --- 1..10: behaviour (PostgreSQL parity; skipped without a live test DSN) ---


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_acquire_empty_project_lock_succeeds(wdb: BaseDatabaseDriver) -> None:
    """Verify test acquire empty project lock succeeds."""
    before = _lock_counts(wdb)
    ok = try_acquire_project_activity(wdb, PA, "watcher", "w1", "watcher_staging", 60.0)
    after = _lock_counts(wdb)
    assert ok is True
    assert after[0] == before[0] + 1
    assert after[1] == before[1]
    row = get_project_activity(wdb, PA)
    assert row is not None
    assert row["owner_type"] == "watcher"
    assert row["owner_id"] == "w1"
    assert row["activity"] == "watcher_staging"
    now = time.time()
    assert float(row["lease_until"]) > now
    assert float(row["heartbeat_at"]) <= now + 1.0


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_same_owner_can_refresh_lease(wdb: BaseDatabaseDriver) -> None:
    """Verify test same owner can refresh lease."""
    try_acquire_project_activity(wdb, PA, "watcher", "w1", "watcher_staging", 10.0)
    r1 = get_project_activity(wdb, PA)
    assert r1 is not None
    lu1 = float(r1["lease_until"])
    time.sleep(0.02)
    before = _lock_counts(wdb)
    ok = heartbeat_project_activity(
        wdb, PA, "watcher", "w1", "watcher_inserting_new_files", 500.0
    )
    after = _lock_counts(wdb)
    assert ok is True
    assert after == before
    r2 = get_project_activity(wdb, PA)
    assert r2 is not None
    assert r2["activity"] == "watcher_inserting_new_files"
    assert float(r2["lease_until"]) > lu1
    assert _count_table(wdb, "project_activity_locks") == 1


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_foreign_owner_same_project_is_blocked(wdb: BaseDatabaseDriver) -> None:
    """Verify test foreign owner same project is blocked."""
    try_acquire_project_activity(wdb, PA, "watcher", "w1", "watcher_staging", 120.0)
    b0 = _lock_counts(wdb)
    ok = try_acquire_project_activity(
        wdb, PA, "indexer", "i1", "indexer_processing", 30.0
    )
    b1 = _lock_counts(wdb)
    assert ok is False
    assert b1 == b0
    row = get_project_activity(wdb, PA)
    assert row is not None
    assert row["owner_type"] == "watcher" and row["owner_id"] == "w1"


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_expired_lease_can_be_taken_over(wdb: BaseDatabaseDriver) -> None:
    """Verify test expired lease can be taken over."""
    try_acquire_project_activity(wdb, PA, "watcher", "w1", "watcher_staging", 0.1)
    time.sleep(0.2)
    ok = try_acquire_project_activity(
        wdb, PA, "indexer", "i1", "indexer_processing", 60.0
    )
    assert ok is True
    row = get_project_activity(wdb, PA)
    assert row is not None
    assert row["owner_type"] == "indexer" and row["owner_id"] == "i1"


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_release_requires_same_owner(wdb: BaseDatabaseDriver) -> None:
    """Verify test release requires same owner."""
    try_acquire_project_activity(wdb, PA, "watcher", "w1", "watcher_staging", 120.0)
    before = get_project_activity(wdb, PA)
    ok = release_project_activity(wdb, PA, "indexer", "i1")
    after = get_project_activity(wdb, PA)
    assert ok is False
    assert after == before
    assert after is not None
    assert after["owner_id"] == "w1"


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_owner_release_clears_or_removes_row(wdb: BaseDatabaseDriver) -> None:
    """Verify test owner release clears or removes row."""
    try_acquire_project_activity(wdb, PA, "watcher", "w1", "watcher_staging", 120.0)
    ok = release_project_activity(wdb, PA, "watcher", "w1")
    assert ok is True
    assert get_project_activity(wdb, PA) is None


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_different_projects_are_not_globally_blocked(wdb: BaseDatabaseDriver) -> None:
    """Verify test different projects are not globally blocked."""
    try_acquire_project_activity(wdb, PA, "watcher", "w1", "watcher_staging", 120.0)
    ok = try_acquire_project_activity(
        wdb, PB, "indexer", "i1", "indexer_processing", 60.0
    )
    assert ok is True
    a = get_project_activity(wdb, PA)
    b = get_project_activity(wdb, PB)
    assert a is not None and a["owner_id"] == "w1"
    assert b is not None and b["owner_id"] == "i1"


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_allowed_owner_type_and_activity_validation(
    wdb: BaseDatabaseDriver,
) -> None:
    """Verify test allowed owner type and activity validation."""
    n_before = _count_table(wdb, "project_activity_locks")
    with pytest.raises(ValueError):
        try_acquire_project_activity(
            wdb, PA, "invalid_owner", "x", "watcher_staging", 10.0
        )
    with pytest.raises(ValueError):
        try_acquire_project_activity(wdb, PA, "watcher", "x", "not_an_activity", 10.0)
    assert _count_table(wdb, "project_activity_locks") == n_before


@pytest.mark.parametrize("wdb", [_PG_PARITY], indirect=True)
def test_heartbeat_requires_current_owner(wdb: BaseDatabaseDriver) -> None:
    """Verify test heartbeat requires current owner."""
    try_acquire_project_activity(wdb, PA, "watcher", "w1", "watcher_staging", 120.0)
    r0 = get_project_activity(wdb, PA)
    assert r0 is not None
    assert (
        heartbeat_project_activity(wdb, PA, "watcher", "w2", "watcher_staging", 200.0)
        is False
    )
    assert (
        heartbeat_project_activity(
            wdb, PA, "indexer", "i1", "indexer_processing", 200.0
        )
        is False
    )
    r1 = get_project_activity(wdb, PA)
    assert r1 is not None
    assert float(r1["lease_until"]) == float(r0["lease_until"])


