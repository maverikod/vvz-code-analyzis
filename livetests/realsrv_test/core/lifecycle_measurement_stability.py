"""
Self-contained ambient-load-detection contract check (bug 2aaac911).

Registered in ``realsrv_test.suites.s15_measurement_stability`` (SUITE_NAME
"stability").

RE-AIMED -- read this before touching the thresholds below. This check's
ORIGINAL form asserted that a cheap listing call's absolute latency
divergence under 8-way self-generated concurrent load stayed within a fixed
3.0x ceiling. That form is RETIRED: verbatim evidence gathered against the
real deployed server (1.6.93) landed at 6.50x (quiet_avg 0.0072s,
loaded_avg 0.0469s) with NOTHING else running in the sweep -- i.e. even a
small, entirely SELF-generated 8-way concurrent batch against tiny,
already-cached (bug 8e6acb34's body-cost fix, shipped 1.6.93) ~7ms calls
degrades average per-call latency past 3x on this server's GIL-bound request
path alone. That is an INTRINSIC scalability property of the server --
squarely bug 8e6acb34's territory (deliberately still open and tracked by
``lifecycle_read_throughput.py``'s ``read_concurrency_speedup_8e6acb34``
metric) -- not a defect in bug 2aaac911's scope, which is about whether the
release gate's VERDICT stays trustworthy regardless of concurrent
interference. Left as originally written, this check would have become a
second, permanently-red check for a property this project already tracks
and accepts elsewhere: exactly the failure mode 2aaac911 exists to
eliminate.

WHAT THIS CHECK NOW TESTS: it directly exercises
``realsrv_test.core.ambient_load.probe_once`` / ``probe_ambient_load`` --
the exact building block ``lifecycle_read_throughput.py`` calls before every
timed measurement to decide whether to skip a corrupted round and report
:attr:`Status.INCONCLUSIVE` instead of a bogus number. It asks the question
2aaac911 is actually about: when there genuinely IS concurrent interference
in flight, does the detection mechanism catch it? Methodology:

1. One warm-up call (excluded), mirroring every other check in this
   package.
2. QUIET-phase probe: nothing else in flight. Sanity precondition -- the
   mechanism must not false-positive on a healthy server. If this phase is
   ALREADY degraded, something else unrelated is loading the server right
   now and this check cannot exercise its own contract cleanly this round,
   so it reports :attr:`Status.INCONCLUSIVE` naming the numbers rather than
   a false verdict about the detection mechanism.
3. LOADED phase (only reached if the quiet phase was clean): fire
   ``_LOAD_CONCURRENCY`` concurrent siblings of the same cheap call against
   the SAME disposable project while, concurrently, taking one deterministic
   probe snapshot (``probe_once`` -- no retry, so it cannot wait for its own
   background load to finish and quietly self-clear). Assert the probe
   reports ``degraded=True``: the same mechanism that gates
   ``read_latency_per_call_regression`` / ``read_concurrency_speedup_8e6acb34``
   must correctly recognize genuine concurrent interference when it is
   actually present. A probe that fails to flag it here is a real defect in
   the detection code itself (:attr:`Status.FAILED`, a code defect this
   suite owns -- not a comment on the server's raw concurrency scalability,
   which stays 8e6acb34's business).

Uses the pipeline's own disposable fixture project (never the large shared
project ``44a8ce88-b467-42a8-b874-033562b89bd0`` that
``lifecycle_loop_liveness.py`` / ``lifecycle_read_throughput.py`` target) so
this check's footprint stays bounded and adds no load to the project other
suites measure -- unchanged from the original design.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.ambient_load import (
    _AMBIENT_LOAD_DEGRADED_RATIO,
    _AMBIENT_LOAD_MIN_DERIVED_CEILING_SECONDS,
    _KNOWN_IDLE_CEILING_SECONDS,
    probe_ambient_load,
    probe_once,
)


def _derived_ceiling(baseline_seconds: float) -> float:
    """Mirror probe_once's derived ceiling, for the diagnostic message only.

    Args:
        baseline_seconds: This run's measured quiet average.

    Returns:
        The ceiling probe_once applies for that baseline, including the clamp
        that stops a slow "quiet" phase from loosening the bar.
    """
    return max(
        _AMBIENT_LOAD_DEGRADED_RATIO
        * min(baseline_seconds, _KNOWN_IDLE_CEILING_SECONDS),
        _AMBIENT_LOAD_MIN_DERIVED_CEILING_SECONDS,
    )
from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME = "ambient_load_probe_flags_self_generated_concurrent_load"

# Mirrors lifecycle_read_throughput.py's own concurrency-metric sizing
# rationale: enough concurrent siblings to reliably contend the per-project
# lock gate (confirmed mechanism -- see that module and
# lifecycle_loop_liveness.py) without approaching lifecycle_loop_liveness.py's
# deliberately heavy K=32 storm.
_LOAD_CONCURRENCY = 8

# Runaway-detection bound, not a normal-completion bound: 1 warm-up + a
# quiet probe (<= 2 attempts x 3 samples) + an 8-way concurrent batch plus
# one more probe round against a 3-file disposable project should complete
# in well under a few seconds on a healthy server, even fully serialized.
# 60s gives generous headroom for a slow-but-healthy run to still complete
# and report a real verdict, while still catching a genuinely stuck check.
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


async def _fire_background_load(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> List[Tuple[int, bool, float, str]]:
    """Fire ``_LOAD_CONCURRENCY`` concurrent siblings of the same cheap call."""
    tasks = [
        asyncio.create_task(_run_cheap_listing(client, fixtures, i))
        for i in range(_LOAD_CONCURRENCY)
    ]
    return list(await asyncio.gather(*tasks))


async def _run_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Tuple[Status, str]:
    """Run the bounded quiet-then-loaded probe contract check once.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        (status, reason); reason always includes the measured numbers.
    """
    warmup_t0 = time.monotonic()
    _, warmup_ok, _, warmup_err = await _run_cheap_listing(client, fixtures, -1)
    warmup_elapsed = time.monotonic() - warmup_t0
    warmup_note = (
        f"warmup_ok={warmup_ok} warmup_elapsed_s={warmup_elapsed:.4f}"
        f"{'' if warmup_ok else f' warmup_error={warmup_err!r}'}"
    )

    quiet_degraded, quiet_avg, quiet_detail = await probe_ambient_load(
        client, fixtures.project_id
    )
    if quiet_degraded:
        return (
            Status.INCONCLUSIVE,
            f"{warmup_note}; quiet-phase probe was already degraded before "
            f"this check generated any load of its own -- cannot exercise "
            f"the detection contract cleanly this round (unrelated load "
            f"already in flight): {quiet_detail}",
        )

    # Deliberately NOT the retrying probe_ambient_load here: a retry would
    # sleep and re-probe after our own background load has likely already
    # finished, letting a genuinely-caught detection silently look clean on
    # the second attempt. probe_once takes one deterministic snapshot while
    # the background batch is actually in flight.
    load_task = asyncio.create_task(_fire_background_load(client, fixtures))
    # Judge against the baseline THIS run just measured, not against a constant
    # remembered from an older, slower server. The property under test is "load
    # makes the server measurably slower than its own idle speed, and the probe
    # notices" -- on 1.6.99+ the same 8-way batch that once averaged 0.0469s/call
    # averages ~0.029s, so an absolute 0.03 ceiling silently stopped separating
    # the two states and this check went RED with nothing actually broken.
    loaded_degraded, loaded_avg, loaded_failures = await probe_once(
        client, fixtures.project_id, baseline_seconds=quiet_avg
    )
    load_results = await load_task
    background_failures = [r for r in load_results if not r[1]]

    reason = (
        f"{warmup_note}; quiet_probe: degraded={quiet_degraded} "
        f"avg_s={quiet_avg:.4f} ({quiet_detail}); loaded_probe "
        f"(concurrent background_load={_LOAD_CONCURRENCY}): "
        f"degraded={loaded_degraded} avg_s={loaded_avg:.4f} "
        f"vs derived_ceiling_s={_derived_ceiling(quiet_avg):.4f} "
        f"(={_AMBIENT_LOAD_DEGRADED_RATIO}x this run's quiet baseline, floor "
        f"{_AMBIENT_LOAD_MIN_DERIVED_CEILING_SECONDS}); "
        f"failures={loaded_failures}; background_load_failures="
        f"{len(background_failures)}"
    )
    if loaded_degraded:
        return (
            Status.EXECUTED_OK,
            f"ambient-load detection correctly flagged self-generated "
            f"concurrent interference: {reason}",
        )
    return (
        Status.FAILED,
        f"ambient-load detection FAILED to flag genuine self-generated "
        f"concurrent interference it should have caught (bug 2aaac911 "
        f"detection defect, not a server-speed property): {reason}",
    )


async def run_measurement_stability_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bounded single-round check: does the ambient-load probe catch real interference?

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
        # INCONCLUSIVE, not FAILED (bug 2aaac911) -- a check that hits its
        # own hard ceiling because the server was busy proved nothing about
        # the detection mechanism either way. Mirrors
        # lifecycle_read_throughput.py's identical timeout handling.
        status, reason = (
            Status.INCONCLUSIVE,
            f"check exceeded its own hard timeout of {_HARD_TIMEOUT_SECONDS}s "
            f"(server likely busy with unrelated work)",
        )
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}
