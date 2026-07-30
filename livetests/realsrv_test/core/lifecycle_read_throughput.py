"""
Read-path performance checks for project-scoped read commands (bug 8e6acb34).

Registered in ``realsrv_test.suites.s11_read_throughput`` (SUITE_NAME
"throughput").

Root cause under test -- CORRECTED (this module's docstring previously claimed
``list_project_files(page_size=1)`` has "a body cheap enough that the wall-clock
is dominated by the lock-gate select()"; that premise was wrong by roughly
800x and is replaced below with what was actually measured):

Every command carrying a literal ``project_id`` runs
``get_project_exclusive_lock()`` (the whole-project-lock gate) on its offload
worker thread BEFORE its body -- see ``commands/base_mcp_command.py``
``_gated_run()``. That gate's own ``database.select()`` cost was bottleneck
(1) (pre-fix: an unbounded ``threading.Lock`` around the driver's single main
PostgreSQL connection, serializing every concurrent project-scoped command
regardless of body cost) and has already been fixed (route through a properly
sized pooled read lane). Bottleneck (2), fixed alongside this check's
documentation, was in the command BODY itself: ``list_project_files`` (chosen
here specifically because ``page_size=1`` makes its RESPONSE cheap, not its
body) walks the project tree and re-validates ``config.json`` on every call.
Measured on this checkout before the fix: ~0.79s of GIL-bound CPU per call --
~59% re-parsing + re-validating ``config.json`` (including 8 RSA
``load_pem_private_key`` calls inside the TLS-material validator) on every
single call, ~41% enumerating the project tree. Both are now fixed: config
validation is cached per process (path + mtime + size), and the already-
declared ``*.tree``/``.log``/``.lock`` file-suffix ignore patterns are now
actually applied during enumeration instead of only pruning directory
basenames.

This module reports TWO INDEPENDENT metrics from the SAME measurement round,
because they track two different facts that must not be conflated:

1. ``read_latency_per_call_regression`` -- is the per-call BODY-COST fix
   (above) still in effect? Measured on the deployed server: 1.6.90
   sequential 13.082s / 16 calls = 0.818s/call -> 1.6.91 sequential 6.025s /
   16 calls = 0.377s/call, a 2.17x real latency improvement. That win is now
   SHIPPED and this metric is its regression guard: it asserts sequential
   per-call latency stays at or below ``_LATENCY_CEILING_SECONDS`` (0.6s).
   The ceiling is deliberately NOT set at the measured 0.377s: a shared
   server under ordinary concurrent load will legitimately run slower call
   to call, and a ceiling pinned to the exact measured value would flap on
   noise alone. 0.6s gives ~1.6x headroom over the 0.377s/call measurement
   (absorbs realistic shared-server jitter) while still catching the
   regression that matters: a reversion of either fixed bottleneck would put
   per-call latency back near 0.8s/call (roughly a 2x regression from
   0.377s), comfortably above 0.6s. Too tight (e.g. pinned near 0.377s)
   flaps on ordinary load; too loose (e.g. 1s+) would let a 2x regression
   back in silently -- 0.6s is chosen to avoid both failure modes.

2. ``read_concurrency_speedup_8e6acb34`` -- does concurrent execution
   actually overlap, or does something still serialize project-scoped reads
   process-wide? This is the ORIGINAL lock-gate/scaling question and remains
   a SEPARATE, STILL-OPEN defect (bug 8e6acb34): measured concurrency
   speedup went 0.82x -> 0.71x across the same 1.6.90 -> 1.6.91 change that
   fixed per-call latency -- concurrent calls are not overlapping, they are
   (if anything) interfering more. This metric's threshold (``speedup >=
   _MIN_SPEEDUP_FACTOR`` = 4.0x) is UNCHANGED and is expected to keep FAILING
   until 8e6acb34's scaling defect is actually fixed; its failure message
   says so explicitly so a red result here reads as a known, already-filed
   defect rather than a new regression.

Methodology (shared by both metrics): fire ``_N`` concurrent calls and time
the batch wall-clock, then run the SAME ``_N`` calls strictly sequentially
(one at a time, awaited in turn) and time that too. One warm-up call runs
first (excluded from both measurements) to absorb cold-start skew, mirroring
``lifecycle_loop_liveness.py``.

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

CHECK_NAME_LATENCY = "read_latency_per_call_regression"
CHECK_NAME_CONCURRENCY = "read_concurrency_speedup_8e6acb34"

# Bug this concurrency metric is tracking. Kept as a named constant so the
# failure message and this module's docstring cannot drift apart.
_CONCURRENCY_BUG_ID = "8e6acb34"

# Same real, sizeable pre-existing project as suite "loop" (s09) -- read-only
# commands only, no mutation. A tiny disposable fixture project would still
# exercise the lock gate (any project_id does), but reusing the same known
# project keeps this check independent of fixture project size/state.
_PROJECT_ID = "44a8ce88-b467-42a8-b874-033562b89bd0"

_N = 16
_MIN_SPEEDUP_FACTOR = 4.0
# Regression ceiling for metric 1 (latency), seconds per call, sequential.
# See module docstring for the justification of this exact value.
_LATENCY_CEILING_SECONDS = 0.6
# Runaway-detection bound (mirrors lifecycle_loop_liveness.py's rationale):
# generous enough that a slow-but-healthy run still completes and reports a
# real verdict, tight enough to catch a genuinely stuck check.
_HARD_TIMEOUT_SECONDS = 120.0

_CHEAP_READ_PARAMS = {
    "project_id": _PROJECT_ID,
    "page_size": 1,
}


async def _run_cheap_read(
    client: CodeAnalysisAsyncClient, index: int
) -> Tuple[int, bool, float, str]:
    """Run one cheap project_id-bearing read call and time it.

    Args:
        client: Connected async client.
        index: Call index, used only for diagnostics.

    Returns:
        Tuple of (index, ok, elapsed_seconds, error_text_or_empty).
    """
    t0 = time.monotonic()
    try:
        resp = await client.call_validated("list_project_files", _CHEAP_READ_PARAMS)
        ok = bool(resp.get("success"))
        err = "" if ok else truncate(str(resp.get("error")))
        return index, ok, time.monotonic() - t0, err
    except Exception as exc:  # noqa: BLE001 - recorded as data, not raised
        return index, False, time.monotonic() - t0, truncate(repr(exc))


async def _run_concurrent_batch(
    client: CodeAnalysisAsyncClient,
) -> Tuple[float, List[Tuple[int, bool, float, str]]]:
    """Fire ``_N`` calls concurrently and return (wall_clock_s, results)."""
    t0 = time.monotonic()
    tasks = [asyncio.create_task(_run_cheap_read(client, i)) for i in range(_N)]
    results = await asyncio.gather(*tasks)
    return time.monotonic() - t0, list(results)


async def _run_sequential_batch(
    client: CodeAnalysisAsyncClient,
) -> Tuple[float, List[Tuple[int, bool, float, str]]]:
    """Run the SAME ``_N`` calls strictly one at a time and return (wall_clock_s, results)."""
    t0 = time.monotonic()
    results: List[Tuple[int, bool, float, str]] = []
    for i in range(_N):
        results.append(await _run_cheap_read(client, i))
    return time.monotonic() - t0, results


def _latency_outcome(
    warmup_ok: bool, warmup_elapsed: float, warmup_err: str, seq_wall: float, seq_results
) -> Tuple[Status, str]:
    """Classify metric 1: sequential per-call latency vs the regression ceiling."""
    seq_failures = [r for r in seq_results if not r[1]]
    per_call = seq_wall / _N if _N else float("inf")
    reason = (
        f"warmup_ok={warmup_ok} warmup_elapsed_s={warmup_elapsed:.3f}"
        f"{'' if warmup_ok else f' warmup_error={warmup_err!r}'}; "
        f"N={_N} cheap_read=list_project_files(project={_PROJECT_ID}, page_size=1); "
        f"sequential_wall_s={seq_wall:.3f} (failures={len(seq_failures)}); "
        f"per_call_s={per_call:.3f}; ceiling_s={_LATENCY_CEILING_SECONDS:.3f}"
    )
    if seq_failures:
        return Status.FAILED, f"one or more sequential read calls failed: {reason}"
    if per_call > _LATENCY_CEILING_SECONDS:
        return (
            Status.FAILED,
            f"sequential per-call latency exceeded its regression ceiling: {reason}",
        )
    return (
        Status.EXECUTED_OK,
        f"sequential per-call latency within its regression ceiling: {reason}",
    )


def _concurrency_outcome(
    seq_wall: float, conc_wall: float, conc_results
) -> Tuple[Status, str]:
    """Classify metric 2: concurrency speedup vs the unchanged 4.0x threshold."""
    conc_failures = [r for r in conc_results if not r[1]]
    speedup = (seq_wall / conc_wall) if conc_wall > 0 else float("inf")
    reason = (
        f"N={_N} cheap_read=list_project_files(project={_PROJECT_ID}, page_size=1); "
        f"sequential_wall_s={seq_wall:.3f}; "
        f"concurrent_wall_s={conc_wall:.3f} (failures={len(conc_failures)}); "
        f"speedup={speedup:.2f}x; min_required={_MIN_SPEEDUP_FACTOR:.1f}x"
    )
    if conc_failures:
        return Status.FAILED, f"one or more concurrent read calls failed: {reason}"
    if speedup < _MIN_SPEEDUP_FACTOR:
        return (
            Status.FAILED,
            f"KNOWN OPEN DEFECT (bug {_CONCURRENCY_BUG_ID}, scaling regression, "
            f"NOT a new failure): concurrent reads did not speed up over "
            f"sequential as required: {reason}",
        )
    return (
        Status.EXECUTED_OK,
        f"concurrent reads sped up over sequential as expected: {reason}",
    )


async def _run_check(
    client: CodeAnalysisAsyncClient,
) -> Tuple[Tuple[Status, str], Tuple[Status, str]]:
    """Run the bounded sequential-vs-concurrent measurement once and classify both metrics.

    Args:
        client: Connected async client.

    Returns:
        ((latency_status, latency_reason), (concurrency_status, concurrency_reason)).
    """
    warmup_t0 = time.monotonic()
    _, warmup_ok, _, warmup_err = await _run_cheap_read(client, -1)
    warmup_elapsed = time.monotonic() - warmup_t0

    seq_wall, seq_results = await _run_sequential_batch(client)
    conc_wall, conc_results = await _run_concurrent_batch(client)

    latency = _latency_outcome(
        warmup_ok, warmup_elapsed, warmup_err, seq_wall, seq_results
    )
    concurrency = _concurrency_outcome(seq_wall, conc_wall, conc_results)
    return latency, concurrency


async def run_read_throughput_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bounded single-round check: two independent read-path performance metrics.

    Args:
        client: Connected async client.
        fixtures: Unused -- this check deliberately targets a real,
            pre-existing project (see module docstring), like suite "loop".

    Returns:
        Two-entry map keyed by :data:`CHECK_NAME_LATENCY` and
        :data:`CHECK_NAME_CONCURRENCY`, each with its own independent
        status/reason -- see module docstring for what each tracks.
    """
    try:
        (latency_status, latency_reason), (concurrency_status, concurrency_reason) = (
            await asyncio.wait_for(_run_check(client), timeout=_HARD_TIMEOUT_SECONDS)
        )
    except asyncio.TimeoutError:
        timeout_reason = f"check exceeded its own hard timeout of {_HARD_TIMEOUT_SECONDS}s"
        latency_status, latency_reason = Status.FAILED, timeout_reason
        concurrency_status, concurrency_reason = Status.FAILED, timeout_reason
    return {
        CHECK_NAME_LATENCY: CommandOutcome(
            CHECK_NAME_LATENCY, Bucket.BUCKET_A, latency_status, latency_reason
        ),
        CHECK_NAME_CONCURRENCY: CommandOutcome(
            CHECK_NAME_CONCURRENCY, Bucket.BUCKET_A, concurrency_status, concurrency_reason
        ),
    }
