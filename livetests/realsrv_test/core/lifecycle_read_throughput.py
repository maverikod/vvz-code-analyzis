"""
Concurrent read throughput check for project-scoped read commands (bug 8e6acb34).

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
basenames. A command body with ~0.8s of GIL-bound CPU work serializes
concurrent calls almost as badly as an unbounded lock would, regardless of
page_size -- this check exercises the REAL end-to-end command path (network +
offload-worker GIL contention together), not the lock gate in isolation, so it
remains a valid regression guard for either bottleneck reappearing.

Methodology: fire ``_N`` concurrent calls and time the batch wall-clock, then
run the SAME ``_N`` calls strictly sequentially (one at a time, awaited in
turn) and time that too. If either bottleneck reappears (lock-gate
serialization, or the command body itself burning GIL-bound CPU on every
call), concurrent wall-clock will be roughly equal to (or, accounting for
offload-pool scheduling overhead, not much better than -- see this check's own
history of measuring speedups below 1.0x) sequential wall-clock. With both
fixed, concurrent calls should overlap substantially and the speedup should be
large. This check asserts speedup >= ``_MIN_SPEEDUP_FACTOR`` (unchanged by
this correction: threshold stays 4.0x -- only the diagnosis above is
corrected, not the bar a fix must clear).

One warm-up call runs first (excluded from both measurements) to absorb
cold-start skew, mirroring ``lifecycle_loop_liveness.py``.

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

CHECK_NAME = "read_throughput_lock_gate_select_pool"

# Same real, sizeable pre-existing project as suite "loop" (s09) -- read-only
# commands only, no mutation. A tiny disposable fixture project would still
# exercise the lock gate (any project_id does), but reusing the same known
# project keeps this check independent of fixture project size/state.
_PROJECT_ID = "44a8ce88-b467-42a8-b874-033562b89bd0"

_N = 16
_MIN_SPEEDUP_FACTOR = 4.0
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


async def _run_check(client: CodeAnalysisAsyncClient) -> Tuple[Status, str]:
    """Run the bounded sequential-vs-concurrent throughput comparison once.

    Args:
        client: Connected async client.

    Returns:
        (status, reason); reason always includes the measured timings.
    """
    warmup_t0 = time.monotonic()
    _, warmup_ok, _, warmup_err = await _run_cheap_read(client, -1)
    warmup_elapsed = time.monotonic() - warmup_t0

    seq_wall, seq_results = await _run_sequential_batch(client)
    conc_wall, conc_results = await _run_concurrent_batch(client)

    seq_failures = [r for r in seq_results if not r[1]]
    conc_failures = [r for r in conc_results if not r[1]]
    speedup = (seq_wall / conc_wall) if conc_wall > 0 else float("inf")

    reason = (
        f"warmup_ok={warmup_ok} warmup_elapsed_s={warmup_elapsed:.3f}"
        f"{'' if warmup_ok else f' warmup_error={warmup_err!r}'}; "
        f"N={_N} cheap_read=list_project_files(project={_PROJECT_ID}, page_size=1); "
        f"sequential_wall_s={seq_wall:.3f} (failures={len(seq_failures)}); "
        f"concurrent_wall_s={conc_wall:.3f} (failures={len(conc_failures)}); "
        f"speedup={speedup:.2f}x; min_required={_MIN_SPEEDUP_FACTOR:.1f}x"
    )

    if seq_failures or conc_failures:
        return Status.FAILED, f"one or more cheap read calls failed: {reason}"
    if speedup < _MIN_SPEEDUP_FACTOR:
        return (
            Status.FAILED,
            f"concurrent reads did not speed up over sequential (process-wide "
            f"read serialization, bug 8e6acb34): {reason}",
        )
    return (
        Status.EXECUTED_OK,
        f"concurrent reads sped up over sequential as expected: {reason}",
    )


async def run_read_throughput_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bounded single-round check: do concurrent lock-gated reads outrun sequential ones?

    Args:
        client: Connected async client.
        fixtures: Unused -- this check deliberately targets a real,
            pre-existing project (see module docstring), like suite "loop".

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
