"""
Dedicated ``list_project_files`` exact-path fast-path smoke check (bug 04cb1578).

A literal (non-glob) ``file_pattern`` naming a known, already-indexed file must
be served by the DB-first single-stat fast path
(``code_analysis.commands.ast.list_files``), not the O(N) full-project walk.
Before the fix, this exact shape of call was the one that took ~110s against a
~2900-file project and tripped the sync-cap -> queue fallback (see
``docs/bugreports`` for bug 04cb1578); after the fix it must return well under
one second as a plain (non-queued) response.

Reported under its own synthetic outcome name,
``list_project_files_exact_path_fast`` -- this deliberately does NOT replace or
short-circuit the generic ``list_project_files`` classification the main
alphabetical sweep performs elsewhere (that generic call has no reason to set
``file_pattern`` and so never exercises this fast path); it is purely
additive, exactly one more precomputed outcome merged into the same table
every other lifecycle module contributes to.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from typing import Any, Dict

from code_analysis_client import CodeAnalysisAsyncClient, QueuedJob

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext

CHECK_NAME = "list_project_files_exact_path_fast"

# Generous relative to the fast path's actual sub-second cost, but tight
# enough to catch a regression back to the O(N) full walk (~110s observed on
# the ~2900-file project that triggered bug 04cb1578).
_MAX_WALL_SECONDS = 15.0


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns.

    Args:
        status: Outcome status for this check.
        reason: Human-readable explanation.

    Returns:
        ``{CHECK_NAME: CommandOutcome(...)}``.
    """
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def run_list_project_files_exact_path_fast_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert the exact-path fast path serves a known existing file quickly.

    Picks the already-seeded ``.py`` fixture file (a known existing path in the
    disposable project) and calls ``list_project_files`` with that exact path
    as ``file_pattern``. Records :attr:`Status.FAILED` unless all of:

    (a) the call completes in under :data:`_MAX_WALL_SECONDS` wall-clock
        seconds;
    (b) the response is a plain result, not a queued-job handoff --
        ``auto_poll=False`` surfaces a :class:`QueuedJob` instead of a dict
        when the server falls back to the queue, which is itself evidence the
        fast path did not engage (a genuinely fast single-stat lookup never
        approaches the sync-cap that triggers the fallback);
    (c) the single returned entry carries the expected ``file_id`` /
        ``relative_path`` for the seeded file.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME: outcome}``, merged into the lifecycle-precomputed
        outcomes table like every other lifecycle module returns.
    """
    if not fixtures.py_file_path or not fixtures.py_file_id:
        return _outcome(
            Status.EXPECTED_ERROR,
            "skipped: seeded .py fixture file_path/file_id unavailable",
        )

    started = time.monotonic()
    try:
        result = await client.call_validated(
            "list_project_files",
            {
                "project_id": fixtures.project_id,
                "file_pattern": fixtures.py_file_path,
            },
            auto_poll=False,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(Status.FAILED, truncate(repr(exc)))
    elapsed = time.monotonic() - started

    if isinstance(result, QueuedJob):
        return _outcome(
            Status.FAILED,
            f"queued-job handoff instead of a plain fast-path result "
            f"(job_id={result.job_id!r}, elapsed={elapsed:.1f}s) -- the "
            "exact-path fast path did not engage",
        )

    if elapsed >= _MAX_WALL_SECONDS:
        return _outcome(
            Status.FAILED,
            f"took {elapsed:.1f}s (>= {_MAX_WALL_SECONDS}s budget) -- "
            "fast path did not engage",
        )

    if not result.get("success"):
        return _outcome(
            Status.FAILED, truncate(f"call failed: {result.get('error')!r}")
        )

    data: Dict[str, Any] = result.get("data") or {}
    files = data.get("files") or data.get("items") or []
    if len(files) != 1:
        return _outcome(
            Status.FAILED,
            truncate(f"expected exactly 1 entry, got {len(files)}: {files!r}"),
        )
    entry = files[0]
    if entry.get("file_id") != fixtures.py_file_id:
        return _outcome(
            Status.FAILED,
            truncate(
                f"file_id mismatch: expected {fixtures.py_file_id!r}, "
                f"got {entry.get('file_id')!r}"
            ),
        )
    if entry.get("relative_path") != fixtures.py_file_path:
        return _outcome(
            Status.FAILED,
            truncate(
                f"relative_path mismatch: expected {fixtures.py_file_path!r}, "
                f"got {entry.get('relative_path')!r}"
            ),
        )

    return _outcome(
        Status.EXECUTED_OK,
        f"exact-path fast path served the seeded file in {elapsed:.2f}s, "
        f"file_id={entry.get('file_id')!r} relative_path={entry.get('relative_path')!r}",
    )
