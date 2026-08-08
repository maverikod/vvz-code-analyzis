"""
Unit tests: s15 re-aimed as an ambient-load-DETECTION contract check (bug 2aaac911).

``lifecycle_measurement_stability.py`` (suite "stability", ``pipeline
live-stability``) used to assert a fixed absolute divergence ceiling under
self-generated concurrent load -- retired because it landed at 6.50x on the
real deployed server even with nothing else running (an intrinsic
GIL/request-path property, bug 8e6acb34's territory, not this bug's). It now
asserts the DETECTION mechanism itself (``realsrv_test.core.ambient_load``)
correctly recognizes genuine self-generated concurrent interference. These
tests stub the client and the ``probe_ambient_load`` / ``probe_once``
symbols as imported into ``lifecycle_measurement_stability`` and pin:

1. A degraded quiet-phase probe (unrelated load already present) reports
   :attr:`Status.INCONCLUSIVE`, never reaches the loaded phase.
2. A clean quiet phase followed by a loaded-phase probe that correctly
   reports degraded reports :attr:`Status.EXECUTED_OK` -- the detection
   mechanism worked.
3. A clean quiet phase followed by a loaded-phase probe that WRONGLY reports
   clean (a detection defect) reports :attr:`Status.FAILED` -- a real code
   defect in the detection mechanism, not a server-speed complaint.
4. The check's own hard timeout reports :attr:`Status.INCONCLUSIVE`, not
   :attr:`Status.FAILED`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

_LIVETESTS_DIR = Path(__file__).resolve().parents[1] / "livetests"
if str(_LIVETESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_LIVETESTS_DIR))

from realsrv_test.core import lifecycle_measurement_stability as lms  # noqa: E402
from realsrv_test.core.catalog import Status  # noqa: E402


class _StubClient:
    """Always reports success fast for ``list_project_files``."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def call_validated(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        assert command == "list_project_files"
        self.calls.append(dict(params))
        return {"success": True, "data": {"items": []}}


def _fixtures() -> SimpleNamespace:
    return SimpleNamespace(project_id="proj-1")


async def _degraded_ambient_load(client, project_id):
    return True, 0.5, "attempt1_avg_s=0.5000(failures=0); attempt2_avg_s=0.4000(failures=0)"


async def _clean_ambient_load(client, project_id):
    return False, 0.005, "attempt1_avg_s=0.0050(failures=0)"


async def _clean_probe_once(client, project_id, *, baseline_seconds=None):
    """Stub: the loaded probe sees nothing (detection missed the interference).

    Accepts ``baseline_seconds`` because the check now judges the loaded phase
    against the baseline it measured in the same run rather than a constant
    (bug 2aaac911 guard); a stub that omits it would only prove the stub's own
    signature is stale.
    """
    return False, 0.005, 0


async def _degraded_probe_once(client, project_id, *, baseline_seconds=None):
    """Stub: the loaded probe correctly flags the interference."""
    return True, 0.09, 0


@pytest.mark.asyncio
async def test_degraded_quiet_phase_reports_inconclusive_never_reaches_loaded_phase(
    monkeypatch,
) -> None:
    monkeypatch.setattr(lms, "probe_ambient_load", _degraded_ambient_load)
    load_called = False

    async def _tripwire_probe_once(client, project_id):
        nonlocal load_called
        load_called = True
        return False, 0.0, 0

    monkeypatch.setattr(lms, "probe_once", _tripwire_probe_once)
    client = _StubClient()

    outcomes = await lms.run_measurement_stability_check(client, _fixtures())

    outcome = outcomes[lms.CHECK_NAME]
    assert outcome.status == Status.INCONCLUSIVE, outcome.reason
    assert "quiet-phase probe was already degraded" in outcome.reason
    assert load_called is False


@pytest.mark.asyncio
async def test_loaded_phase_correctly_flagged_reports_executed_ok(monkeypatch) -> None:
    monkeypatch.setattr(lms, "probe_ambient_load", _clean_ambient_load)
    monkeypatch.setattr(lms, "probe_once", _degraded_probe_once)
    client = _StubClient()

    outcomes = await lms.run_measurement_stability_check(client, _fixtures())

    outcome = outcomes[lms.CHECK_NAME]
    assert outcome.status == Status.EXECUTED_OK, outcome.reason
    assert "correctly flagged" in outcome.reason
    # The background load batch itself still ran against the stub client.
    assert len(client.calls) >= lms._LOAD_CONCURRENCY


@pytest.mark.asyncio
async def test_loaded_phase_missed_by_detection_reports_failed(monkeypatch) -> None:
    monkeypatch.setattr(lms, "probe_ambient_load", _clean_ambient_load)
    monkeypatch.setattr(lms, "probe_once", _clean_probe_once)
    client = _StubClient()

    outcomes = await lms.run_measurement_stability_check(client, _fixtures())

    outcome = outcomes[lms.CHECK_NAME]
    assert outcome.status == Status.FAILED, outcome.reason
    assert "FAILED to flag" in outcome.reason
    assert "detection defect" in outcome.reason


@pytest.mark.asyncio
async def test_hard_timeout_reports_inconclusive_not_failed(monkeypatch) -> None:
    async def _stalled_ambient_load(client, project_id):
        await asyncio.sleep(1.0)
        return False, 0.0, "unreachable"

    monkeypatch.setattr(lms, "probe_ambient_load", _stalled_ambient_load)
    monkeypatch.setattr(lms, "_HARD_TIMEOUT_SECONDS", 0.01)
    client = _StubClient()

    outcomes = await lms.run_measurement_stability_check(client, _fixtures())

    outcome = outcomes[lms.CHECK_NAME]
    assert outcome.status == Status.INCONCLUSIVE, outcome.reason
    assert "hard timeout" in outcome.reason
