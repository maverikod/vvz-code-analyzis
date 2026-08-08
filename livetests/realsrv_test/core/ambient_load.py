"""
Shared ambient-load pre-measurement probe (bug 2aaac911).

Root cause under test: the live pipeline's verdict for a timing-sensitive
check (``lifecycle_read_throughput.py``'s latency and concurrency metrics)
used to depend on whatever ELSE happened to be running against the server in
the same sweep. Confirmed on the real deployed server: the 1.6.92 sweep
reported both throughput metrics FAILED with ``check exceeded its own hard
timeout of 120.0s`` (twice) while standalone runs of the exact same check
were clean; the 1.6.93 sweep reported ``read_latency_per_call_regression``
FAILED at 0.646s/call vs its 0.600s ceiling while two standalone runs of the
same check gave 0.009-0.010s/call -- a ~65x discrepancy caused purely by
``lifecycle_loop_liveness.py``'s K=32 storm against the same shared heavy
project running immediately before it in the same sweep, not a code
regression.

This module gives any timing-sensitive check a small, bounded way to notice
that condition BEFORE it spends its measurement budget on numbers nobody
should trust: run a few cheap SEQUENTIAL calls (no concurrency of our own
mixed in) against the same project the real measurement is about to use, and
compare the average against a documented "known idle" ceiling. Sequential
by design -- it must answer "is the server externally busy right now",
never "does concurrency scale on this server", which is the separate,
already-tracked, and deliberately still-open question bug 8e6acb34 owns
(``lifecycle_read_throughput.py``'s ``read_concurrency_speedup_8e6acb34``
metric measures that on purpose and is NOT gated by this probe).

Two entry points:

- :func:`probe_once` -- a single, deterministic probe round. No retry, no
  sleep. Used where the caller needs a snapshot taken at an exact moment
  (e.g. while a self-generated concurrent batch is deliberately in flight --
  see ``lifecycle_measurement_stability.py``, which would have its own
  probe's retry loop simply wait for its OWN background load to finish and
  silently self-clear if it used the retrying wrapper below instead).
- :func:`probe_ambient_load` -- the bounded-retry wrapper a real timing check
  calls before it measures anything. Ambient load from a neighbouring suite
  is often transient (e.g. right after a load-generator suite's storm
  finishes), so this gives it one short, FIXED chance to clear before the
  caller gives up and reports :attr:`Status.INCONCLUSIVE` -- never an
  unbounded wait.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

# Known-idle per-call baseline for a cheap page_size=1 ``list_project_files``
# call against the enumeration cache (bug 8e6acb34's body-cost fix, shipped
# 1.6.93): measured standalone at 0.009-0.010s/call
# (lifecycle_read_throughput.py module docstring) and 0.0072s/call as the
# quiet baseline in the original measurement-stability reproduction
# (verbatim RED on deployed 1.6.93). ~0.010s is the practical ceiling of
# "genuinely idle" for this call shape.
_KNOWN_IDLE_CEILING_SECONDS = 0.010

# Ambient-load probe ceiling: how far a SEQUENTIAL (self-uncontended)
# per-call average may drift above known-idle before this probe concludes
# the server is currently busy with work the caller does not control.
#
# ~3x known-idle (0.03s) is chosen to sit:
#   - comfortably ABOVE ordinary per-call jitter on a healthy server: the two
#     independent standalone measurements cited above landed within 0.001s
#     of each other -- no observed jitter anywhere near 0.03s on a quiet
#     server;
#   - comfortably BELOW the confirmed corruption/interference cases this bug
#     is about: 0.0469s/call average measured inside an 8-way
#     SELF-generated concurrent batch (the original measurement-stability
#     reproduction) and 0.646s/call measured inside the full sweep
#     immediately after lifecycle_loop_liveness.py's K=32 storm
#     (lifecycle_read_throughput.py module docstring) -- both cross this
#     ceiling with room to spare (~1.5x and ~21x respectively), so a probe
#     taken while either condition is in flight reliably reports degraded.
#
# RE-DERIVED 2026-08-08 (0.03 -> 0.02). The numbers above were taken on 1.6.93;
# the server has since got faster and the constant stopped sitting between the
# two states it must separate. Measured on deployed 1.6.99-1.6.101: quiet
# 0.0066-0.0075s/call, and the SAME 8-way self-generated batch that used to
# average 0.0469s/call now averages 0.0271-0.0292s/call -- under the old 0.03
# ceiling, so the probe stopped flagging interference it was built to catch and
# the self-check for this very bug went RED. 0.02 is ~3x today's measured idle
# and still ~1.5x below the loaded case.
#
# An absolute constant anchored to a remembered server speed will drift again
# every time the server gets faster. Prefer `baseline_seconds` below, which asks
# the question this probe actually means -- "is the server slower than it is
# when idle?" -- against a baseline measured in the same run. The constant
# remains the fallback for callers that have no baseline to offer.
_AMBIENT_LOAD_PROBE_CEILING_SECONDS = 0.02

# Multiple of a run's own measured idle baseline above which the server counts
# as busy, used when a caller supplies `baseline_seconds`.
#
# 2.0, not 3.0. Measured across six live runs on 1.6.101/1.6.102, the ratio
# between the quiet baseline and the SAME 8-way self-generated batch was:
#   0.0073 -> 0.0345 (4.7x)   0.0095 -> 0.0348 (3.7x)   0.0134 -> 0.0328 (2.4x)
#   0.0160 -> 0.0659 (4.1x)   0.0135 -> 0.0324 (2.4x)   0.0121 -> 0.0434 (3.6x)
# The spread is 2.4x-4.7x: a 3.0 threshold cuts straight through it, so the same
# real interference was flagged or missed depending on how noisy the quiet phase
# happened to be. 2.0 sits below the worst observed case with room to spare and
# still demands the server be twice its own idle cost before anything is called
# degraded.
_AMBIENT_LOAD_DEGRADED_RATIO = 2.0

# Floor for the derived ceiling: on a very fast server 3x idle can land within
# ordinary sub-millisecond jitter, which would report degraded constantly.
_AMBIENT_LOAD_MIN_DERIVED_CEILING_SECONDS = 0.015

# Small and cheap on purpose: the probe itself must not become a new source
# of the exact interference this bug is about. 3 sequential samples average
# out one-off scheduling noise without adding meaningful cost.
_PROBE_SAMPLES = 3

# Ambient load from a neighbouring suite is often transient. One bounded
# retry after a short, FIXED pause gives it a real chance to clear before a
# caller gives up and reports INCONCLUSIVE -- never an unbounded wait.
_PROBE_MAX_ATTEMPTS = 2
_PROBE_RETRY_DELAY_SECONDS = 2.0


async def probe_once(
    client: CodeAnalysisAsyncClient,
    project_id: str,
    *,
    page_size: int = 1,
    samples: int = _PROBE_SAMPLES,
    ceiling_seconds: float = _AMBIENT_LOAD_PROBE_CEILING_SECONDS,
    baseline_seconds: Optional[float] = None,
) -> Tuple[bool, float, int]:
    """Run one deterministic probe round: ``samples`` sequential cheap calls.

    No retry and no sleep -- callers that need a snapshot taken at an exact
    moment (e.g. while their own background load is deliberately in flight)
    use this directly instead of :func:`probe_ambient_load`.

    Args:
        client: Connected async client.
        project_id: Project to probe (any project_id exercises the same
            whole-project-lock gate as the real measurement the caller is
            about to take).
        page_size: Kept at 1 -- the cheap-response shape every caller uses.
        samples: Sequential calls this round.
        ceiling_seconds: Absolute degraded ceiling in seconds/call, used when
            no ``baseline_seconds`` is supplied.
        baseline_seconds: This run's own measured idle average. When given, the
            ceiling becomes ``_AMBIENT_LOAD_DEGRADED_RATIO`` times it (never
            below ``_AMBIENT_LOAD_MIN_DERIVED_CEILING_SECONDS``), so the verdict
            tracks how fast the server actually is today instead of how fast it
            was when the constant was written -- see the note on
            ``_AMBIENT_LOAD_PROBE_CEILING_SECONDS``.

    Returns:
        Tuple of (degraded, avg_elapsed_s, failures). ``degraded`` is True
        when any call failed or the average exceeded the effective ceiling.
    """
    if baseline_seconds is not None and baseline_seconds > 0:
        # A supplied baseline may only TIGHTEN the bar, never loosen it: a
        # "quiet" phase that measures slower than known-idle was not actually
        # quiet, and letting that inflate the ceiling would make the probe blind
        # exactly when the server is already contended. Observed live: a quiet
        # phase reading 0.0134s/call (vs the usual 0.0073-0.0095) pushed the
        # derived ceiling to 0.0403 and hid a loaded phase of 0.0328.
        effective_baseline = min(baseline_seconds, _KNOWN_IDLE_CEILING_SECONDS)
        ceiling_seconds = max(
            _AMBIENT_LOAD_DEGRADED_RATIO * effective_baseline,
            _AMBIENT_LOAD_MIN_DERIVED_CEILING_SECONDS,
        )
    params: Dict[str, Any] = {"project_id": project_id, "page_size": page_size}
    failures = 0
    elapsed_total = 0.0
    for _ in range(samples):
        t0 = time.monotonic()
        try:
            resp = await client.call_validated("list_project_files", params)
            if not resp.get("success"):
                failures += 1
        except Exception:  # noqa: BLE001 - recorded as data, not raised
            failures += 1
        elapsed_total += time.monotonic() - t0
    avg = elapsed_total / samples if samples else 0.0
    degraded = failures > 0 or avg > ceiling_seconds
    return degraded, avg, failures


async def probe_ambient_load(
    client: CodeAnalysisAsyncClient,
    project_id: str,
    *,
    page_size: int = 1,
    samples: int = _PROBE_SAMPLES,
    max_attempts: int = _PROBE_MAX_ATTEMPTS,
    retry_delay_seconds: float = _PROBE_RETRY_DELAY_SECONDS,
    ceiling_seconds: float = _AMBIENT_LOAD_PROBE_CEILING_SECONDS,
) -> Tuple[bool, float, str]:
    """Bounded pre-measurement probe: is the server already busy?

    Calls :func:`probe_once` up to ``max_attempts`` times, pausing
    ``retry_delay_seconds`` between attempts, so transient neighbouring load
    (e.g. the tail of a just-finished load-generator suite) gets one real,
    bounded chance to clear before the caller gives up on this round. Never
    waits unboundedly.

    Args:
        client: Connected async client.
        project_id: Project to probe.
        page_size: Kept at 1.
        samples: Sequential calls per attempt.
        max_attempts: Total probe attempts before giving up.
        retry_delay_seconds: Pause between attempts.
        ceiling_seconds: Degraded-baseline ceiling in seconds/call.

    Returns:
        Tuple of (degraded, last_avg_elapsed_s, detail) where ``degraded`` is
        True only if EVERY attempt stayed degraded, and ``detail`` names
        every attempt's numbers for the caller's outcome reason.
    """
    attempts: List[str] = []
    degraded = True
    last_avg = 0.0
    for attempt in range(1, max_attempts + 1):
        degraded, last_avg, failures = await probe_once(
            client,
            project_id,
            page_size=page_size,
            samples=samples,
            ceiling_seconds=ceiling_seconds,
        )
        attempts.append(
            f"attempt{attempt}_avg_s={last_avg:.4f}(failures={failures})"
        )
        if not degraded:
            break
        if attempt < max_attempts:
            await asyncio.sleep(retry_delay_seconds)
    detail = (
        f"ambient_probe: samples={samples} ceiling_s={ceiling_seconds:.3f} "
        f"{'; '.join(attempts)}"
    )
    return degraded, last_avg, detail
