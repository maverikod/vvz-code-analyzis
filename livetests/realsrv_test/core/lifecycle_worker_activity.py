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
it starts a REAL worker process against a REAL disposable project with a
small fixture file pending vectorization and asserts observable, COMPLETE
embedding progress, not just a successful-looking start.

Mechanism: create an ISOLATED disposable project and upload a small fixture
``.py`` module with a few documented functions (one un-vectorized
``code_chunks`` row per function via the docstring chunker -- see
``core/docstring_chunker_pkg/docstring_chunker.py``), run ``update_indexes``
once so the file is registered and chunked, then start a vectorization
worker scoped to that project via ``start_worker``. Poll ``check_vectors`` on
the disposable project for up to :data:`_POLL_TIMEOUT_SECONDS`: a live,
correctly-configured worker will pick up the pending file, chunk it, and
embed EVERY chunk, driving ``chunks_pending_vectorization`` to ``0`` and
``chunks_with_model`` up to ``total_chunks``.

IMPORTANT -- why the predicate must require ``chunks_with_model ==
total_chunks`` and not merely ``total_chunks > 0``: chunking is driven by the
indexer/chunker pipeline, NOT by the vectorization worker, so a project can
accumulate chunks (``total_chunks > 0``) even when the vectorization worker
itself is completely broken. A pre-fix server (``svo_config=None``) still
chunks the fixture file normally -- what it can never do is EMBED a chunk, so
``chunks_with_model`` stays at ``0`` forever while ``chunks_pending_
vectorization`` stays stuck at ``total_chunks``. Only a predicate that
requires the embed round-trip to actually complete (see
``vectorization_fixture_common.poll_check_vectors_fully_vectorized``) can
distinguish "worker chunked it" from "worker embedded it", which is the only
thing bug 827e2b05 breaks.

The isolated-project creation, fixture source generation, worker start/stop
hardening, and ``check_vectors`` polling live in
``realsrv_test.core.vectorization_fixture_common``, the same machinery
``lifecycle_vectorization_batch_cap.py`` and ``lifecycle_vector_dim_parity.py``
use, so all three vectorization-worker livetests stay in sync instead of
drifting apart.

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
``start_and_verify_vectorization_worker``'s ``started_fresh`` flag), but on a
pre-fix server that still leaves a duplicate, permanently-broken worker
process behind that this check cannot clean up by itself. THE ORCHESTRATOR
MUST SCHEDULE A DELIBERATE RED RUN OF THIS SUITE ONLY IMMEDIATELY BEFORE A
DEPLOY THAT WILL RESTART THE SERVICE -- never against a long-lived pre-fix
production server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict, List

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step
from realsrv_test.core.vectorization_fixture_common import (
    create_isolated_vectorization_project,
    poll_check_vectors_fully_vectorized,
    start_and_verify_vectorization_worker,
    stop_vectorization_worker_if_started,
    upload_fixture_file,
)

CHECK_NAME = "worker_activity_manual_start_vectorization_progresses"

# Small and well under the embed service's default 20-text batch cap -- this
# check is about the worker being alive and able to embed at all (bug
# 827e2b05), not about the batch-cap path (that's
# lifecycle_vectorization_batch_cap.py, bug 16b1abbe).
_TOTAL_FUNCTIONS = 5

_RELATIVE_PATH = "worker_activity_fixture.py"

# The strict predicate (poll_check_vectors_fully_vectorized) requires the
# full chunk -> embed round-trip to complete, not just chunking, so this
# needs more headroom than a "chunking happened" check would.
_POLL_TIMEOUT_SECONDS = 150.0
_POLL_INTERVAL_SECONDS = 5.0


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map this module returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def run_worker_activity_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Start a real vectorization worker and assert it fully embeds a fixture file.

    Args:
        client: Connected async client.
        fixtures: Unused -- this check creates and tears down its OWN
            isolated disposable project (never ``fixtures.project_id``) so a
            pre-existing project's chunk state cannot mask (or fake) the
            result.

    Returns:
        ``{CHECK_NAME: outcome}``. :attr:`Status.EXECUTED_OK` only when
        ``check_vectors`` on the disposable project shows every chunk fully
        embedded (``total_chunks > 0``, ``chunks_pending_vectorization == 0``,
        ``chunks_with_model == total_chunks``) within the poll window --
        :attr:`Status.FAILED` (RED) otherwise. See the module docstring for
        why the predicate must require completed embedding, not just
        chunking, and for the teardown constraint this check cannot fully
        self-heal on a pre-fix server.
    """
    project_id, _project_root, create_status, create_reason = (
        await create_isolated_vectorization_project(
            client,
            name_prefix="verify_worker_activity",
            description="isolated disposable project for the manual-start vectorization-worker activity check (bug 827e2b05)",
        )
    )
    if create_status is not Status.EXECUTED_OK:
        return _outcome(Status.FAILED, create_reason)
    assert project_id is not None

    started_fresh = False
    try:
        file_id, upload_status, upload_reason = await upload_fixture_file(
            client,
            project_id=project_id,
            relative_path=_RELATIVE_PATH,
            total_functions=_TOTAL_FUNCTIONS,
            session_comment="worker-activity manual-start check (bug 827e2b05)",
        )
        if upload_status is not Status.EXECUTED_OK:
            return _outcome(Status.FAILED, upload_reason)
        assert file_id is not None

        update_status = await call_step(
            client,
            "update_indexes",
            {"project_id": project_id},
            ok_reason=f"indexed the {_TOTAL_FUNCTIONS}-function fixture file",
        )
        if update_status.status is not Status.EXECUTED_OK:
            return _outcome(
                update_status.status,
                f"update_indexes did not succeed: {update_status.reason}",
            )

        start_status, start_reason, started_fresh = (
            await start_and_verify_vectorization_worker(client, project_id)
        )
        if start_status is not Status.EXECUTED_OK:
            return _outcome(start_status, start_reason)

        try:
            poll_status, poll_reason, final_data = await poll_check_vectors_fully_vectorized(
                client,
                project_id,
                timeout_seconds=_POLL_TIMEOUT_SECONDS,
                interval_seconds=_POLL_INTERVAL_SECONDS,
            )
        finally:
            # Conditional stop: only stop the worker if this call actually
            # started a fresh one -- a concurrent suite's already-running
            # worker must survive our teardown. See module docstring.
            await stop_vectorization_worker_if_started(client, started_fresh)

        if poll_status is Status.EXECUTED_OK:
            return _outcome(
                Status.EXECUTED_OK,
                f"project={project_id}: {poll_reason} (manual start_worker kwargs "
                "are boot-parity and the worker actually embedded every chunk)",
            )
        return _outcome(
            Status.FAILED,
            f"project={project_id}: not fully vectorized within "
            f"{_POLL_TIMEOUT_SECONDS:.0f}s ({poll_reason}) -- bug 827e2b05: a "
            "pre-fix server computes svo_config=None for a manually-started "
            "vectorization worker, so it chunks files normally but can never "
            f"embed anything (last check_vectors data: {truncate(repr(final_data))})",
        )
    finally:
        try:
            await client.call_validated(
                "delete_project",
                {"project_id": project_id, "delete_from_disk": True},
            )
        except Exception:  # noqa: BLE001 - best-effort cleanup only, even on failure
            pass


# Re-exported for realsrv_test._cli --list and suite discovery.
__all__: List[str] = ["run_worker_activity_check", "CHECK_NAME"]
