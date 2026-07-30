"""
Unit tests: the shared ambient-load pre-measurement probe (bug 2aaac911).

``realsrv_test.core.ambient_load`` is the shared building block every
timing-sensitive check (``lifecycle_read_throughput.py``,
``lifecycle_measurement_stability.py``) uses to notice, BEFORE it measures
anything, that the server already looks busy with work it does not control.
These tests stub the client entirely (no live server, no real sleeping past
what the test itself controls) and pin the probe's core contract:

1. A fast, all-success round is never degraded.
2. A round whose average call time exceeds the ceiling IS degraded.
3. A single call failure marks the round degraded even if it was fast.
4. ``probe_ambient_load`` retries up to its bound, stops early once a round
   clears, and reports every attempt in its detail string.
5. ``probe_ambient_load`` reports degraded only when EVERY attempt stayed
   degraded (never silently swallows a still-bad final state).
6. ``probe_once`` never retries or sleeps -- exactly one round, deterministic.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_LIVETESTS_DIR = Path(__file__).resolve().parents[1] / "livetests"
if str(_LIVETESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_LIVETESTS_DIR))

from realsrv_test.core.ambient_load import probe_ambient_load, probe_once  # noqa: E402


class _StubClient:
    """Records every ``call_validated`` call; each call optionally sleeps.

    ``elapsed_per_call`` is a queue of per-call sleep durations (seconds),
    consumed one at a time; the last value repeats once exhausted.
    ``fail_calls`` names 1-based call indices (across the whole client's
    lifetime) that should report ``success: False``.
    """

    def __init__(
        self,
        *,
        elapsed_per_call: List[float] | None = None,
        fail_calls: set | None = None,
    ) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._elapsed_per_call = elapsed_per_call or [0.0]
        self._fail_calls = fail_calls or set()

    async def call_validated(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        assert command == "list_project_files"
        index = len(self.calls) + 1
        self.calls.append(dict(params))
        delay_index = min(index - 1, len(self._elapsed_per_call) - 1)
        delay = self._elapsed_per_call[delay_index]
        if delay:
            await asyncio.sleep(delay)
        if index in self._fail_calls:
            return {"success": False, "error": "boom"}
        return {"success": True, "data": {"items": []}}


@pytest.mark.asyncio
async def test_probe_once_fast_success_round_is_not_degraded() -> None:
    client = _StubClient(elapsed_per_call=[0.0])
    degraded, avg, failures = await probe_once(
        client, "proj-1", samples=3, ceiling_seconds=0.03
    )
    assert degraded is False
    assert failures == 0
    assert avg < 0.03
    assert len(client.calls) == 3
    assert all(p == {"project_id": "proj-1", "page_size": 1} for p in client.calls)


@pytest.mark.asyncio
async def test_probe_once_slow_round_is_degraded() -> None:
    client = _StubClient(elapsed_per_call=[0.02])
    degraded, avg, failures = await probe_once(
        client, "proj-1", samples=3, ceiling_seconds=0.01
    )
    assert degraded is True
    assert failures == 0
    assert avg >= 0.01


@pytest.mark.asyncio
async def test_probe_once_a_single_failure_marks_the_round_degraded() -> None:
    client = _StubClient(elapsed_per_call=[0.0], fail_calls={2})
    degraded, avg, failures = await probe_once(
        client, "proj-1", samples=3, ceiling_seconds=0.03
    )
    assert degraded is True
    assert failures == 1


@pytest.mark.asyncio
async def test_probe_once_never_retries_or_sleeps_between_calls() -> None:
    """Exactly ``samples`` calls, no more -- no retry logic in probe_once."""
    client = _StubClient(elapsed_per_call=[0.0])
    await probe_once(client, "proj-1", samples=3, ceiling_seconds=0.03)
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_probe_ambient_load_stops_early_once_a_round_clears() -> None:
    """Degraded on attempt 1, clean on attempt 2 -> degraded=False, 2 attempts only."""
    client = _StubClient(elapsed_per_call=[0.02, 0.02, 0.02, 0.0, 0.0, 0.0])
    degraded, avg, detail = await probe_ambient_load(
        client,
        "proj-1",
        samples=3,
        ceiling_seconds=0.01,
        max_attempts=3,
        retry_delay_seconds=0.001,
    )
    assert degraded is False
    assert avg < 0.01
    assert len(client.calls) == 6  # exactly two attempts of 3 samples each
    assert "attempt1_avg_s=" in detail
    assert "attempt2_avg_s=" in detail
    assert "attempt3_avg_s=" not in detail


@pytest.mark.asyncio
async def test_probe_ambient_load_reports_degraded_only_after_exhausting_attempts() -> None:
    """Every attempt stays degraded -> degraded=True, detail names all attempts."""
    client = _StubClient(elapsed_per_call=[0.02])
    degraded, avg, detail = await probe_ambient_load(
        client,
        "proj-1",
        samples=2,
        ceiling_seconds=0.01,
        max_attempts=2,
        retry_delay_seconds=0.001,
    )
    assert degraded is True
    assert avg >= 0.01
    assert len(client.calls) == 4  # two attempts of 2 samples each, no early stop
    assert "attempt1_avg_s=" in detail
    assert "attempt2_avg_s=" in detail


@pytest.mark.asyncio
async def test_probe_ambient_load_single_attempt_when_first_round_clears() -> None:
    client = _StubClient(elapsed_per_call=[0.0])
    degraded, _avg, detail = await probe_ambient_load(
        client,
        "proj-1",
        samples=3,
        ceiling_seconds=0.03,
        max_attempts=2,
        retry_delay_seconds=0.001,
    )
    assert degraded is False
    assert len(client.calls) == 3
    assert "attempt2_avg_s=" not in detail
