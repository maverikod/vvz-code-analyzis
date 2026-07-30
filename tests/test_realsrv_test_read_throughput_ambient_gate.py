"""
Unit tests: read-throughput's ambient-load gate and INCONCLUSIVE timeout (bug 2aaac911).

``lifecycle_read_throughput.py``'s two metrics
(``read_latency_per_call_regression`` / ``read_concurrency_speedup_8e6acb34``)
must not report a FAILED verdict that is really just neighbouring-load noise.
These tests stub the client and the shared
``realsrv_test.core.ambient_load.probe_ambient_load`` symbol as imported
into ``lifecycle_read_throughput`` (monkeypatched there, not re-derived from
real sleeps) and pin:

1. A degraded pre-measurement probe short-circuits BOTH metrics to
   :attr:`Status.INCONCLUSIVE`, naming the probe's own numbers, and never
   issues a single timed measurement call (no warmup/sequential/concurrent
   traffic wasted on a round nobody would trust).
2. A clean probe lets the real measurement proceed -- both metrics reach the
   client for their full call budget (1 warmup + 16 sequential + 16
   concurrent = 33 calls).
3. The check's own hard timeout reports :attr:`Status.INCONCLUSIVE` on both
   metrics, not :attr:`Status.FAILED`.

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

from realsrv_test.core import lifecycle_read_throughput as lrt  # noqa: E402
from realsrv_test.core.catalog import Status  # noqa: E402


class _StubClient:
    """Records every ``call_validated`` call; always reports success fast."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def call_validated(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        assert command == "list_project_files"
        self.calls.append(dict(params))
        return {"success": True, "data": {"items": []}}


async def _degraded_probe_stub(client, project_id):
    return True, 0.5, "attempt1_avg_s=0.5000(failures=0)"


async def _clean_probe_stub(client, project_id):
    return False, 0.005, "attempt1_avg_s=0.0050(failures=0)"


@pytest.mark.asyncio
async def test_degraded_probe_short_circuits_both_metrics_to_inconclusive(
    monkeypatch,
) -> None:
    monkeypatch.setattr(lrt, "probe_ambient_load", _degraded_probe_stub)
    client = _StubClient()

    outcomes = await lrt.run_read_throughput_check(client, fixtures=None)

    latency = outcomes[lrt.CHECK_NAME_LATENCY]
    concurrency = outcomes[lrt.CHECK_NAME_CONCURRENCY]
    assert latency.status == Status.INCONCLUSIVE, latency.reason
    assert concurrency.status == Status.INCONCLUSIVE, concurrency.reason
    assert "ambient load detected" in latency.reason
    assert "ambient load detected" in concurrency.reason
    assert "0.5000" in latency.reason
    # Exactly 1 call: the warm-up (runs BEFORE the probe, absorbing cold-
    # start skew like every other check) -- a degraded probe must still
    # skip the real sequential/concurrent measurement traffic (16 + 16).
    assert len(client.calls) == 1, "a degraded probe must skip the timed measurement batches"


@pytest.mark.asyncio
async def test_clean_probe_lets_the_real_measurement_proceed(monkeypatch) -> None:
    monkeypatch.setattr(lrt, "probe_ambient_load", _clean_probe_stub)
    client = _StubClient()

    outcomes = await lrt.run_read_throughput_check(client, fixtures=None)

    latency = outcomes[lrt.CHECK_NAME_LATENCY]
    concurrency = outcomes[lrt.CHECK_NAME_CONCURRENCY]
    # A clean probe must not itself produce an INCONCLUSIVE verdict -- the
    # real measurement ran and reached a real classification.
    assert latency.status != Status.INCONCLUSIVE, latency.reason
    assert concurrency.status != Status.INCONCLUSIVE, concurrency.reason
    # 1 warmup + 16 sequential + 16 concurrent = 33 real timed calls.
    assert len(client.calls) == 33


@pytest.mark.asyncio
async def test_hard_timeout_reports_inconclusive_not_failed(monkeypatch) -> None:
    async def _stalled_probe(client, project_id):
        await asyncio.sleep(1.0)
        return False, 0.0, "unreachable"

    monkeypatch.setattr(lrt, "probe_ambient_load", _stalled_probe)
    monkeypatch.setattr(lrt, "_HARD_TIMEOUT_SECONDS", 0.01)
    client = _StubClient()

    outcomes = await lrt.run_read_throughput_check(client, fixtures=None)

    latency = outcomes[lrt.CHECK_NAME_LATENCY]
    concurrency = outcomes[lrt.CHECK_NAME_CONCURRENCY]
    assert latency.status == Status.INCONCLUSIVE, latency.reason
    assert concurrency.status == Status.INCONCLUSIVE, concurrency.reason
    assert "hard timeout" in latency.reason
    assert "hard timeout" in concurrency.reason
    assert "not a code regression" in latency.reason
