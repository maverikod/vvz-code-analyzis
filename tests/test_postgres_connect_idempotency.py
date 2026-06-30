"""
Tests for the PostgreSQL idle-connection-leak fix.

Two defects are covered:

* Defect A — ``PostgreSQLDriver.connect()`` must be idempotent: a second connect
  on the same instance must tear down the stale main connection / pool / manager
  / reaper instead of orphaning them, and never leave two reaper threads.
* Defect B — the vectorization worker loop must **reuse** its database client
  across cycles instead of building (and orphaning) a fresh one every poll.

The unit tests run without a live PostgreSQL (psycopg is never connected). A
gated live test (skipped unless ``CODE_ANALYSIS_POSTGRES_TEST_DSN`` is set)
asserts backend-connection conservation across a double connect.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import os
import threading
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver

# --- Defect A: connect() idempotency -------------------------------------


def test_teardown_stale_state_calls_disconnect_when_initialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A1: with stale state present, the pre-connect teardown calls disconnect()."""
    driver = PostgreSQLDriver()
    driver.conn = object()  # simulate an already-initialized driver
    calls = {"n": 0}
    monkeypatch.setattr(
        driver, "disconnect", lambda: calls.__setitem__("n", calls["n"] + 1)
    )

    driver._teardown_stale_state_if_any()

    assert calls["n"] == 1


def test_teardown_stale_state_noop_when_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A1: a fresh driver does not call disconnect() (nothing to tear down)."""
    driver = PostgreSQLDriver()
    calls = {"n": 0}
    monkeypatch.setattr(
        driver, "disconnect", lambda: calls.__setitem__("n", calls["n"] + 1)
    )

    driver._teardown_stale_state_if_any()

    assert calls["n"] == 0


def test_start_reaper_never_leaves_two_threads() -> None:
    """A2: starting the reaper twice stops the old thread; never two alive."""
    driver = PostgreSQLDriver()
    driver._transaction_reaper_interval_seconds = 30.0
    driver._transaction_max_age_seconds = 300.0
    try:
        driver._start_transaction_reaper()
        first = driver._reaper_thread
        assert first is not None and first.is_alive()

        driver._start_transaction_reaper()
        second = driver._reaper_thread
        assert second is not None and second.is_alive()

        # The second start replaced the first and stopped it — no leaked thread.
        assert second is not first
        assert not first.is_alive()
    finally:
        driver._stop_transaction_reaper()
    assert driver._reaper_thread is None


# --- Defect B: vectorization worker reuses its client --------------------


def test_vectorization_loop_reuses_client_across_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B: ensure_database_connection runs once, not once per cycle."""
    from code_analysis.core.vectorization_worker_pkg import processing as proc

    fake_db = MagicMock(name="database")
    ensure_calls = {"n": 0}
    cycle_calls = {"n": 0}
    stop_event = threading.Event()

    async def fake_ensure(worker: Any, cfg: Any, **kwargs: Any):
        """Return a live client; counts how often a (re)connect happened."""
        ensure_calls["n"] += 1
        return (fake_db, True, 1.0, True)

    async def fake_cycle(*args: Any, **kwargs: Any):
        """One cycle; stop the loop after 3 so the test terminates."""
        cycle_calls["n"] += 1
        if cycle_calls["n"] >= 3:
            stop_event.set()
        return (0, 0, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0)

    monkeypatch.setattr(proc, "ensure_database_connection", fake_ensure)
    monkeypatch.setattr(proc, "run_one_cycle", fake_cycle)
    monkeypatch.setattr(proc, "write_worker_status", lambda *a, **k: None)

    worker = SimpleNamespace(
        svo_client_manager=None,
        config_path="/nonexistent/config.json",
        status_file_path=None,
        _stop_event=stop_event,
    )

    asyncio.run(proc.process_chunks(worker, poll_interval=0))

    # The client was created once and reused for all 3 cycles (no per-cycle leak).
    assert cycle_calls["n"] == 3
    assert ensure_calls["n"] == 1
    # And it is released on loop exit (Part B3).
    fake_db.disconnect.assert_called_once()


# --- Live PostgreSQL (optional; skipped without a DSN) -------------------

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


def _live_dsn() -> str:
    dsn = (os.environ.get(_PG_ENV) or "").strip()
    if not dsn:
        pytest.skip(
            f"Live PostgreSQL test skipped: set {_PG_ENV} to run (optional CI)."
        )
    return dsn


def _backend_count(dsn: str) -> int:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database()"
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0


@pytest.mark.postgres
@pytest.mark.integration
def test_live_double_connect_does_not_orphan() -> None:
    """T1: a second connect() does not double the backend connection count."""
    dsn = _live_dsn()
    # Disable the reaper thread so the count reflects connections only.
    config: Dict[str, Any] = {
        "dsn": dsn,
        "transaction_reaper_interval_seconds": 0,
    }
    driver = PostgreSQLDriver()
    baseline = _backend_count(dsn)
    try:
        driver.connect(config)
        after_first = _backend_count(dsn)
        assert after_first > baseline  # main + pool opened

        driver.connect(config)  # second connect on the SAME instance
        after_second = _backend_count(dsn)
        # Idempotent: stale main+pool were torn down, not orphaned.
        assert after_second == after_first
    finally:
        driver.disconnect()
    assert _backend_count(dsn) <= baseline + 1
