"""
Event-loop liveness check under concurrent load (bug 4d1a2895).

Registered in ``realsrv_test.suites.s09_loop_liveness`` (SUITE_NAME "loop").

Root cause under test: ``BaseMCPCommand.run()`` used to execute the
whole-project exclusive-lock pre-check SYNCHRONOUSLY on the asyncio event
loop, before the per-command offload dispatch. Under concurrent load, this
inline blocking work can starve the single server event loop badly enough
that even a trivial, DB-free control call (``health``) cannot be scheduled
in time.

This check fires ``_HEAVY_CONCURRENCY`` concurrent read-only ``search`` calls
(fulltext only, no semantic/grep) against a real, sizeable pre-existing
project on the live server, each carrying a literal ``project_id`` kwarg so
every one of them goes through the whole-project-lock gate in ``run()``.
While that load is in flight, it repeatedly samples the lightweight
``health`` control call and records its round-trip latency. A single sample
unreliably lands on the (brief) starvation window (confirmed empirically
while designing this check), so this polls at a fixed short interval for the
whole heavy-load duration instead of firing one shot -- still one bounded
round: no retry-on-failure, hard overall timeout.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME = "loop_liveness_under_concurrent_load"

# A real, sizeable project already registered on the live server (the
# code-analyzis / CAS project itself; read-only commands only). The
# pipeline's own disposable fixture project (3 tiny files) has nowhere near
# enough fulltext corpus to make concurrent search calls take long enough to
# matter, so this check deliberately targets a pre-existing project instead
# of ``fixtures.project_id``.
_HEAVY_PROJECT_ID = "44a8ce88-b467-42a8-b874-033562b89bd0"

_HEAVY_CONCURRENCY = 32
_CONTROL_LATENCY_BUDGET_SECONDS = 10.0
_CONTROL_POLL_INTERVAL_SECONDS = 0.3
_HARD_TIMEOUT_SECONDS = 90.0

_HEAVY_SEARCH_PARAMS = {
    "query": "def ",
    "enable_semantic": False,
    "enable_grep": False,
    "fulltext_limit": 200,
    "first_block_wait_seconds": 30.0,
}


async def _run_heavy(
    client: CodeAnalysisAsyncClient, index: int
) -> Tuple[int, bool, float, str]:
    """Run one concurrent read-only ``search`` call and time it.

    Args:
        client: Connected async client.
        index: Task index, used only for diagnostics.

    Returns:
        Tuple of (index, ok, elapsed_seconds, error_text_or_empty).
    """
    t0 = time.monotonic()
    params = dict(_HEAVY_SEARCH_PARAMS)
    params["project_id"] = _HEAVY_PROJECT_ID
    try:
        resp = await client.call_validated("search", params)
        ok = bool(resp.get("success"))
        err = "" if ok else truncate(str(resp.get("error")))
        return index, ok, time.monotonic() - t0, err
    except Exception as exc:  # noqa: BLE001 - recorded as data, not raised
        return index, False, time.monotonic() - t0, truncate(repr(exc))


async def _poll_control(
    client: CodeAnalysisAsyncClient, stop_event: asyncio.Event
) -> List[Tuple[bool, float]]:
    """Sample the lightweight ``health`` control call until ``stop_event`` fires.

    Args:
        client: Connected async client.
        stop_event: Set once the heavy load has finished.

    Returns:
        List of (ok, latency_seconds) samples, one per poll.
    """
    samples: List[Tuple[bool, float]] = []
    while not stop_event.is_set():
        t0 = time.monotonic()
        try:
            resp = await client.rpc.health()
            ok = str(resp.get("status")) == "ok"
        except Exception:  # noqa: BLE001 - a failed sample is itself a FAILED signal
            ok = False
        samples.append((ok, time.monotonic() - t0))
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=_CONTROL_POLL_INTERVAL_SECONDS
            )
        except asyncio.TimeoutError:
            pass
    return samples


async def _run_check(client: CodeAnalysisAsyncClient) -> Tuple[Status, str]:
    """Run the bounded concurrent-load-vs-control-latency check once.

    Args:
        client: Connected async client.

    Returns:
        (status, reason); reason always includes the measured timings.
    """
    stop_event = asyncio.Event()
    heavy_tasks = [
        asyncio.create_task(_run_heavy(client, i)) for i in range(_HEAVY_CONCURRENCY)
    ]
    poll_task = asyncio.create_task(_poll_control(client, stop_event))
    heavy_results = await asyncio.gather(*heavy_tasks)
    stop_event.set()
    samples = await poll_task

    heavy_timings = [round(r[2], 3) for r in heavy_results]
    heavy_failures = [r for r in heavy_results if not r[1]]
    control_latencies = [s[1] for s in samples]
    max_control_latency = max(control_latencies) if control_latencies else 0.0
    control_errors = [s for s in samples if not s[0]]

    reason = (
        f"K={_HEAVY_CONCURRENCY} heavy=search(project={_HEAVY_PROJECT_ID}); "
        f"heavy_timings_s={heavy_timings}; heavy_failures={len(heavy_failures)}; "
        f"control_samples={len(samples)}; "
        f"max_control_latency_s={max_control_latency:.3f}; "
        f"control_errors={len(control_errors)}; "
        f"budget_s={_CONTROL_LATENCY_BUDGET_SECONDS}"
    )

    if control_errors:
        return (
            Status.FAILED,
            f"control call errored while heavy load was in flight: {reason}",
        )
    if max_control_latency > _CONTROL_LATENCY_BUDGET_SECONDS:
        return Status.FAILED, f"control call exceeded latency budget: {reason}"
    return Status.EXECUTED_OK, f"control call stayed within budget: {reason}"


async def run_loop_liveness_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bounded single-round check: does concurrent read load starve the main loop?

    Args:
        client: Connected async client.
        fixtures: Unused -- this check deliberately targets a real,
            pre-existing project with a large fulltext corpus instead of the
            pipeline's own disposable fixture project (see module docstring).

    Returns:
        ``{CHECK_NAME: outcome}`` -- single-entry map, like every check in
        this package.
    """
    try:
        status, reason = await asyncio.wait_for(
            _run_check(client), timeout=_HARD_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        status, reason = (
            Status.FAILED,
            f"check exceeded its own hard timeout of {_HARD_TIMEOUT_SECONDS}s",
        )
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}
