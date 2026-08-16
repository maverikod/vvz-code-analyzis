"""
Shared machinery for the vectorization-worker livetest lifecycles (1.6.113
hardening pass, item C).

Both ``lifecycle_vectorization_batch_cap.py`` (suite ``vectorization_batch_cap``,
bug 16b1abbe) and ``lifecycle_vector_dim_parity.py`` (suite ``vectorparity``, bug
f4dd4039) need the same three things: an isolated disposable project to drive the
real vectorization worker against (instead of a shared fixture project or, for the
old ``vectorparity`` check, a hardcoded fixed project id), a small fixture Python
module with a configurable number of documented functions (one ``code_chunks`` row
per function via the docstring chunker -- see
``core/docstring_chunker_pkg/docstring_chunker.py``), and a bounded
``check_vectors`` poll for full vectorization. This module factors that machinery
out of the batch-cap lifecycle (its original home before this pass) so both
lifecycles share one implementation instead of drifting apart.

Also centralizes the worker start/stop hardening added in this same pass:
verify the vectorization worker is actually alive (bounded retries) before
starting the poll window, and only ``stop_worker`` in teardown when THIS call's
``start_worker`` actually spawned a fresh worker process -- a concurrent suite's
already-running worker must survive our teardown, not get stopped out from under
it (``start_worker`` on an already-running vectorization worker succeeds at the
transport level but reports ``success: False`` / a "already running" message in
its data, which is the only signal that distinguishes the two cases -- see
``code_analysis/core/worker_lifecycle.py``'s ``start_vectorization_worker``).

1.6.114 gate hardening (restart race, see ``start_and_verify_vectorization_
worker``): right after a service restart, the boot vectorization worker
(``main_workers.py``'s ``startup_vectorization_worker``) takes a few seconds
to register its PID file. If this module's own ``start_worker`` call raced
ahead of it, it could win that race and become the fleet's ONLY vectorization
worker -- the real boot worker then sees an "already running" PID file it did
not itself write and backs off, so when THIS call's teardown correctly stops
"its own" worker (``started_fresh`` was True), the fleet is left with no
vectorization worker at all. ``start_and_verify_vectorization_worker`` now
waits briefly for an already-running (or about-to-register) worker before
attempting its own start, so the legitimate boot worker wins that race
instead.

Also adds the two extra signals ``lifecycle_vectorization_batch_cap.py``
needs to assert the 16b1abbe fix without depending on fleet-wide ANN
throughput: ``poll_check_vectors_fully_embedded`` (embedding-complete
predicate, STEP 1 only) and ``scan_vectorization_log_for_cap_errors``
(confirms the embed service's per-request cap was never actually hit during
the run). See both functions' docstrings for why.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Status, truncate
from realsrv_test.core.disposable_project import purge_disposable_project
from realsrv_test.core.lifecycle_common import call_step, call_step_with_data

logger = logging.getLogger(__name__)

# Bounded retries to confirm the vectorization worker process is actually alive
# (get_worker_status summary.is_running) before trusting the poll window that
# follows -- start_worker returning success does not guarantee the spawned
# process has registered itself yet (multiprocessing.Process.start() returns
# before the child finishes its own startup).
_WORKER_LIVENESS_RETRIES = 3
_WORKER_LIVENESS_RETRY_DELAY_SECONDS = 2.0

# Bounded wait for an already-running (or about-to-register) boot vectorization
# worker before racing to start a fresh one ourselves -- see the module
# docstring's "restart race" paragraph. In steady state (no recent restart)
# this resolves on the very first poll, since the boot worker has already
# been running for a while; it only actually waits in the narrow post-restart
# window.
_BOOT_WORKER_WAIT_TIMEOUT_SECONDS = 30.0
_BOOT_WORKER_WAIT_INTERVAL_SECONDS = 3.0


def generate_fixture_source(total_functions: int) -> str:
    """Build a ``.py`` module with ``total_functions`` documented functions.

    Each function gets its own one-line docstring so the docstring chunker
    persists one ``code_chunks`` row per function -- ``total_functions``
    un-vectorized chunks for a single file.

    Args:
        total_functions: Number of top-level documented functions to emit.

    Returns:
        Full Python module source text.
    """
    lines = [
        '"""Fixture module for a vectorization-worker livetest lifecycle.',
        "",
        f"Has {total_functions} documented functions so the docstring chunker",
        "persists that many un-vectorized chunks for this one file.",
        '"""',
        "",
        "",
    ]
    for i in range(total_functions):
        lines.append(f"def vectorization_fixture_fn_{i}() -> int:")
        lines.append(f'    """Return a fixed value; function #{i} of the fixture set."""')
        lines.append(f"    return {i}")
        lines.append("")
        lines.append("")
    return "\n".join(lines)


async def create_isolated_vectorization_project(
    client: CodeAnalysisAsyncClient,
    *,
    name_prefix: str,
    description: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Status, str]:
    """Create the isolated throwaway project a vectorization livetest lifecycle
    runs against, mirroring
    ``realsrv_test.core.lifecycle_indexer_correctness.
    run_update_indexes_usages_idempotent``'s isolated-project pattern.

    Args:
        client: Connected async client.
        name_prefix: Project-name prefix (a random 8-hex suffix is appended so
            concurrent runs never collide).
        description: ``create_project`` description text.

    Returns:
        ``(project_id, project_root, project_name, status, reason)``.
        ``status`` is :attr:`Status.EXECUTED_OK` with ``project_id``/
        ``project_root``/``project_name`` set on success; otherwise all
        three are ``None`` and ``reason`` explains the failure.
        ``project_name`` is returned alongside the id so callers can pass
        both straight to
        :func:`~realsrv_test.core.disposable_project.purge_disposable_project`
        (via :func:`teardown_vectorization_project`) in teardown, without
        each lifecycle reconstructing the name from ``name_prefix`` itself.
    """
    watch_dir_status, watch_dir_data = await call_step_with_data(
        client, "list_watch_dirs", {}, ok_reason="watch directories listed"
    )
    watch_dirs = (watch_dir_data or {}).get("watch_dirs") or []
    if watch_dir_status.status is not Status.EXECUTED_OK or not watch_dirs:
        return (
            None,
            None,
            None,
            Status.FAILED,
            f"could not list a watch_dir for the isolated project ({watch_dir_status.reason})",
        )
    watch_dir_id = str(watch_dirs[0]["id"])

    suffix = uuid.uuid4().hex[:8]
    project_name = f"{name_prefix}_{suffix}"
    create_status, create_data = await call_step_with_data(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": project_name,
            "description": description,
            "create_venv": False,
            "apply_template": False,
        },
        ok_reason="isolated throwaway project created",
    )
    if create_status.status is not Status.EXECUTED_OK:
        return (
            None,
            None,
            None,
            Status.FAILED,
            f"could not create the isolated project ({create_status.reason})",
        )
    project_id = str((create_data or {}).get("project_id") or "")
    project_root = str((create_data or {}).get("project_root") or "")
    if not project_id or not project_root:
        return (
            None,
            None,
            None,
            Status.FAILED,
            f"create_project response missing project_id/project_root: {create_data!r}",
        )
    return project_id, project_root, project_name, Status.EXECUTED_OK, "isolated project ready"


async def teardown_vectorization_project(
    client: CodeAnalysisAsyncClient, project_id: str, project_name: Optional[str]
) -> str:
    """Purge an isolated vectorization livetest project (bug d5835fbf).

    Thin wrapper around
    :func:`~realsrv_test.core.disposable_project.purge_disposable_project` so
    the three vectorization lifecycles (batch-cap, worker-activity,
    dim-parity) share one teardown path instead of each hand-rolling a bare
    ``project_set_mark_del(delete_from_disk=True)`` call with no follow-up
    trash purge -- the old per-lifecycle version left every one of these
    isolated projects sitting in trash forever (12 leaked entries observed
    across the three suites before this fix).

    Args:
        client: Connected async client.
        project_id: Isolated project to purge.
        project_name: The project's name, if known (fallback matcher only;
            see ``purge_disposable_project``'s docstring).

    Returns:
        The short outcome string from ``purge_disposable_project`` -- never
        raises.
    """
    return await purge_disposable_project(client, project_id, project_name)


async def upload_fixture_file(
    client: CodeAnalysisAsyncClient,
    *,
    project_id: str,
    relative_path: str,
    total_functions: int,
    session_comment: str,
) -> Tuple[Optional[str], Status, str]:
    """Open a session and upload the generated fixture file into ``project_id``.

    Args:
        client: Connected async client.
        project_id: Isolated project to upload into.
        relative_path: Destination path inside the project.
        total_functions: Passed through to :func:`generate_fixture_source`.
        session_comment: Comment for the ``session_create`` call.

    Returns:
        ``(file_id, status, reason)``. ``file_id`` is ``None`` on failure.
    """
    session_status, session_data = await call_step_with_data(
        client,
        "session_create",
        {"comment": session_comment},
        ok_reason="session created for the isolated project",
    )
    if session_status.status is not Status.EXECUTED_OK:
        return None, Status.FAILED, f"could not open a session ({session_status.reason})"
    session_id = str((session_data or {}).get("session_id") or "")
    if not session_id:
        return (
            None,
            Status.FAILED,
            f"session_create response missing session_id: {session_data!r}",
        )

    content = generate_fixture_source(total_functions).encode("utf-8")
    try:
        file_id = await client.file_sessions.upload_new(
            session_id, content, project_id, relative_path
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return None, Status.FAILED, truncate(f"fixture file upload failed: {exc!r}")
    if not file_id:
        return None, Status.FAILED, "fixture upload returned no file_id"
    return str(file_id), Status.EXECUTED_OK, "fixture file uploaded"


async def poll_check_vectors_fully_vectorized(
    client: CodeAnalysisAsyncClient,
    project_id: str,
    *,
    timeout_seconds: float,
    interval_seconds: float = 5.0,
) -> Tuple[Status, str, Optional[Dict[str, Any]]]:
    """Poll ``check_vectors`` until fully vectorized or the bounded timeout expires.

    Args:
        client: Connected async client.
        project_id: Project to poll.
        timeout_seconds: Bounded poll window.
        interval_seconds: Delay between polls.

    Returns:
        Tuple of (status, reason, last ``check_vectors`` data dict or None).
        ``status`` is :attr:`Status.EXECUTED_OK` only if, before the deadline,
        a poll observed ``chunks_pending_vectorization == 0`` and
        ``chunks_with_model == total_chunks`` with ``total_chunks > 0``.
    """
    deadline = time.monotonic() + timeout_seconds
    last_data: Optional[Dict[str, Any]] = None
    last_reason = "check_vectors was never called"
    while time.monotonic() < deadline:
        outcome, data = await call_step_with_data(
            client,
            "check_vectors",
            {"project_id": project_id},
            ok_reason="check_vectors executed",
        )
        if outcome.status is not Status.EXECUTED_OK:
            last_reason = f"check_vectors call failed: {outcome.reason}"
        else:
            last_data = data or {}
            total = last_data.get("total_chunks")
            pending = last_data.get("chunks_pending_vectorization")
            with_model = last_data.get("chunks_with_model")
            last_reason = (
                f"total_chunks={total} chunks_pending_vectorization={pending} "
                f"chunks_with_model={with_model}"
            )
            if (
                isinstance(total, int)
                and total > 0
                and pending == 0
                and with_model == total
            ):
                return Status.EXECUTED_OK, last_reason, last_data
        await asyncio.sleep(interval_seconds)
    return Status.FAILED, last_reason, last_data


async def poll_check_vectors_fully_embedded(
    client: CodeAnalysisAsyncClient,
    project_id: str,
    *,
    timeout_seconds: float,
    interval_seconds: float = 5.0,
) -> Tuple[Status, str, Optional[Dict[str, Any]]]:
    """Poll ``check_vectors`` until every chunk has an embedding MODEL recorded.

    Unlike :func:`poll_check_vectors_fully_vectorized`, this predicate does
    NOT require ``chunks_pending_vectorization == 0``. STEP 2 of
    vectorization (writing ``embedding_vec`` / the ANN index entry) is
    throttled by ``worker.batch_size`` PER PROJECT PER FLEET CYCLE (5 by
    default); once every project on the fleet is unpaused and draining a
    large shared backlog, one fleet cycle can take minutes, so a single
    project's ANN write-out can legitimately still show
    ``chunks_pending_vectorization > 0`` long after that project's chunks
    are all fully embedded (``chunks_pending_vectorization`` counts both
    "not yet embedded" and "embedded but ANN write still pending" chunks).
    Requiring ANN completion inside a check's fixed poll window therefore
    asserts fleet-wide ANN write throughput, not the bug 16b1abbe actually
    guards.

    This predicate asserts exactly the thing 16b1abbe's fix is about --
    STEP 1, the ``get_embeddings()`` call the batch-cap bug used to fail
    outright for any file with more un-vectorized chunks than the embed
    service's per-request cap -- and leaves ANN throughput out of scope. See
    :func:`scan_vectorization_log_for_cap_errors` for the other half of the
    16b1abbe regression signature (embedding completing by silently retrying
    past a cap rejection would still slip through this predicate alone).

    Args:
        client: Connected async client.
        project_id: Project to poll.
        timeout_seconds: Bounded poll window.
        interval_seconds: Delay between polls.

    Returns:
        Tuple of (status, reason, last ``check_vectors`` data dict or None).
        ``status`` is :attr:`Status.EXECUTED_OK` only if, before the
        deadline, a poll observed ``chunks_with_model == total_chunks`` with
        ``total_chunks > 0``.
    """
    deadline = time.monotonic() + timeout_seconds
    last_data: Optional[Dict[str, Any]] = None
    last_reason = "check_vectors was never called"
    while time.monotonic() < deadline:
        outcome, data = await call_step_with_data(
            client,
            "check_vectors",
            {"project_id": project_id},
            ok_reason="check_vectors executed",
        )
        if outcome.status is not Status.EXECUTED_OK:
            last_reason = f"check_vectors call failed: {outcome.reason}"
        else:
            last_data = data or {}
            total = last_data.get("total_chunks")
            with_model = last_data.get("chunks_with_model")
            with_vector = last_data.get("chunks_with_vector")
            pending = last_data.get("chunks_pending_vectorization")
            last_reason = (
                f"total_chunks={total} chunks_with_model={with_model} "
                f"chunks_with_vector={with_vector} "
                f"chunks_pending_vectorization={pending}"
            )
            if isinstance(total, int) and total > 0 and with_model == total:
                return Status.EXECUTED_OK, last_reason, last_data
        await asyncio.sleep(interval_seconds)
    return Status.FAILED, last_reason, last_data


async def _poll_worker_is_running(
    client: CodeAnalysisAsyncClient,
    worker_type: str,
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> Tuple[bool, str]:
    """Poll ``get_worker_status(worker_type)`` for up to ``timeout_seconds``.

    Always performs at least one check. Never raises: a failed
    ``get_worker_status`` call is treated as "not confirmed running yet" and
    retried like any other miss.

    Args:
        client: Connected async client.
        worker_type: ``worker_type`` to pass to ``get_worker_status``.
        timeout_seconds: Bounded wait window (``0`` performs exactly one
            check, no retries -- used for a single point-in-time read).
        interval_seconds: Delay between polls.

    Returns:
        ``(is_running, reason)``.
    """
    deadline = time.monotonic() + timeout_seconds
    last_reason = f"{worker_type} worker status never checked"
    while True:
        status_outcome, status_data = await call_step_with_data(
            client,
            "get_worker_status",
            {"worker_type": worker_type},
            ok_reason=f"{worker_type} worker status checked",
        )
        if status_outcome.status is Status.EXECUTED_OK:
            is_running = bool(
                ((status_data or {}).get("summary") or {}).get("is_running")
            )
            if is_running:
                return True, f"{worker_type} worker is running"
            last_reason = f"{worker_type} worker is not running"
        else:
            last_reason = (
                f"get_worker_status({worker_type}) call failed: "
                f"{status_outcome.reason}"
            )
        if time.monotonic() >= deadline:
            return False, last_reason
        await asyncio.sleep(interval_seconds)


async def start_and_verify_vectorization_worker(
    client: CodeAnalysisAsyncClient, project_id: str
) -> Tuple[Status, str, bool]:
    """Start the vectorization worker and confirm it is actually alive before the
    caller opens its poll window.

    Before attempting its own ``start_worker``, this first waits up to
    :data:`_BOOT_WORKER_WAIT_TIMEOUT_SECONDS` for an already-running (or
    about-to-register) vectorization worker -- see the module docstring's
    "restart race" paragraph for why: right after a service restart, racing
    ahead of the boot worker's own startup and winning would make THIS call's
    teardown stop the fleet's only vectorization worker. In steady state this
    wait resolves on its very first poll (the boot worker has already been up
    for a while), so it costs nothing outside the narrow post-restart window.

    Args:
        client: Connected async client.
        project_id: Project to pass to ``start_worker``.

    Returns:
        ``(status, reason, started_fresh)``. ``status`` is
        :attr:`Status.EXECUTED_OK` once liveness is confirmed (or the worker
        was already running -- either way there is a live worker to poll
        against). ``started_fresh`` is True only when THIS call's
        ``start_worker`` actually spawned a new process (i.e. neither the
        pre-start wait nor the start response itself found/reported an
        already-running worker) -- callers use this to decide whether their
        teardown should ``stop_worker``: stopping a worker a concurrent suite
        (or the fleet's boot worker) depends on would be its own regression.
    """
    already_running, wait_reason = await _poll_worker_is_running(
        client,
        "vectorization",
        timeout_seconds=_BOOT_WORKER_WAIT_TIMEOUT_SECONDS,
        interval_seconds=_BOOT_WORKER_WAIT_INTERVAL_SECONDS,
    )
    if already_running:
        return (
            Status.EXECUTED_OK,
            "vectorization worker already running before start_worker was "
            f"attempted; reused instead of racing a fresh start ({wait_reason})",
            False,
        )

    start_status, start_data = await call_step_with_data(
        client,
        "start_worker",
        {"worker_type": "vectorization", "project_id": project_id},
        ok_reason="vectorization worker start requested",
    )
    if start_status.status is not Status.EXECUTED_OK:
        return (
            Status.FAILED,
            f"start_worker(vectorization) did not succeed: {start_status.reason}",
            False,
        )
    message = str((start_data or {}).get("message") or "")
    started_fresh = "already running" not in message.lower()

    last_reason = message or "start_worker(vectorization) returned no message"
    for attempt in range(1, _WORKER_LIVENESS_RETRIES + 1):
        status_outcome, status_data = await call_step_with_data(
            client,
            "get_worker_status",
            {"worker_type": "vectorization"},
            ok_reason="vectorization worker status checked",
        )
        if status_outcome.status is Status.EXECUTED_OK:
            is_running = bool(
                ((status_data or {}).get("summary") or {}).get("is_running")
            )
            if is_running:
                return (
                    Status.EXECUTED_OK,
                    f"vectorization worker alive after start_worker ({message})",
                    started_fresh,
                )
            last_reason = (
                f"get_worker_status reports is_running=False (attempt {attempt}"
                f"/{_WORKER_LIVENESS_RETRIES})"
            )
        else:
            last_reason = (
                f"get_worker_status call failed (attempt {attempt}"
                f"/{_WORKER_LIVENESS_RETRIES}): {status_outcome.reason}"
            )
        if attempt < _WORKER_LIVENESS_RETRIES:
            await asyncio.sleep(_WORKER_LIVENESS_RETRY_DELAY_SECONDS)
    return (
        Status.FAILED,
        f"vectorization worker liveness could not be confirmed: {last_reason}",
        started_fresh,
    )


async def stop_vectorization_worker_if_started(
    client: CodeAnalysisAsyncClient, started_fresh: bool
) -> None:
    """Stop the vectorization worker in teardown, but only if THIS run started it.

    A concurrent suite may depend on an already-running worker; stopping it out
    from under that suite would be its own flake source, so this is a no-op
    when :func:`start_and_verify_vectorization_worker` reported
    ``started_fresh=False`` (this includes the case where it reused an
    already-running boot worker instead of starting its own -- see that
    function's "restart race" wait).

    When the stop actually runs, this logs (observability only, no restart
    attempted here) whether a vectorization worker remains running
    afterwards -- e.g. a boot worker that registered while THIS call's worker
    was alive would leave the fleet covered; none remaining is the scenario
    :func:`start_and_verify_vectorization_worker`'s pre-start wait exists to
    avoid, so seeing it here after the wait was added would itself be a
    signal worth investigating.

    Args:
        client: Connected async client.
        started_fresh: Value returned by
            :func:`start_and_verify_vectorization_worker`.
    """
    if not started_fresh:
        return
    await call_step(
        client,
        "stop_worker",
        {"worker_type": "vectorization"},
        ok_reason="vectorization worker stopped",
    )
    still_running, remain_reason = await _poll_worker_is_running(
        client, "vectorization", timeout_seconds=0.0, interval_seconds=0.0
    )
    logger.info(
        "stop_vectorization_worker_if_started: post-stop vectorization worker "
        "state -- %s (%s)",
        "still running (another worker covers the fleet)"
        if still_running
        else "not running (fleet is workerless until a new one starts)",
        remain_reason,
    )


async def scan_vectorization_log_for_cap_errors(
    client: CodeAnalysisAsyncClient,
    *,
    tail_lines: int = 2000,
    search_pattern: str = "exceeds the maximum allowed",
) -> Tuple[Status, str]:
    """Scan the vectorization worker log for the embed service's cap-error text.

    Bug 16b1abbe's un-fixed behavior has a distinctive log signature: the
    embed service's own rejection message ("Job command failed: Batch size N
    exceeds the maximum allowed (20)") on every cycle that tries to send an
    oversized batch. :func:`poll_check_vectors_fully_embedded` proves chunks
    eventually got a model recorded, but that alone does not prove the cap
    was never hit -- a server that silently retried past a cap rejection (or
    fell back to some other broken path that still eventually records a
    model) would slip through the poll alone. This scan is the second,
    independent half of the 16b1abbe regression signature the caller checks
    for: embedding completed AND the cap was never actually exceeded.

    Uses ``tail`` rather than a computed ``from_time`` window: log lines are
    parsed as naive local timestamps (see ``log_viewer_utils.
    parse_log_timestamp``) with no guaranteed clock parity between this
    client and the remote server, so a client-computed ``from_time`` would be
    an unreliable bound. ``tail_lines`` is generous enough to cover this
    check's own run (a single-project, single-file fixture) even under a
    busy shared fleet log.

    Args:
        client: Connected async client.
        tail_lines: How many of the most recent vectorization-log lines to
            search.
        search_pattern: Regex/text passed to ``view_worker_logs``'s
            ``search_pattern``.

    Returns:
        ``(status, reason)``. :attr:`Status.EXECUTED_OK` when zero matching
        log lines were found; :attr:`Status.FAILED` with the matching
        entries (truncated) otherwise. A failed ``view_worker_logs`` call
        itself is also reported as :attr:`Status.FAILED` -- a check that
        cannot confirm the log is clean must not silently pass.
    """
    outcome, data = await call_step_with_data(
        client,
        "view_worker_logs",
        {
            "worker_type": "vectorization",
            "search_pattern": search_pattern,
            "tail": tail_lines,
        },
        ok_reason="vectorization log scanned for cap errors",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return (
            Status.FAILED,
            f"could not scan the vectorization log for cap errors: {outcome.reason}",
        )
    data = data or {}
    filtered = data.get("filtered_lines")
    if not isinstance(filtered, int):
        filtered = len(data.get("entries") or [])
    if filtered == 0:
        return (
            Status.EXECUTED_OK,
            f"0 hits for {search_pattern!r} in the last {tail_lines} "
            "vectorization log line(s)",
        )
    entries = data.get("entries") or []
    return (
        Status.FAILED,
        f"{filtered} hit(s) for {search_pattern!r} in the last {tail_lines} "
        f"vectorization log line(s): {truncate(repr(entries))}",
    )
