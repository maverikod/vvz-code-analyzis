"""
Bounded grep-phase liveness check for the search(enable_grep=true) hang (bug 0c124699).

Groundwork/regression guard, not a full re-verification of the bug: starts a
``search`` job with ``enable_grep=true`` against a freshly-seeded, deliberately
UN-indexed file (so the coverage pre-filter cannot skip it as
"indexed_current" - it is guaranteed to land in the on-disk grep candidate
set), then polls ``search_get_status`` in a bounded wall-clock window and
asserts two things that were both false before the 0c124699 fix:

1. The job reaches a terminal status (anything other than ``"running"``)
   within the bound - the symptom this check guards against is the grep
   phase never finishing within a sane wall-clock budget.
2. ``progress["scanned_files"]`` (``manifest.metrics[METRIC_SCANNED_FILES]``)
   moves off ``0`` at some point during the poll - the metric a stuck job
   used to leave frozen at ``0`` for its entire run, making a live grep scan
   indistinguishable from a genuinely hung one to a polling client.

Conventions follow ``_verify_client_all_commands_lifecycle_list_files_fast.py``
(a single-check, catalog-shaped module returning ``{CHECK_NAME: CommandOutcome}``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step_with_data

CHECK_NAME = "search_grep_bounded_liveness"

# Wall-clock bound for the whole grep phase to reach a terminal status.
_MAX_WALL_SECONDS = 60.0
_POLL_INTERVAL_SECONDS = 1.5


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def _best_effort_close(client: CodeAnalysisAsyncClient, job_id: str) -> None:
    """Close a search job without letting cleanup failures affect the verdict."""
    if not job_id:
        return
    try:
        await client.call_validated("search_close", {"job_id": job_id})
    except Exception:  # noqa: BLE001 - cleanup only
        pass


async def run_search_grep_bounded_liveness_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Bound the grep phase's wall time and confirm live scanned_files progress.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME: outcome}`` - :attr:`Status.EXECUTED_OK` only when the
        job reaches a terminal status within :data:`_MAX_WALL_SECONDS` AND
        ``scanned_files`` was observed > 0 at some point during the poll.
    """
    if not fixtures.session_id:
        return _outcome(
            Status.EXPECTED_ERROR, "skipped: no fixture session_id available"
        )

    token = f"verifygrepbounded{uuid.uuid4().hex}"
    relative_path = f"verify_grep_bounded_{uuid.uuid4().hex[:8]}.py"
    # Deliberately NOT followed by update_indexes: an un-indexed file is
    # guaranteed to be an index-gap candidate for the grep coverage
    # pre-filter, so the grep phase always has >=1 real file to scan on disk.
    content = f'"""Grep-bounded liveness fixture.\n\nToken: {token}\n"""\n'

    try:
        file_id = await client.file_sessions.upload_new(
            fixtures.session_id,
            content.encode("utf-8"),
            fixtures.project_id,
            relative_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(Status.FAILED, truncate(f"seed upload failed: {exc!r}"))
    if not file_id:
        return _outcome(Status.FAILED, "seed upload returned no file_id")

    search_outcome, search_data = await call_step_with_data(
        client,
        "search",
        {
            "project_id": fixtures.project_id,
            "query": token,
            "enable_semantic": False,
            "enable_grep": True,
            "grep_patterns": [token],
        },
        ok_reason="grep-enabled search job started against the disposable project",
    )
    if search_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            search_outcome.status,
            f"search(enable_grep=true) call itself failed: {search_outcome.reason}",
        )
    job_id = str((search_data or {}).get("job_id") or "").strip()
    if not job_id:
        return _outcome(
            Status.FAILED, "search(enable_grep=true) returned no job_id"
        )

    started = time.monotonic()
    deadline = started + _MAX_WALL_SECONDS
    max_scanned_files = 0
    last_status = "running"
    reached_terminal = False
    poll_count = 0

    while True:
        poll_count += 1
        status_outcome, status_data = await call_step_with_data(
            client, "search_get_status", {"job_id": job_id}
        )
        if status_outcome.status is not Status.EXECUTED_OK:
            await _best_effort_close(client, job_id)
            return _outcome(
                Status.FAILED,
                f"search_get_status failed on poll #{poll_count} "
                f"(elapsed={time.monotonic() - started:.1f}s): {status_outcome.reason}",
            )
        payload = status_data or {}
        last_status = str(payload.get("status") or "")
        progress = payload.get("progress") or {}
        scanned_files = int(progress.get("scanned_files") or 0)
        max_scanned_files = max(max_scanned_files, scanned_files)

        if last_status != "running":
            reached_terminal = True
            break
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    elapsed = time.monotonic() - started
    await _best_effort_close(client, job_id)

    if not reached_terminal:
        return _outcome(
            Status.FAILED,
            f"job {job_id} still 'running' after {elapsed:.1f}s "
            f"(bound={_MAX_WALL_SECONDS}s, {poll_count} polls, "
            f"max scanned_files observed={max_scanned_files}) - grep phase did "
            "not reach a terminal status within the bounded wall",
        )
    if max_scanned_files <= 0:
        return _outcome(
            Status.FAILED,
            f"job {job_id} reached terminal status {last_status!r} in "
            f"{elapsed:.1f}s, but scanned_files never moved off 0 across "
            f"{poll_count} poll(s) - metrics.scanned_files is not live-wired",
        )
    return _outcome(
        Status.EXECUTED_OK,
        f"job {job_id} reached terminal status {last_status!r} in {elapsed:.1f}s "
        f"(bound={_MAX_WALL_SECONDS}s); scanned_files reached {max_scanned_files} "
        f"across {poll_count} poll(s)",
    )
