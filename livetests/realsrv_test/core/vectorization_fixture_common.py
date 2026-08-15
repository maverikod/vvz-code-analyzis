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

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Status, truncate
from realsrv_test.core.lifecycle_common import call_step, call_step_with_data

# Bounded retries to confirm the vectorization worker process is actually alive
# (get_worker_status summary.is_running) before trusting the poll window that
# follows -- start_worker returning success does not guarantee the spawned
# process has registered itself yet (multiprocessing.Process.start() returns
# before the child finishes its own startup).
_WORKER_LIVENESS_RETRIES = 3
_WORKER_LIVENESS_RETRY_DELAY_SECONDS = 2.0


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
) -> Tuple[Optional[str], Optional[str], Status, str]:
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
        ``(project_id, project_root, status, reason)``. ``status`` is
        :attr:`Status.EXECUTED_OK` with ``project_id``/``project_root`` set on
        success; otherwise both are ``None`` and ``reason`` explains the
        failure.
    """
    watch_dir_status, watch_dir_data = await call_step_with_data(
        client, "list_watch_dirs", {}, ok_reason="watch directories listed"
    )
    watch_dirs = (watch_dir_data or {}).get("watch_dirs") or []
    if watch_dir_status.status is not Status.EXECUTED_OK or not watch_dirs:
        return (
            None,
            None,
            Status.FAILED,
            f"could not list a watch_dir for the isolated project ({watch_dir_status.reason})",
        )
    watch_dir_id = str(watch_dirs[0]["id"])

    suffix = uuid.uuid4().hex[:8]
    create_status, create_data = await call_step_with_data(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": f"{name_prefix}_{suffix}",
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
            Status.FAILED,
            f"could not create the isolated project ({create_status.reason})",
        )
    project_id = str((create_data or {}).get("project_id") or "")
    project_root = str((create_data or {}).get("project_root") or "")
    if not project_id or not project_root:
        return (
            None,
            None,
            Status.FAILED,
            f"create_project response missing project_id/project_root: {create_data!r}",
        )
    return project_id, project_root, Status.EXECUTED_OK, "isolated project ready"


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


async def start_and_verify_vectorization_worker(
    client: CodeAnalysisAsyncClient, project_id: str
) -> Tuple[Status, str, bool]:
    """Start the vectorization worker and confirm it is actually alive before the
    caller opens its poll window.

    Args:
        client: Connected async client.
        project_id: Project to pass to ``start_worker``.

    Returns:
        ``(status, reason, started_fresh)``. ``status`` is
        :attr:`Status.EXECUTED_OK` once liveness is confirmed (or the worker
        was already running -- either way there is a live worker to poll
        against). ``started_fresh`` is True only when THIS call's
        ``start_worker`` actually spawned a new process (i.e. the response did
        not report "already running") -- callers use this to decide whether
        their teardown should ``stop_worker``: stopping a worker a concurrent
        suite depends on would be its own regression.
    """
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
    ``started_fresh=False``.

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
