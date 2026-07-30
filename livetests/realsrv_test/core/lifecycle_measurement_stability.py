"""
Self-contained measurement-stability check (bug 2aaac911).

Registered in ``realsrv_test.suites.s15_measurement_stability`` (SUITE_NAME
"stability").

Root cause under test: the live pipeline's release gate reports numbers for a
timing/performance check as if that check ran in isolation, when in fact its
wall-clock is at the mercy of whatever ELSE is running concurrently against
the same server in the same sweep. Confirmed on the real deployed server (not
reproduced here from the bug report alone -- see the bug-fix-cycle evidence
already gathered for 2aaac911): ``lifecycle_read_throughput.py``'s
``read_latency_per_call_regression`` measured 0.646s/call inside the full
1.6.93 sweep (immediately after ``lifecycle_loop_liveness.py``'s K=32 storm
against the same shared heavy project) against 0.009-0.010s/call for the
identical check run standalone -- a ~65x discrepancy caused purely by
neighbouring load, not a code regression.

This check reproduces that same class of defect in a SELF-CONTAINED,
bounded, cheap way -- it does not depend on suite ordering or on another
suite's concurrent load, and it does NOT touch the large shared project
(``44a8ce88-b467-42a8-b874-033562b89bd0``) that ``lifecycle_loop_liveness.py``
/ ``lifecycle_read_throughput.py`` use, to avoid adding to exactly the kind of
cross-suite interference this bug is about. Instead it generates its OWN
small, bounded load against the pipeline's own disposable fixture project and
asks the same question in miniature: does a cheap, otherwise-trivial listing
call's latency stay within a bounded multiple of its quiet-server baseline
when a small amount of concurrent traffic to the SAME project is in flight?
Every project-scoped command (this one included) passes through the
whole-project-lock gate in ``BaseMCPCommand.run()`` before its body runs (see
``lifecycle_read_throughput.py`` and ``lifecycle_loop_liveness.py`` for the
mechanism), so concurrent siblings against the same project_id are expected
to contend that same gate -- exactly the kind of interference the bug's
release-gate verdicts are silently sensitive to.

Methodology: one warm-up call (excluded, absorbs cold-start skew, mirroring
every other lifecycle check in this package), then a QUIET baseline --
``_QUIET_SAMPLES`` sequential calls to a cheap, project-scoped listing
command with nothing else in flight -- followed by a LOADED measurement --
``_LOAD_CONCURRENCY`` concurrent calls of the exact same command fired at
once, whose individual elapsed times are averaged. The ratio
``loaded_avg_s / quiet_avg_s`` is the divergence factor; it must stay at or
below ``_MAX_DIVERGENCE_FACTOR`` (see that constant for the numeric
justification). This check intentionally reports :attr:`Status.FAILED`, not
:attr:`Status.INCONCLUSIVE`, when the divergence ceiling is breached: the
INCONCLUSIVE vocabulary (also introduced by bug 2aaac911) exists for a check
whose OWN measurement cannot be trusted because of load it does not control;
this check's divergence-under-its-own-controlled-load IS the thing under
test, so a ceiling breach here is this check's own real, reproducible
verdict, not an unmeasurable condition.

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

CHECK_NAME = "cheap_listing_latency_stable_under_self_load"

# Small and cheap on purpose -- this check must not itself become a source of
# the exact cross-check interference bug 2aaac911 is about. 3 quiet samples
# is enough to average out one-off scheduling noise without adding real cost;
# 8 concurrent siblings is enough to contend the per-project lock gate
# (mechanism confirmed in lifecycle_read_throughput.py /
# lifecycle_loop_liveness.py) without approaching the K=32 storm size that
# lifecycle_loop_liveness.py already uses deliberately as a heavy load.
_QUIET_SAMPLES = 3
_LOAD_CONCURRENCY = 8

# Divergence ceiling: loaded_avg_s / quiet_avg_s must not exceed this.
#
# Justification: a quiescence-safe measurement should show only mild
# self-interference from 8 concurrent siblings on the same tiny disposable
# project -- dispatch/network overhead, not queueing behind a shared lock.
# The real evidence already gathered for this bug shows the actual defect is
# nowhere near this boundary: 0.646s vs 0.010s baseline is a ~65x
# discrepancy. 3.0x is chosen to sit far below that -- comfortably outside
# the range ordinary shared-host jitter from just 8 bounded self-generated
# calls could plausibly produce -- while still being tight enough to catch
# the lock-gate serialization this check targets: if the K=8 siblings queue
# behind the same whole-project lock rather than overlapping, the AVERAGE
# per-call elapsed time among them approaches the batch wall-clock (every
# call's timer keeps running while it waits for the lock, so a serialized
# batch of K calls behind one gate yields an average wait alone of roughly
# (K-1)/2 call-times, i.e. ~3.5x the single-call baseline for K=8, before
# even adding each call's own execution time) -- comfortably above 3.0x.
# Too tight (e.g. 1.5x) would flap on ordinary scheduling noise between 3
# quiet samples and 8 concurrent ones; too loose (e.g. 10x+) would let the
# exact serialization defect back in silently.
_MAX_DIVERGENCE_FACTOR = 3.0

# Floor under the quiet-baseline denominator so a near-zero (sub-millisecond)
# quiet sample cannot make the divergence ratio blow up on measurement noise
# alone -- mirrors the intent of the regression ceiling in
# lifecycle_read_throughput.py, scaled down for this check's much cheaper
# call shape.
_MIN_QUIET_FLOOR_SECONDS = 0.005

# Runaway-detection bound, not a normal-completion bound: 1 warm-up + 3 quiet
# + 8 concurrent cheap page_size=1 calls against a 3-file disposable project
# should complete in well under a few seconds on a healthy server, even
# fully serialized. 60s gives generous headroom for a slow-but-healthy run
# to still complete and report a real verdict, while still catching a
# genuinely stuck check.
_HARD_TIMEOUT_SECONDS = 60.0


async def _run_cheap_listing(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext, index: int
) -> Tuple[int, bool, float, str]:
    """Run one cheap project-scoped listing call and time it.

    Args:
        client: Connected async client.
        fixtures: The disposable project fixture for this run.
        index: Call index, used only for diagnostics.

    Returns:
        Tuple of (index, ok, elapsed_seconds, error_text_or_empty).
    """
    t0 = time.monotonic()
    try:
        resp = await client.call_validated(
            "list_project_files",
            {"project_id": fixtures.project_id, "page_size": 1},
        )
        ok = bool(resp.get("success"))
        err = "" if ok else truncate(str(resp.get("error")))
        return index, ok, time.monotonic() - t0, err
    except Exception as exc:  # noqa: BLE001 - recorded as data, not raised
        return index, False, time.monotonic() - t0, truncate(repr(exc))


async def _run_quiet_baseline(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> List[Tuple[int, bool, float, str]]:
    """Run ``_QUIET_SAMPLES`` calls strictly one at a time, nothing else in flight."""
    results: List[Tuple[int, bool, float, str]] = []
    for i in range(_QUIET_SAMPLES):
        results.append(await _run_cheap_listing(client, fixtures, i))
    return results


async def _run_loaded_batch(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> List[Tuple[int, bool, float, str]]:
    """Fire ``_LOAD_CONCURRENCY`` calls of the same command concurrently."""
    tasks = [
        asyncio.create_task(_run_cheap_listing(client, fixtures, i))
        for i in range(_LOAD_CONCURRENCY)
    ]
    return list(await asyncio.gather(*tasks))


def _classify(
    project_id: str,
    warmup_ok: bool,
    warmup_elapsed: float,
    warmup_err: str,
    quiet_results: List[Tuple[int, bool, float, str]],
    loaded_results: List[Tuple[int, bool, float, str]],
) -> Tuple[Status, str]:
    """Classify the divergence between the quiet baseline and the self-loaded batch."""
    quiet_failures = [r for r in quiet_results if not r[1]]
    loaded_failures = [r for r in loaded_results if not r[1]]

    quiet_avg = (
        sum(r[2] for r in quiet_results) / len(quiet_results) if quiet_results else 0.0
    )
    loaded_avg = (
        sum(r[2] for r in loaded_results) / len(loaded_results)
        if loaded_results
        else 0.0
    )
    quiet_denominator = max(quiet_avg, _MIN_QUIET_FLOOR_SECONDS)
    divergence = loaded_avg / quiet_denominator

    reason = (
        f"warmup_ok={warmup_ok} warmup_elapsed_s={warmup_elapsed:.4f}"
        f"{'' if warmup_ok else f' warmup_error={warmup_err!r}'}; "
        f"cheap_read=list_project_files(project={project_id}, page_size=1); "
        f"quiet_samples={_QUIET_SAMPLES} quiet_avg_s={quiet_avg:.4f} "
        f"(failures={len(quiet_failures)}); "
        f"loaded_concurrency={_LOAD_CONCURRENCY} loaded_avg_s={loaded_avg:.4f} "
        f"(failures={len(loaded_failures)}); "
        f"divergence={divergence:.2f}x; ceiling={_MAX_DIVERGENCE_FACTOR:.1f}x"
    )
    if quiet_failures or loaded_failures:
        return (
            Status.FAILED,
            f"one or more cheap listing calls failed: {reason}",
        )
    if divergence > _MAX_DIVERGENCE_FACTOR:
        return (
            Status.FAILED,
            f"cheap listing latency diverged beyond its stability ceiling "
            f"under self-generated concurrent load (bug 2aaac911): {reason}",
        )
    return (
        Status.EXECUTED_OK,
        f"cheap listing latency stayed within its stability ceiling under "
        f"self-generated concurrent load: {reason}",
    )


async def _run_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Tuple[Status, str]:
    """Run the bounded quiet-vs-self-loaded measurement once and classify it.

    Args:
        client: Connected async client.
        fixtures: The disposable project fixture for this run.

    Returns:
        (status, reason); reason always includes the measured timings.
    """
    warmup_t0 = time.monotonic()
    _, warmup_ok, _, warmup_err = await _run_cheap_listing(client, fixtures, -1)
    warmup_elapsed = time.monotonic() - warmup_t0

    quiet_results = await _run_quiet_baseline(client, fixtures)
    loaded_results = await _run_loaded_batch(client, fixtures)

    return _classify(
        fixtures.project_id,
        warmup_ok,
        warmup_elapsed,
        warmup_err,
        quiet_results,
        loaded_results,
    )


async def run_measurement_stability_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bounded single-round check: is a cheap listing call's latency stable under self-load?

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run --
            deliberately used here (unlike ``lifecycle_loop_liveness.py`` /
            ``lifecycle_read_throughput.py``, which target a large
            pre-existing project) to keep this check's own footprint bounded
            and cheap (see module docstring).

    Returns:
        ``{CHECK_NAME: outcome}`` -- single-entry map, like every check in
        this package.
    """
    try:
        status, reason = await asyncio.wait_for(
            _run_check(client, fixtures), timeout=_HARD_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        status, reason = (
            Status.FAILED,
            f"check exceeded its own hard timeout of {_HARD_TIMEOUT_SECONDS}s",
        )
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}
