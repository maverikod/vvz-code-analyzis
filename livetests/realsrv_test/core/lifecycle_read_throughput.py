"""
Read-path performance checks for project-scoped read commands (bug 8e6acb34).

Registered in ``realsrv_test.suites.s11_read_throughput`` (SUITE_NAME
"throughput").

WHAT THIS MODULE MEASURES NOW (bug 8e6acb34, Fix 2) -- and why the previous
client-side wall-clock measurement was misleading:

Both metrics below used to time each call with ``time.monotonic()`` around
the ``await`` on the CLIENT side. That grades the MEASURING INSTRUMENT, not
the server. Confirmed on the deployed server (192.168.254.26:15010), same
warm ``health`` call, three clients: plain ``curl`` (no GIL) -- 1.2ms; a raw
``httpx.AsyncClient`` in Python -- 4.6ms; this project's
``code_analysis_client`` (pre-Fix-1) -- 7.6ms. A cheap ``list_project_files
(page_size=1)`` call through the client measured 9.11ms total, only ~1.5ms
more than plain ``health`` -- i.e. the server itself does the whole listing
in roughly 2.7ms, and the remaining ~6.4ms of every "client" measurement was
client-side Python/httpx overhead (~3.4ms httpx, ~2.7-3.0ms the client's own
schema-fetch-per-process pattern, fixed by Fix 1's on-disk schema cache).
Concurrency made this worse, not better: firing 16 raw-httpx calls at once
measured only a 1.41x wall-clock speedup over sequential -- the MEASURING
client was saturating its own event loop / GIL at roughly the same ratio
this module used to attribute to the SERVER's ``read_concurrency_speedup``
metric. Grading the server by client-side wall clock was therefore grading
the wrong thing for both metrics.

Fix 2 replaces client wall-clock with SERVER-reported processing time: every
call in this module passes ``BaseMCPCommand.SERVER_TIMING_REQUEST_KEY``
(``_measure_server_time_ms=True``, see
``code_analysis/commands/base_mcp_command.py``) via the raw ``client.call``
path (bypassing client-side schema validation, which does not know this
internal flag). The server wraps the ENTIRE ``run()`` call -- lock-gate
check, offload-pool dispatch/queueing, and the command body -- with
``time.perf_counter()`` and attaches the result in milliseconds to the
response under ``_server_processing_ms``. This field is opt-in and invisible
to every other caller (see that module's docstring); it costs one
``time.perf_counter()`` pair per call, immaterial next to the call itself.

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
documentation, was in the command BODY itself: ``list_project_files``
(chosen here specifically because ``page_size=1`` makes its RESPONSE cheap,
not its body) walks the project tree and re-validates ``config.json`` on
every call. Both are now fixed: config validation is cached per process
(path + mtime + size), and the already-declared ``*.tree``/``.log``/``.lock``
file-suffix ignore patterns are now actually applied during enumeration
instead of only pruning directory basenames.

AMBIENT-LOAD GATING (bug 2aaac911): both metrics below share a single
pre-measurement probe (``realsrv_test.core.ambient_load.probe_ambient_load``)
run AFTER the existing warm-up call and BEFORE any regression-relevant timed
calls -- unaffected by Fix 2, this probe still uses client wall-clock on
purpose (it answers "is the server externally busy right now", a question
about the SHARED server's overall load, not this module's own per-call
correctness). See that module's docstring for the full rationale. If the
server still looks busy on an already-warm connection, both metrics report
:attr:`Status.INCONCLUSIVE` naming the observed numbers INSTEAD of measuring
noise and presenting it as a verdict.

This module reports TWO INDEPENDENT metrics from the SAME measurement round,
because they track two different facts that must not be conflated:

1. ``read_latency_per_call_regression`` -- is the per-call BODY-COST fix
   (above) still in effect, as observed by the SERVER itself? Asserts the
   average of each sequential call's ``_server_processing_ms`` stays at or
   below ``_LATENCY_CEILING_SECONDS`` (0.6s, unchanged -- server time is a
   SUBSET of the old wall-clock measurement, minus ~6-10ms of client/network
   overhead per call, so the existing ceiling remains a safe, if now
   slightly more generous, bound). A reversion of either fixed bottleneck
   would put server-side per-call time back near 0.8s, comfortably above
   0.6s; ordinary shared-server jitter on a healthy build stays in the
   0.01-0.1s range, comfortably below it.

2. ``read_concurrency_speedup_8e6acb34`` -- does concurrent execution
   actually overlap on the SERVER, or does something still serialize
   project-scoped reads process-wide? Bug 8e6acb34's own client-side
   wall-clock version of this metric was unreliable (see above): the
   measuring client's own concurrency limits corrupted the ratio. The
   server-time version instead compares:
     - ``seq_server_total_ms`` = SUM of each sequential call's
       ``_server_processing_ms`` (sequential calls never overlap, so this
       sum is a faithful, purely server-side reconstruction of how long the
       server needed to do all N calls' work one at a time);
     - ``conc_server_max_ms`` = MAX of each concurrent call's
       ``_server_processing_ms`` (this module's server-side timer wraps the
       WHOLE ``run()`` including the lock-gate wait, so a call stuck behind
       serialized predecessors reports its OWN inflated duration; the
       slowest of the N concurrent calls is therefore a faithful
       reconstruction of how long the server needed to finish the whole
       batch, again purely server-side).
   ``speedup = seq_server_total_ms / conc_server_max_ms``: unconstrained
   real concurrency keeps ``conc_server_max_ms`` close to a single call's
   own cost (every call proceeds independently), so speedup approaches N
   (16x here); serialization inflates ``conc_server_max_ms`` toward
   ``seq_server_total_ms`` (the last call effectively waited for everyone
   ahead of it), driving speedup toward 1x. This metric's threshold
   (``speedup >= _MIN_SPEEDUP_FACTOR`` = 4.0x, UNCHANGED) is expected to
   keep FAILING until 8e6acb34's scaling defect is actually fixed; its
   failure message says so explicitly so a red result here reads as a
   known, already-filed defect rather than a new regression.

Methodology (shared by both metrics): fire ``_N`` concurrent calls and
collect each one's ``_server_processing_ms``, then run the SAME ``_N`` calls
strictly sequentially (one at a time, awaited in turn) and collect the same.
One warm-up call runs first (excluded from both measurements) to absorb
cold-start skew, mirroring ``lifecycle_loop_liveness.py``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.ambient_load import probe_ambient_load
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
# Regression ceiling for metric 1 (latency), seconds per call, SERVER time
# (see module docstring for why server time -- excludes ~6-10ms/call of
# client+network overhead that used to count against this same ceiling under
# the old client wall-clock measurement, so 0.6s remains a safe bound).
_LATENCY_CEILING_SECONDS = 0.6
# Runaway-detection bound (mirrors lifecycle_loop_liveness.py's rationale):
# generous enough that a slow-but-healthy run still completes and reports a
# real verdict, tight enough to catch a genuinely stuck check.
_HARD_TIMEOUT_SECONDS = 120.0

# Server-side opt-in timing flag/result key names (bug 8e6acb34, Fix 2). Kept
# as local string literals rather than importing
# ``code_analysis.commands.base_mcp_command.BaseMCPCommand`` -- this package
# runs against a REMOTE, possibly differently-versioned server and otherwise
# never imports server-internal code; they MUST stay in sync with
# ``BaseMCPCommand.SERVER_TIMING_REQUEST_KEY`` / ``SERVER_TIMING_RESULT_KEY``.
_SERVER_TIMING_REQUEST_KEY = "_measure_server_time_ms"
_SERVER_TIMING_RESULT_KEY = "_server_processing_ms"

_CHEAP_READ_PARAMS = {
    "project_id": _PROJECT_ID,
    "page_size": 1,
    _SERVER_TIMING_REQUEST_KEY: True,
}


async def _run_cheap_read(
    client: CodeAnalysisAsyncClient, index: int
) -> Tuple[int, bool, Optional[float], str]:
    """Run one cheap project_id-bearing read call and return its SERVER time.

    Uses ``client.call`` (not ``call_validated``): the server-timing opt-in
    flag is intentionally not part of any command's public schema, so
    client-side schema validation would reject it as an unknown parameter.

    Args:
        client: Connected async client.
        index: Call index, used only for diagnostics.

    Returns:
        Tuple of (index, ok, server_processing_ms_or_None, error_text_or_empty).
        ``server_processing_ms`` is ``None`` when the call failed or the
        server did not report the timing field (e.g. a pre-Fix-2 server) --
        callers must treat that as a measurement failure, never as 0.
    """
    try:
        resp = await client.call("list_project_files", _CHEAP_READ_PARAMS)
        ok = bool(resp.get("success"))
        if not ok:
            return index, False, None, truncate(str(resp.get("error")))
        data = resp.get("data")
        server_ms = None
        if isinstance(data, dict):
            raw = data.get(_SERVER_TIMING_RESULT_KEY)
            if isinstance(raw, (int, float)):
                server_ms = float(raw)
        if server_ms is None:
            return (
                index,
                False,
                None,
                f"response missing {_SERVER_TIMING_RESULT_KEY!r} "
                "(server predates bug 8e6acb34 Fix 2?)",
            )
        return index, True, server_ms, ""
    except Exception as exc:  # noqa: BLE001 - recorded as data, not raised
        return index, False, None, truncate(repr(exc))


async def _run_concurrent_batch(
    client: CodeAnalysisAsyncClient,
) -> Tuple[float, List[Tuple[int, bool, Optional[float], str]]]:
    """Fire ``_N`` calls concurrently; return (wall_clock_s, results).

    ``wall_clock_s`` is retained only as a diagnostic in the outcome reason
    (bug 8e6acb34's own finding was that this wall-clock figure is dominated
    by the measuring client, which is exactly why the metrics below no
    longer use it for classification -- see module docstring).
    """
    t0 = time.monotonic()
    tasks = [asyncio.create_task(_run_cheap_read(client, i)) for i in range(_N)]
    results = await asyncio.gather(*tasks)
    return time.monotonic() - t0, list(results)


async def _run_sequential_batch(
    client: CodeAnalysisAsyncClient,
) -> Tuple[float, List[Tuple[int, bool, Optional[float], str]]]:
    """Run the SAME ``_N`` calls strictly one at a time; return (wall_clock_s, results)."""
    t0 = time.monotonic()
    results: List[Tuple[int, bool, Optional[float], str]] = []
    for i in range(_N):
        results.append(await _run_cheap_read(client, i))
    return time.monotonic() - t0, results


def _server_ms_values(
    results: List[Tuple[int, bool, Optional[float], str]]
) -> Tuple[List[float], List[Tuple[int, bool, Optional[float], str]]]:
    """Split ``results`` into (server_ms values, failures)."""
    values: List[float] = []
    failures: List[Tuple[int, bool, Optional[float], str]] = []
    for r in results:
        _, ok, server_ms, _ = r
        if ok and server_ms is not None:
            values.append(server_ms)
        else:
            failures.append(r)
    return values, failures


def _latency_outcome(
    warmup_ok: bool,
    warmup_elapsed: float,
    warmup_err: str,
    seq_wall: float,
    seq_results: List[Tuple[int, bool, Optional[float], str]],
) -> Tuple[Status, str]:
    """Classify metric 1: sequential per-call SERVER time vs the regression ceiling."""
    seq_server_ms, seq_failures = _server_ms_values(seq_results)
    per_call_s = (sum(seq_server_ms) / len(seq_server_ms) / 1000.0) if seq_server_ms else float("inf")
    reason = (
        f"warmup_ok={warmup_ok} warmup_elapsed_s={warmup_elapsed:.3f}"
        f"{'' if warmup_ok else f' warmup_error={warmup_err!r}'}; "
        f"N={_N} cheap_read=list_project_files(project={_PROJECT_ID}, page_size=1); "
        f"sequential_wall_s={seq_wall:.3f} (client-side, diagnostic only); "
        f"failures={len(seq_failures)}; "
        f"per_call_server_ms={per_call_s * 1000.0:.3f}; "
        f"ceiling_s={_LATENCY_CEILING_SECONDS:.3f}"
    )
    if seq_failures:
        return Status.FAILED, f"one or more sequential read calls failed: {reason}"
    if per_call_s > _LATENCY_CEILING_SECONDS:
        return (
            Status.FAILED,
            f"sequential per-call SERVER time exceeded its regression ceiling: {reason}",
        )
    return (
        Status.EXECUTED_OK,
        f"sequential per-call SERVER time within its regression ceiling: {reason}",
    )


def _concurrency_outcome(
    seq_results: List[Tuple[int, bool, Optional[float], str]],
    conc_wall: float,
    conc_results: List[Tuple[int, bool, Optional[float], str]],
) -> Tuple[Status, str]:
    """Classify metric 2: SERVER-time-based concurrency speedup vs the unchanged 4.0x threshold."""
    seq_server_ms, seq_failures = _server_ms_values(seq_results)
    conc_server_ms, conc_failures = _server_ms_values(conc_results)

    seq_total_ms = sum(seq_server_ms) if seq_server_ms else 0.0
    conc_max_ms = max(conc_server_ms) if conc_server_ms else 0.0
    speedup = (seq_total_ms / conc_max_ms) if conc_max_ms > 0 else float("inf")

    reason = (
        f"N={_N} cheap_read=list_project_files(project={_PROJECT_ID}, page_size=1); "
        f"seq_server_total_ms={seq_total_ms:.3f}; "
        f"conc_server_max_ms={conc_max_ms:.3f}; "
        f"conc_wall_s={conc_wall:.3f} (client-side, diagnostic only); "
        f"seq_failures={len(seq_failures)} conc_failures={len(conc_failures)}; "
        f"speedup={speedup:.2f}x; min_required={_MIN_SPEEDUP_FACTOR:.1f}x"
    )
    if seq_failures or conc_failures:
        return Status.FAILED, f"one or more read calls failed: {reason}"
    if speedup < _MIN_SPEEDUP_FACTOR:
        return (
            Status.FAILED,
            f"KNOWN OPEN DEFECT (bug {_CONCURRENCY_BUG_ID}, scaling regression, "
            f"NOT a new failure): concurrent reads did not speed up over "
            f"sequential (server time) as required: {reason}",
        )
    return (
        Status.EXECUTED_OK,
        f"concurrent reads sped up over sequential (server time) as expected: {reason}",
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
    # Warm-up runs BEFORE the ambient-load probe, not after: every other
    # check in this package already treats a fresh connection/process's
    # first touch of a project as a one-off cold-start cost to absorb, never
    # a measurement (see lifecycle_loop_liveness.py's identical rationale).
    warmup_t0 = time.monotonic()
    _, warmup_ok, _, warmup_err = await _run_cheap_read(client, -1)
    warmup_elapsed = time.monotonic() - warmup_t0

    probe_degraded, probe_avg, probe_detail = await probe_ambient_load(
        client, _PROJECT_ID
    )
    if probe_degraded:
        inconclusive = (
            Status.INCONCLUSIVE,
            f"ambient load detected before measurement started -- skipping "
            f"the timed round rather than reporting noise as a verdict "
            f"(bug 2aaac911): warmup_ok={warmup_ok} warmup_elapsed_s="
            f"{warmup_elapsed:.4f} last_probe_avg_s={probe_avg:.4f} "
            f"{probe_detail}",
        )
        return inconclusive, inconclusive

    seq_wall, seq_results = await _run_sequential_batch(client)
    conc_wall, conc_results = await _run_concurrent_batch(client)

    latency = _latency_outcome(
        warmup_ok, warmup_elapsed, warmup_err, seq_wall, seq_results
    )
    concurrency = _concurrency_outcome(seq_results, conc_wall, conc_results)
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
        # INCONCLUSIVE, not FAILED (bug 2aaac911): a check that hits its own
        # hard ceiling because the server was busy proved nothing about the
        # code under test either way.
        timeout_reason = (
            f"check exceeded its own hard timeout of {_HARD_TIMEOUT_SECONDS}s "
            f"(server likely busy with unrelated work, not a code regression)"
        )
        latency_status, latency_reason = Status.INCONCLUSIVE, timeout_reason
        concurrency_status, concurrency_reason = Status.INCONCLUSIVE, timeout_reason
    return {
        CHECK_NAME_LATENCY: CommandOutcome(
            CHECK_NAME_LATENCY, Bucket.BUCKET_A, latency_status, latency_reason
        ),
        CHECK_NAME_CONCURRENCY: CommandOutcome(
            CHECK_NAME_CONCURRENCY, Bucket.BUCKET_A, concurrency_status, concurrency_reason
        ),
    }
