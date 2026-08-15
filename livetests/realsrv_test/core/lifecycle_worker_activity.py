"""
Live end-to-end proof that a manually-started vectorization worker is
actually alive and processing chunks (bug 827e2b05).

Registered as suite ``s25`` (``realsrv_test.suites.s25_worker_activity``,
``SUITE_NAME = "worker_activity"``).

Root cause under test: manual ``start_worker`` (``StartWorkerMCPCommand.execute``)
used to build the vectorization worker's ``svo_config`` by passing the ENTIRE
``code_analysis`` config section unfiltered into ``ServerConfig(**...)``.
``ServerConfig`` has ``model_config = {"extra": "forbid"}`` and any real
config carries a ``database`` key (and a ``storage`` key) that are not
``ServerConfig`` fields, so this deterministically raised a pydantic
``ValidationError`` that was swallowed into ``svo_config = None`` -- the
worker process started (PID present, ``start_worker`` reported success) but
could never actually embed anything. ``tests/test_worker_start_args_parity.py``
proves the kwargs the command computes are correct now at the unit level
(mocking the manager call); this check is the live, end-to-end counterpart --
it starts a REAL worker process against a REAL disposable project with one
file pending vectorization and asserts observable progress, not just a
successful-looking start.

Mechanism: create a disposable project, upload one small Python file into it
(``file_sessions.upload_new``), run ``update_indexes`` once so the file is
registered and (new file) marked ``needs_chunking``, then start a
vectorization worker scoped to that project via ``start_worker``. Poll
``check_vectors`` on the disposable project for up to ~90 seconds: a live,
correctly-configured worker will pick up the pending file, chunk it, and
embed it, driving ``total_chunks`` and eventually ``chunks_with_vector``
above zero. A pre-fix server never gets past svo_config=None, so neither
counter ever moves and this check goes RED.

Teardown constraint (read before scheduling a RED run): the vectorization
worker started by ``main_workers.py`` at server boot is UNIVERSAL -- it is
not scoped to one project, and the dedup guard against a second one is a PID
file keyed on ``worker_log_path`` (``core/worker_registry.py`` /
``core/worker_lifecycle.py``). On a PRE-FIX server, this check's manual
``start_worker`` computes a worker_log_path that diverges from boot's, so it
does NOT collide with an already-running boot worker's PID file -- it starts
a SECOND, differently-configured (svo_config=None) vectorization worker
process that coexists with the boot one and then goes on failing to embed
anything for every project on the server, not just this check's disposable
one, until a service restart reaps it. This check's own teardown only stops
the worker IT started (never a pre-existing boot worker -- see
``start_worker``'s "already running" message below), but on a pre-fix
server that still leaves a duplicate, permanently-broken worker process
behind that this check cannot clean up by itself. THE ORCHESTRATOR MUST
SCHEDULE A DELIBERATE RED RUN OF THIS SUITE ONLY IMMEDIATELY BEFORE A
DEPLOY THAT WILL RESTART THE SERVICE -- never against a long-lived
pre-fix production server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step_with_data

CHECK_NAME = "worker_activity_manual_start_vectorization_progresses"

_POLL_TIMEOUT_SECONDS = 90.0
_POLL_INTERVAL_SECONDS = 3.0

_FIXTURE_FILE_PATH = "src/needs_vectorization.py"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map this module returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def run_worker_activity_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Start a real vectorization worker and assert it makes observable progress.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run --
            only ``fixtures.session_id`` is used; this check creates and
            tears down its OWN disposable project (never
            ``fixtures.project_id``) so a pre-existing project's chunk state
            cannot mask (or fake) the result.

    Returns:
        ``{CHECK_NAME: outcome}``. :attr:`Status.EXECUTED_OK` only when
        ``check_vectors`` on the disposable project shows ``total_chunks`` or
        ``chunks_with_vector`` above zero within the poll window --
        :attr:`Status.FAILED` (RED) otherwise. See the module docstring for
        the teardown constraint this check cannot fully self-heal on a
        pre-fix server.
    """
    if not fixtures.session_id:
        return _outcome(Status.EXPECTED_ERROR, "skipped: no fixture session_id available")

    watch_dir_status, watch_dir_data = await call_step_with_data(
        client, "list_watch_dirs", {}, ok_reason="watch directories listed"
    )
    watch_dirs = (watch_dir_data or {}).get("watch_dirs") or []
    if watch_dir_status.status is not Status.EXECUTED_OK or not watch_dirs:
        return _outcome(
            Status.FAILED,
            f"could not list a watch_dir for the disposable project ({watch_dir_status.reason})",
        )
    watch_dir_id = str(watch_dirs[0]["id"])

    project_id: Optional[str] = None
    started_fresh_worker = False
    try:
        project_id, seed_error = await _seed_fixture_project(
            client, watch_dir_id=watch_dir_id, session_id=fixtures.session_id
        )
        if seed_error:
            return _outcome(Status.FAILED, truncate(seed_error))
        assert project_id is not None

        # Tolerant pre-cleanup: stop any leftover vectorization worker from a
        # previous interrupted run of this same check. Never treated as a
        # hard failure -- "nothing to stop" is the common/expected case.
        try:
            await client.call_validated(
                "stop_worker", {"worker_type": "vectorization", "timeout": 10}
            )
        except Exception:  # noqa: BLE001 - best-effort tolerant cleanup only
            pass

        start_outcome, start_data = await call_step_with_data(
            client,
            "start_worker",
            {"worker_type": "vectorization", "project_id": project_id},
            ok_reason="vectorization worker start requested for the disposable project",
        )
        if start_outcome.status is not Status.EXECUTED_OK:
            return _outcome(
                Status.FAILED,
                f"start_worker(vectorization) did not succeed: {start_outcome.reason}",
            )
        start_message = str((start_data or {}).get("message") or "")
        started_fresh_worker = "already running" not in start_message.lower()

        progress, poll_reason = await _poll_for_vectorization_progress(
            client, project_id
        )
        if progress:
            return _outcome(
                Status.EXECUTED_OK,
                f"project={project_id}: {poll_reason} (manual start_worker kwargs "
                "are boot-parity and the worker is actually processing chunks)",
            )
        return _outcome(
            Status.FAILED,
            f"project={project_id}: no vectorization progress observed within "
            f"{_POLL_TIMEOUT_SECONDS:.0f}s ({poll_reason}) -- bug 827e2b05: a "
            "pre-fix server computes svo_config=None for a manually-started "
            "vectorization worker, so it can never embed anything",
        )
    finally:
        if started_fresh_worker:
            try:
                await client.call_validated(
                    "stop_worker", {"worker_type": "vectorization", "timeout": 10}
                )
            except Exception:  # noqa: BLE001 - best-effort teardown only
                pass
        if project_id:
            try:
                await client.call_validated(
                    "project_set_mark_del", {"project_id": project_id}
                )
            except Exception:  # noqa: BLE001 - best-effort cleanup only
                pass


async def _seed_fixture_project(
    client: CodeAnalysisAsyncClient,
    *,
    watch_dir_id: str,
    session_id: str,
) -> tuple[Optional[str], Optional[str]]:
    """Create a disposable project with one file pending vectorization.

    Args:
        client: Connected async client.
        watch_dir_id: Watch directory to create the disposable project under.
        session_id: Open file-session id (not project-scoped).

    Returns:
        ``(project_id, error)`` -- ``error`` is ``None`` on success.
        ``project_id`` may be set even when ``error`` is not ``None`` (a
        later step failed after project creation), so the caller can still
        clean it up.
    """
    suffix = uuid.uuid4().hex[:8]
    create_status, create_data = await call_step_with_data(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": f"verify_worker_activity_{suffix}",
            "description": "throwaway fixture for the manual-start vectorization-worker activity check",
            "create_venv": False,
            "apply_template": False,
        },
        ok_reason="worker-activity fixture project created",
    )
    if create_status.status is not Status.EXECUTED_OK:
        return None, f"could not create the fixture project ({create_status.reason})"
    project_id = str((create_data or {}).get("project_id") or "")
    if not project_id:
        return None, f"create_project response missing project_id: {create_data!r}"

    token = uuid.uuid4().hex[:12]
    content = (
        f'"""Fixture file pending vectorization (token {token}).\n\n'
        "Deliberately long-ish docstring so the chunker has real text to "
        "split into at least one chunk instead of a trivial near-empty file.\n"
        '"""\n\n'
        "def fixture_function_for_vectorization_activity_check() -> int:\n"
        '    """Return a constant; only exists to give the vectorization '
        'worker something to embed."""\n'
        "    return 1\n"
    ).encode("utf-8")
    try:
        await client.file_sessions.upload_new(
            session_id, content, project_id, _FIXTURE_FILE_PATH
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return project_id, f"fixture file upload failed: {exc!r}"

    reindex_outcome, _reindex_data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": project_id},
        ok_reason="update_indexes run completed (registers the fixture file, marks needs_chunking)",
    )
    if reindex_outcome.status is not Status.EXECUTED_OK:
        return (
            project_id,
            f"update_indexes did not succeed: {reindex_outcome.reason}",
        )

    return project_id, None


async def _poll_for_vectorization_progress(
    client: CodeAnalysisAsyncClient, project_id: str
) -> tuple[bool, str]:
    """Poll ``check_vectors`` (and ``get_worker_status`` for diagnostics)
    for up to :data:`_POLL_TIMEOUT_SECONDS`, watching for chunking/embedding
    progress on the disposable project.

    Args:
        client: Connected async client.
        project_id: Disposable project id with one file pending vectorization.

    Returns:
        ``(progress_observed, reason)`` -- ``reason`` always describes the
        last observed state (for both the OK and FAILED outcome text).
    """
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    last_reason = "no check_vectors response observed"
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = await client.call_validated(
                "check_vectors", {"project_id": project_id}
            )
        except Exception as exc:  # noqa: BLE001 - keep polling despite one bad poll
            last_reason = f"check_vectors attempt {attempt} raised {exc!r}"
        else:
            if resp.get("success") is True:
                data = resp.get("data") or {}
                total_chunks = data.get("total_chunks") or 0
                chunks_with_vector = data.get("chunks_with_vector") or 0
                last_reason = (
                    f"check_vectors attempt {attempt}: total_chunks={total_chunks} "
                    f"chunks_with_vector={chunks_with_vector}"
                )
                if total_chunks > 0 or chunks_with_vector > 0:
                    return True, last_reason
            else:
                last_reason = (
                    f"check_vectors attempt {attempt} did not succeed: "
                    f"{truncate(str(resp.get('error')))}"
                )

        if time.monotonic() >= deadline:
            # One last diagnostic snapshot of the worker's own cycle stats,
            # merged into the reason text -- never gates the pass/fail
            # decision (get_worker_status's cycle_stats shape is best-effort
            # diagnostics, not a stable contract this check should depend on).
            diag = await _diagnostic_worker_status(client)
            if diag:
                last_reason = f"{last_reason}; {diag}"
            return False, last_reason

        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


async def _diagnostic_worker_status(client: CodeAnalysisAsyncClient) -> str:
    """Best-effort ``get_worker_status(vectorization)`` snapshot for the
    FAILED reason text. Never raises; returns "" on any problem."""
    try:
        resp = await client.call_validated(
            "get_worker_status", {"worker_type": "vectorization"}
        )
    except Exception:  # noqa: BLE001 - diagnostics only
        return ""
    if resp.get("success") is not True:
        return ""
    data = resp.get("data") or {}
    cycle_stats = data.get("cycle_stats")
    workers = data.get("workers") or data.get("processes")
    return f"get_worker_status diagnostics: cycle_stats={cycle_stats!r} workers={workers!r}"


# Re-exported for realsrv_test._cli --list and suite discovery.
__all__: List[str] = ["run_worker_activity_check", "CHECK_NAME"]
