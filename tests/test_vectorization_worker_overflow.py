"""
Regression tests for TZ-CA-VECTORIZATION-WORKER-OVERFLOW-001.

A-5: a circuit_breaker-open state with infinite/huge backoff_delay must not
     let OverflowError escape the poll-interval tail; the worker must keep
     cycling without human intervention.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.core.svo_client_manager import CircuitState
from code_analysis.core.vectorization_worker_pkg.processing import (
    _MAX_POLL_INTERVAL,
    process_chunks,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_self(stop_event: asyncio.Event, svo: object) -> MagicMock:
    """Minimal mock of VectorizationWorker needed by process_chunks."""
    m = MagicMock()
    m.config_path = "/nonexistent/config.json"  # triggers except→drv_type="unknown"
    m.db_path = None
    m.status_file_path = None
    m._stop_event = stop_event
    m.svo_client_manager = svo
    return m


def _open_svo(backoff_delay: float) -> MagicMock:
    svo = MagicMock()
    svo.get_circuit_state.return_value = CircuitState(
        state="open", failures=999, opened_at=0.0
    )
    svo.get_backoff_delay.return_value = backoff_delay
    return svo


async def _fake_ensure_db(self, cfg_path, *, db_available, db_status_logged, backoff, backoff_max):
    fake_db = MagicMock()
    fake_db.disconnect = MagicMock()
    return (fake_db, True, backoff, db_status_logged)


def _make_fake_run_one_cycle(stop_event: asyncio.Event, cycles_done: list):
    async def _inner(self, db, cycle_count, total_processed, total_errors):
        cycles_done.append(cycle_count)
        stop_event.set()  # one cycle is enough; stop the outer while loop
        return (0, 0, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0)

    return _inner


# ---------------------------------------------------------------------------
# A-5.1: float('inf') backoff must not produce OverflowError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_infinite_backoff_does_not_raise_overflow():
    """
    backoff_delay=inf previously caused int(inf) → OverflowError that killed the worker.
    After A-1+A-2 the tail is guarded and clamped; the worker must complete cleanly.
    """
    stop_event = asyncio.Event()
    cycles_done: list = []

    self_mock = _make_self(stop_event, _open_svo(float("inf")))
    fake_cycle = _make_fake_run_one_cycle(stop_event, cycles_done)

    with (
        patch(
            "code_analysis.core.vectorization_worker_pkg.processing.ensure_database_connection",
            _fake_ensure_db,
        ),
        patch(
            "code_analysis.core.vectorization_worker_pkg.processing.run_one_cycle",
            fake_cycle,
        ),
        patch(
            "code_analysis.core.vectorization_worker_pkg.processing.write_worker_status"
        ),
    ):
        result = await process_chunks(self_mock, poll_interval=30)

    assert len(cycles_done) == 1, "worker must complete at least one cycle"
    assert result["processed"] == 0


# ---------------------------------------------------------------------------
# A-5.2: very large finite float (> C ssize_t) is also clamped safely
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_huge_float_backoff_does_not_raise_overflow():
    """1e308 is a legal Python float but int(1e308) overflows C ssize_t on 64-bit."""
    stop_event = asyncio.Event()
    cycles_done: list = []

    self_mock = _make_self(stop_event, _open_svo(1e308))
    fake_cycle = _make_fake_run_one_cycle(stop_event, cycles_done)

    with (
        patch(
            "code_analysis.core.vectorization_worker_pkg.processing.ensure_database_connection",
            _fake_ensure_db,
        ),
        patch(
            "code_analysis.core.vectorization_worker_pkg.processing.run_one_cycle",
            fake_cycle,
        ),
        patch(
            "code_analysis.core.vectorization_worker_pkg.processing.write_worker_status"
        ),
    ):
        result = await process_chunks(self_mock, poll_interval=30)

    assert len(cycles_done) == 1
    assert result["processed"] == 0


# ---------------------------------------------------------------------------
# A-5.3: _MAX_POLL_INTERVAL constant enforces the ceiling
# ---------------------------------------------------------------------------


def test_max_poll_interval_ceiling():
    """_MAX_POLL_INTERVAL must be a finite int ≤ 3600 so range() never overflows."""
    assert isinstance(_MAX_POLL_INTERVAL, int)
    assert _MAX_POLL_INTERVAL <= 3600
    # Sanity: range() must not raise for the ceiling value
    assert len(range(_MAX_POLL_INTERVAL)) == _MAX_POLL_INTERVAL


# ---------------------------------------------------------------------------
# A-3 (config validator upper bounds)
# ---------------------------------------------------------------------------


def test_config_validator_rejects_huge_max_backoff():
    from code_analysis.core.config_validator.section_code_analysis import (
        validate_code_analysis_section_impl,
    )

    results: list = []
    validate_code_analysis_section_impl(
        {
            "code_analysis": {
                "worker": {
                    "circuit_breaker": {
                        "max_backoff": 9999,
                        "initial_backoff": 1,
                    }
                }
            }
        },
        results,
    )
    keys = [r.key for r in results]
    assert "worker.circuit_breaker.max_backoff" in keys


def test_config_validator_rejects_huge_backoff_multiplier():
    from code_analysis.core.config_validator.section_code_analysis import (
        validate_code_analysis_section_impl,
    )

    results: list = []
    validate_code_analysis_section_impl(
        {
            "code_analysis": {
                "worker": {
                    "circuit_breaker": {
                        "backoff_multiplier": 100,
                        "initial_backoff": 1,
                        "max_backoff": 60,
                    }
                }
            }
        },
        results,
    )
    keys = [r.key for r in results]
    assert "worker.circuit_breaker.backoff_multiplier" in keys


def test_config_validator_accepts_valid_circuit_breaker():
    from code_analysis.core.config_validator.section_code_analysis import (
        validate_code_analysis_section_impl,
    )

    results: list = []
    validate_code_analysis_section_impl(
        {
            "code_analysis": {
                "worker": {
                    "circuit_breaker": {
                        "failure_threshold": 3,
                        "recovery_timeout": 60,
                        "success_threshold": 1,
                        "initial_backoff": 5,
                        "max_backoff": 300,
                        "backoff_multiplier": 2,
                    }
                }
            }
        },
        results,
    )
    assert results == [], f"Expected no errors, got: {results}"
