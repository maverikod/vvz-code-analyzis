"""
Vectorization embed-batch-cap check (bug 16b1abbe).

Registered as suite ``s22`` (``realsrv_test.suites.s22_vectorization_batch_cap``,
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
poll ``check_vectors`` with a bounded timeout for
``chunks_pending_vectorization == 0`` and ``chunks_with_model == total_chunks``.
On the unfixed server this must go RED: the oversized embed call keeps
failing outright, so the file's chunks never leave "pending".

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step, call_step_with_data

CHECK_NAME = "chunk_only_embed_batch_cap"

# Comfortably above the embed service's default 20-text cap so a single
# get_embeddings() call for the whole file is guaranteed to be rejected on
# the unfixed server.
_TOTAL_FUNCTIONS = 30

_POLL_TIMEOUT_SECONDS = 180.0
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


def _generate_fixture_source(total_functions: int) -> str:
    """Build a ``.py`` module with ``total_functions`` documented functions.

    Each function gets its own one-line docstring so the docstring chunker
    persists one ``code_chunks`` row per function (see module docstring) —
    ``total_functions`` un-vectorized chunks for a single file.

    Args:
        total_functions: Number of top-level documented functions to emit.

    Returns:
        Full Python module source text.
    """
    lines = [
        '"""Fixture module for the vectorization embed-batch-cap check (bug 16b1abbe).',
        "",
        f"Has {total_functions} documented functions so the docstring chunker",
        "persists more un-vectorized chunks for this one file than the embed",
        "service's default per-request text cap (20).",
        '"""',
        "",
        "",
    ]
    for i in range(total_functions):
        lines.append(f"def batch_cap_fixture_fn_{i}() -> int:")
        lines.append(f'    """Return a fixed value; function #{i} of the batch-cap fixture set."""')
        lines.append(f"    return {i}")
        lines.append("")
        lines.append("")
    return "\n".join(lines)


async def _create_isolated_project(
    client: CodeAnalysisAsyncClient,
) -> tuple[Optional[str], Optional[str], Optional[Dict[str, CommandOutcome]]]:
    """Create the isolated throwaway project this check runs against.

    Args:
        client: Connected async client.

    Returns:
        ``(project_id, project_root, None)`` on success, or
        ``(None, None, failure_outcome)`` on failure.
    """
    watch_dir_status, watch_dir_data = await call_step_with_data(
        client, "list_watch_dirs", {}, ok_reason="watch directories listed"
    )
    watch_dirs = (watch_dir_data or {}).get("watch_dirs") or []
    if watch_dir_status.status is not Status.EXECUTED_OK or not watch_dirs:
        return (
            None,
            None,
            _outcome(
                Status.FAILED,
                f"could not list a watch_dir for the isolated project ({watch_dir_status.reason})",
            ),
        )
    watch_dir_id = str(watch_dirs[0]["id"])

    suffix = uuid.uuid4().hex[:8]
    create_status, create_data = await call_step_with_data(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": f"verify_vecbatchcap_{suffix}",
            "description": "isolated disposable project for the embed batch-cap check (bug 16b1abbe)",
            "create_venv": False,
            "apply_template": False,
        },
        ok_reason="isolated throwaway project created",
    )
    if create_status.status is not Status.EXECUTED_OK:
        return (
            None,
            None,
            _outcome(
                Status.FAILED,
                f"could not create the isolated project ({create_status.reason})",
            ),
        )
    project_id = str((create_data or {}).get("project_id") or "")
    project_root = str((create_data or {}).get("project_root") or "")
    if not project_id or not project_root:
        return (
            None,
            None,
            _outcome(
                Status.FAILED,
                f"create_project response missing project_id/project_root: {create_data!r}",
            ),
        )
    return project_id, project_root, None


async def _poll_check_vectors(
    client: CodeAnalysisAsyncClient, project_id: str
) -> tuple[Status, str, Optional[Dict[str, Any]]]:
    """Poll ``check_vectors`` until fully vectorized or the bounded timeout expires.

    Args:
        client: Connected async client.
        project_id: Isolated project UUID.

    Returns:
        Tuple of (status, reason, last ``check_vectors`` data dict or None).
        ``status`` is :attr:`Status.EXECUTED_OK` only if, before the
        deadline, a poll observed ``chunks_pending_vectorization == 0`` and
        ``chunks_with_model == total_chunks`` with ``total_chunks > 0``.
    """
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
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
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    return Status.FAILED, last_reason, last_data


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
        every chunk of the oversized fixture file ends up fully vectorized
        (``chunks_pending_vectorization == 0`` and
        ``chunks_with_model == total_chunks``) within the bounded poll.
    """
    project_id, project_root, create_failure = await _create_isolated_project(client)
    if create_failure is not None:
        return create_failure
    assert project_id is not None and project_root is not None

    try:
        session_status, session_data = await call_step_with_data(
            client,
            "session_create",
            {"comment": "vectorization batch-cap check (bug 16b1abbe)"},
            ok_reason="session created for the isolated project",
        )
        if session_status.status is not Status.EXECUTED_OK:
            return _outcome(
                Status.FAILED,
                f"could not open a session ({session_status.reason})",
            )
        session_id = str((session_data or {}).get("session_id") or "")
        if not session_id:
            return _outcome(
                Status.FAILED,
                f"session_create response missing session_id: {session_data!r}",
            )

        relative_path = "batch_cap_fixture.py"
        content = _generate_fixture_source(_TOTAL_FUNCTIONS).encode("utf-8")
        try:
            file_id = await client.file_sessions.upload_new(
                session_id, content, project_id, relative_path
            )
        except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
            return _outcome(
                Status.FAILED, truncate(f"fixture file upload failed: {exc!r}")
            )
        if not file_id:
            return _outcome(Status.FAILED, "fixture upload returned no file_id")

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

        start_status = await call_step(
            client,
            "start_worker",
            {"worker_type": "vectorization", "project_id": project_id},
            ok_reason="vectorization worker started for the isolated project",
        )
        if start_status.status is not Status.EXECUTED_OK:
            return _outcome(
                start_status.status,
                f"start_worker(vectorization) did not succeed: {start_status.reason}",
            )

        try:
            poll_status, poll_reason, final_data = await _poll_check_vectors(
                client, project_id
            )
        finally:
            # Best-effort: this stops the process-wide vectorization worker
            # (stop_worker takes no project_id — see s07_workers' identical
            # file_watcher stop), matching the existing worker-lifecycle
            # idiom (realsrv_test.core.lifecycle_workers.run_worker_lifecycle).
            await call_step(
                client,
                "stop_worker",
                {"worker_type": "vectorization"},
                ok_reason="vectorization worker stopped",
            )

        if poll_status is Status.EXECUTED_OK:
            return _outcome(
                Status.EXECUTED_OK,
                f"{relative_path}: all {_TOTAL_FUNCTIONS} chunk(s) fully "
                f"vectorized within {_POLL_TIMEOUT_SECONDS:.0f}s ({poll_reason})",
            )
        return _outcome(
            Status.FAILED,
            f"{relative_path}: not fully vectorized within "
            f"{_POLL_TIMEOUT_SECONDS:.0f}s ({poll_reason}) — bug 16b1abbe: a "
            "file with more un-vectorized chunks than the embed service's "
            "per-request text cap never completes embedding "
            f"(last check_vectors data: {truncate(repr(final_data))})",
        )
    finally:
        try:
            await client.call_validated(
                "delete_project",
                {"project_id": project_id, "delete_from_disk": True},
            )
        except Exception:  # noqa: BLE001 - best-effort cleanup only, even on failure
            pass
