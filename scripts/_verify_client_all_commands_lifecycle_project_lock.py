"""
rename_project / emergency_unlock_project lock-roundtrip lifecycle check
(bugs 88f06abc, 5da73265).

Registered in ``_verify_client_all_commands_lifecycles.run_lifecycles``.

Flow, against the disposable ``fixtures.project_id``:
1. ``rename_project`` to a fresh uuid-based name -> confirm the returned
   ``project_id`` is unchanged and ``new_name`` matches.
2. ``list_projects`` to confirm the project is still reachable under the SAME
   ``project_id`` (no reindex required - deliberately does NOT call
   ``update_indexes``).
3. ``rename_project`` a SECOND time, back to the ORIGINAL name - this
   exercises the full lock acquire/release cycle twice and proves the lock
   from step 1 was actually released (a stuck lock would make this second
   call fail with PROJECT_LOCKED).
4. ``emergency_unlock_project`` with ``force=false`` on the now-unlocked
   project - confirms the report-only mode correctly shows ``locked: False``.
5. Best-effort limitation: this single-threaded script cannot truly hold a
   lock across two concurrent connections to synthesize a REAL stuck lock via
   the public API alone, so a genuinely-stuck-lock scenario is not exercised
   here (see the code comment at the bottom of this module).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step_with_data

CHECK_NAME = "project_exclusive_lock_rename_roundtrip"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def run_project_lock_rename_roundtrip_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Rename the fixture project twice and confirm the lock releases cleanly.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME: outcome}`` - :attr:`Status.EXECUTED_OK` only when both
        renames succeed (proving the lock acquire/release cycle completed
        twice without getting stuck) AND the post-roundtrip
        ``emergency_unlock_project`` report confirms ``locked: False``.
    """
    original_name = f"verify_lock_original_{uuid.uuid4().hex[:8]}"
    new_name = f"verify_lock_renamed_{uuid.uuid4().hex[:8]}"

    # Step 1: rename to a fresh name.
    rename_out, rename_data = await call_step_with_data(
        client,
        "rename_project",
        {"project_id": fixtures.project_id, "new_name": new_name},
        ok_reason="rename_project (forward) completed",
    )
    if rename_out.status is not Status.EXECUTED_OK:
        return _outcome(
            rename_out.status,
            f"forward rename_project did not succeed: {rename_out.reason}",
        )
    forward_data = rename_data or {}
    if forward_data.get("project_id") != fixtures.project_id:
        return _outcome(
            Status.FAILED,
            f"forward rename_project returned project_id="
            f"{forward_data.get('project_id')!r}, expected {fixtures.project_id!r} "
            "(project_id must never change across a rename)",
        )
    if forward_data.get("new_name") != new_name:
        return _outcome(
            Status.FAILED,
            f"forward rename_project returned new_name="
            f"{forward_data.get('new_name')!r}, expected {new_name!r}",
        )

    # Step 2: confirm the project is still reachable under the same
    # project_id (no reindex required - deliberately no update_indexes call).
    list_out, list_data = await call_step_with_data(
        client,
        "list_projects",
        {},
        ok_reason="list_projects reachable after rename",
    )
    if list_out.status is not Status.EXECUTED_OK:
        return _outcome(
            list_out.status,
            f"list_projects after rename did not succeed: {list_out.reason}",
        )
    items = (list_data or {}).get("items")
    if not isinstance(items, list) or not any(
        isinstance(row, dict) and row.get("id") == fixtures.project_id
        for row in items
    ):
        return _outcome(
            Status.FAILED,
            f"project_id {fixtures.project_id!r} not found in list_projects "
            "after rename - project became unreachable",
        )

    # Step 3: rename back to the original name - proves the lock from step 1
    # was released (a stuck lock would make this fail with PROJECT_LOCKED).
    back_out, back_data = await call_step_with_data(
        client,
        "rename_project",
        {"project_id": fixtures.project_id, "new_name": original_name},
        ok_reason="rename_project (back to original) completed",
    )
    if back_out.status is not Status.EXECUTED_OK:
        return _outcome(
            back_out.status,
            f"second rename_project (undo) did not succeed - the lock from "
            f"the first rename may be stuck: {back_out.reason}",
        )
    back_payload = back_data or {}
    if back_payload.get("new_name") != original_name:
        return _outcome(
            Status.FAILED,
            f"undo rename_project returned new_name="
            f"{back_payload.get('new_name')!r}, expected {original_name!r}",
        )

    # Step 4: emergency_unlock_project(force=false) must report locked=False
    # now that both renames completed and released their locks.
    report_out, report_data = await call_step_with_data(
        client,
        "emergency_unlock_project",
        {"project_id": fixtures.project_id, "force": False, "reason": ""},
        ok_reason="emergency_unlock_project report-only call completed",
    )
    if report_out.status is not Status.EXECUTED_OK:
        return _outcome(
            report_out.status,
            f"emergency_unlock_project(force=false) did not succeed: {report_out.reason}",
        )
    if (report_data or {}).get("locked") is not False:
        return _outcome(
            Status.FAILED,
            "emergency_unlock_project(force=false) reports locked="
            f"{(report_data or {}).get('locked')!r} after both renames "
            "completed - expected False (lock was not released cleanly)",
        )

    # Step 5 (documented limitation, not a skipped assertion): a genuinely
    # stuck lock (e.g. a crashed rename_project mid-flight) cannot be
    # synthesized here. This script drives one client against one live
    # server sequentially; there is no supported public-API way from this
    # single-threaded check alone to hold project_exclusive_locks open past
    # the end of a rename_project call and then run a second, concurrent
    # operation against the same project before releasing it. Exercising a
    # real stuck-lock scenario would require either a second live session
    # racing this one, or a privileged test-only hook to insert a lock row
    # directly - neither is available to this check. Steps 1-4 above are the
    # full extent of what is verifiable through the public API.
    return _outcome(
        Status.EXECUTED_OK,
        f"project {fixtures.project_id}: rename -> {new_name!r} -> back to "
        f"{original_name!r} roundtrip completed; lock released cleanly both "
        "times (confirmed via emergency_unlock_project force=false report)",
    )
