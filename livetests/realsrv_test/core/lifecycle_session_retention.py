"""
Search-session idle-sweep retention regression check for the live-server verifier.

Proves the search-session cleanup sweeper actually removes an idle, closed
paginated search-session directory, instead of letting it accumulate on disk
forever. Measured locally before this fix: 69 session directories, 56,505
files, 1.6 GB under ``data/search_sessions``, oldest dating back roughly two
months with nothing ever expiring them.

Against a server that predates this fix, ``search_sessions_purge`` does not
exist on the command surface at all, so the very first call this check makes
to it fails outright -- a clean, deterministic RED signal, not a
timing-dependent guess about whether some other cleanup mechanism happened to
run before the check could observe it.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step_with_data

CHECK_NAME = "search_session_idle_sweep"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map this lifecycle returns.

    Args:
        status: Outcome status for this check.
        reason: Human-readable explanation.

    Returns:
        ``{CHECK_NAME: CommandOutcome(...)}``.
    """
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def run_session_retention_sweep_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Prove an idle, closed search session gets swept by the cleaner.

    Flow: ``search`` (creates a session against the disposable project) ->
    ``search_close`` (moves it to the "closed" terminal state, eligible for
    idle-based cleanup) -> ``search_sessions_purge`` with
    ``max_age_seconds=0`` (force-sweep every idle terminal session
    regardless of the configured retention, so this check does not have to
    wait out the real 1800s default or even the 60s minimum sweep cadence)
    -> ``search_get_page`` (must now report ``SESSION_NOT_FOUND``).

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME: outcome}``.
    """
    search_outcome, search_data = await call_step_with_data(
        client,
        "search",
        {
            "project_id": fixtures.project_id,
            "query": "Sample",
            "enable_semantic": False,
        },
    )
    if search_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            Status.FAILED,
            truncate(f"setup: search did not succeed: {search_outcome.reason}"),
        )
    job_id = str((search_data or {}).get("job_id") or "").strip()
    if not job_id:
        return _outcome(Status.FAILED, "setup: search returned no job_id")

    close_outcome, _close_data = await call_step_with_data(
        client, "search_close", {"job_id": job_id}
    )
    if close_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            Status.FAILED,
            truncate(
                f"setup: search_close did not succeed: {close_outcome.reason}"
            ),
        )

    purge_outcome, purge_data = await call_step_with_data(
        client,
        "search_sessions_purge",
        {"max_age_seconds": 0},
    )
    if purge_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            Status.FAILED,
            truncate(
                "search_sessions_purge did not succeed (missing on this "
                f"server?): {purge_outcome.reason}"
            ),
        )
    purged_ids = (purge_data or {}).get("purged_session_ids") or []
    if job_id not in purged_ids:
        return _outcome(
            Status.FAILED,
            truncate(
                f"search_sessions_purge ran but did not report {job_id!r} "
                f"as purged (purged={purged_ids!r})"
            ),
        )

    try:
        verify_resp = await client.call_validated(
            "search_get_page",
            {"job_id": job_id, "block_position": 1},
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            Status.FAILED,
            truncate(f"post-purge search_get_page raised: {exc!r}"),
        )

    if verify_resp.get("success") is not False:
        return _outcome(
            Status.FAILED,
            truncate(
                "session directory still resolvable after purge "
                f"(search_get_page success={verify_resp.get('success')!r})"
            ),
        )
    error_code = (verify_resp.get("error") or {}).get("code")
    if error_code != "SESSION_NOT_FOUND":
        return _outcome(
            Status.FAILED,
            truncate(
                f"search_get_page failed with unexpected code {error_code!r} "
                "after purge (expected SESSION_NOT_FOUND)"
            ),
        )

    return _outcome(
        Status.EXECUTED_OK,
        f"session {job_id} closed then purged; search_get_page now reports "
        "SESSION_NOT_FOUND",
    )
