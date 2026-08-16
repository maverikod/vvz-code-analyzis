"""
Vectorization embed-batch-cap check (bug 16b1abbe).

Registered as suite ``s23`` (``realsrv_test.suites.s23_vectorization_batch_cap``,
``SUITE_NAME = "vectorization_batch_cap"``).

The embed service enforces a hard per-request text cap (20 by default; "Job
command failed: Batch size N exceeds the maximum allowed (20)"). Before bug
16b1abbe's fix, ``process_chunk_only_files`` (``core/vectorization_worker_pkg/
batch_processor.py``) sent ALL of a file's un-vectorized chunks in one
``get_embeddings()`` call, so any file with more than the cap's worth of
un-vectorized chunks failed its whole embed call every worker cycle and never
made progress (nor did it ever dead-letter, since the whole-batch exception
bypassed the per-chunk retry/dead-letter accounting entirely).

Mechanism: create an ISOLATED disposable project (own throwaway project, not
the shared sweep fixture — this check needs full control over what the
vectorization worker sees, mirroring
``realsrv_test.core.lifecycle_indexer_correctness.
run_update_indexes_usages_idempotent``'s isolated-project pattern), upload
ONE ``.py`` file with more documented functions than the cap (so the
docstring chunker persists more than 20 embedding-less ``code_chunks`` rows
for that single file — see ``core/docstring_chunker_pkg/docstring_chunker.py``,
one chunk per documented function), run ``update_indexes`` to index it,
``start_worker(worker_type="vectorization")`` to drive the real chunk-only
embed + ANN-index pipeline without waiting for file-watcher discovery, and
poll ``check_vectors`` with a bounded timeout for ``chunks_with_model ==
total_chunks`` (every chunk got an embedding-model round-trip). On the
unfixed server this must go RED: the oversized embed call keeps failing
outright, so the file's chunks never get a model recorded at all.

Why full ANN completion (``chunks_pending_vectorization == 0`` /
``chunks_with_vector == total_chunks``) is deliberately NOT asserted here
(1.6.114 gate hardening): STEP 2 of vectorization -- writing
``embedding_vec`` / the ANN index entry once a chunk has a model -- is
throttled by ``worker.batch_size`` PER PROJECT PER FLEET CYCLE (5 by
default). The vectorization worker is universal: it visits every project on
the fleet in its poll loop, not just this check's isolated one. Once 1.6.114
unpaused every project and the fleet started draining a large shared
backlog, a single fleet cycle can take minutes, so this check's bounded poll
window can observe only a couple of cycles worth of ANN writes for its own
project -- nowhere near enough to require full ANN completion within the
window. That is fleet-wide ANN write throughput, not the bug 16b1abbe
guards, so requiring it here would make this check RED for a reason
unrelated to 16b1abbe whenever the fleet is busy. See
``vectorization_fixture_common.poll_check_vectors_fully_embedded``'s
docstring for the full reasoning, and
``vectorization_fixture_common.scan_vectorization_log_for_cap_errors`` for
the second half of the signature this check now also asserts: the embed
service's per-request cap must never actually have been hit during the run
(a silent retry-past-cap could otherwise complete embedding while still
being the bug this check exists to catch).

The isolated-project creation, fixture source generation, and check_vectors
polling live in ``realsrv_test.core.vectorization_fixture_common`` (factored
out during the 1.6.113 hardening pass so ``lifecycle_vector_dim_parity.py``
can share the same machinery instead of targeting a hardcoded fixed project).
That same pass also added the worker start/stop hardening this lifecycle uses
(``start_and_verify_vectorization_worker`` / ``stop_vectorization_worker_if_
started``): confirm the worker process is actually alive via
``get_worker_status`` (bounded retries) before trusting the poll window, and
only stop the worker in teardown when THIS call actually started a fresh one
-- a concurrent suite's already-running worker must not get stopped out from
under it. The 1.6.114 pass added a further wait, before that start, for an
already-running boot worker (see ``start_and_verify_vectorization_worker``'s
docstring) to close a restart race that could otherwise leave the fleet with
no vectorization worker at all after this check's teardown.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step
from realsrv_test.core.vectorization_fixture_common import (
    create_isolated_vectorization_project,
    poll_check_vectors_fully_embedded,
    scan_vectorization_log_for_cap_errors,
    start_and_verify_vectorization_worker,
    stop_vectorization_worker_if_started,
    upload_fixture_file,
)

CHECK_NAME = "chunk_only_embed_batch_cap"

# Comfortably above the embed service's default 20-text cap so a single
# get_embeddings() call for the whole file is guaranteed to be rejected on
# the unfixed server.
_TOTAL_FUNCTIONS = 30

# Bumped from 180s -> 240s during the 1.6.113 hardening pass: the added
# liveness-verification step (start_and_verify_vectorization_worker, up to
# 3 retries with a 2s delay) eats into the time available before this poll's
# own deadline, and the shared probe server has been observed to take longer
# under concurrent-suite load than the original budget assumed. The cap
# semantics this check exists to prove (_TOTAL_FUNCTIONS=30 > the embed
# service's 20-text cap) are unchanged -- this only widens the flake margin.
_POLL_TIMEOUT_SECONDS = 240.0
_POLL_INTERVAL_SECONDS = 5.0


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map this lifecycle returns.

    Args:
        status: Outcome status for the check.
        reason: Human-readable explanation of the result.

    Returns:
        ``{CHECK_NAME: CommandOutcome(...)}``, the shape ``run_lifecycles`` merges.
    """
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def run_vectorization_batch_cap_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run the embed-batch-cap check against its own isolated disposable project.

    Args:
        client: Connected async client.
        fixtures: The shared sweep fixture (only used as a fallback session
            source if the isolated project's own session bootstrap is not
            needed — this check opens no extra session, it reuses
            ``client.file_sessions.upload_new`` directly against the
            isolated project via a fresh session created here).

    Returns:
        ``{CHECK_NAME: outcome}`` — :attr:`Status.EXECUTED_OK` only when
        every chunk of the oversized fixture file ends up with an embedding
        model recorded (``chunks_with_model == total_chunks``) within the
        bounded poll AND the vectorization log shows zero cap-rejection hits
        for the run (see module docstring for why ANN/``chunks_with_vector``
        completion is intentionally not required here).
    """
    project_id, project_root, create_status, create_reason = (
        await create_isolated_vectorization_project(
            client,
            name_prefix="verify_vecbatchcap",
            description="isolated disposable project for the embed batch-cap check (bug 16b1abbe)",
        )
    )
    if create_status is not Status.EXECUTED_OK:
        return _outcome(Status.FAILED, create_reason)
    assert project_id is not None and project_root is not None

    started_fresh = False
    try:
        relative_path = "batch_cap_fixture.py"
        file_id, upload_status, upload_reason = await upload_fixture_file(
            client,
            project_id=project_id,
            relative_path=relative_path,
            total_functions=_TOTAL_FUNCTIONS,
            session_comment="vectorization batch-cap check (bug 16b1abbe)",
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
            poll_status, poll_reason, final_data = await poll_check_vectors_fully_embedded(
                client,
                project_id,
                timeout_seconds=_POLL_TIMEOUT_SECONDS,
                interval_seconds=_POLL_INTERVAL_SECONDS,
            )
        finally:
            # Conditional stop (1.6.113 hardening): only stop the worker if this
            # call actually started a fresh one -- see module docstring.
            await stop_vectorization_worker_if_started(client, started_fresh)

        if poll_status is not Status.EXECUTED_OK:
            return _outcome(
                Status.FAILED,
                f"{relative_path}: not fully embedded within "
                f"{_POLL_TIMEOUT_SECONDS:.0f}s ({poll_reason}) — bug 16b1abbe: a "
                "file with more un-vectorized chunks than the embed service's "
                "per-request text cap never completes embedding "
                f"(last check_vectors data: {truncate(repr(final_data))})",
            )

        cap_scan_status, cap_scan_reason = await scan_vectorization_log_for_cap_errors(
            client
        )
        if cap_scan_status is not Status.EXECUTED_OK:
            return _outcome(
                Status.FAILED,
                f"{relative_path}: all {_TOTAL_FUNCTIONS} chunk(s) got an "
                f"embedding model ({poll_reason}) but the cap-error log scan "
                f"failed the 16b1abbe signature: {cap_scan_reason}",
            )

        return _outcome(
            Status.EXECUTED_OK,
            f"{relative_path}: all {_TOTAL_FUNCTIONS} chunk(s) fully embedded "
            f"within {_POLL_TIMEOUT_SECONDS:.0f}s ({poll_reason}); cap-error "
            f"log scan clean ({cap_scan_reason})",
        )
    finally:
        try:
            # 1.6.114 gate hardening: this used to call a non-existent
            # "delete_project" command, so this teardown always raised and
            # was silently swallowed below -- the isolated disposable project
            # was NEVER actually deleted by any run of this check. The real
            # command is "project_set_mark_del" (see
            # ``code_analysis/commands/project_management_mcp_commands/
            # delete_project.py``); orphaned "verify_vecbatchcap_*" projects
            # from that bug were found still sitting in the live fleet's
            # vectorization queue hours later, endlessly re-chunking the same
            # already-chunked file every cycle (their needs_chunking state
            # never cleared either) and materially contributing to the
            # fleet-load contention this check's own predicate exists to
            # tolerate.
            await client.call_validated(
                "project_set_mark_del",
                {"project_id": project_id, "delete_from_disk": True},
            )
        except Exception:  # noqa: BLE001 - best-effort cleanup only, even on failure
            pass
