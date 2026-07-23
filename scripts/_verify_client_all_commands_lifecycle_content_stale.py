"""
Content-stale flag read-after-write lifecycle check (bug 56c23bd9).

UNREGISTERED groundwork module (intentionally not wired into
``_verify_client_all_commands_lifecycles.run_lifecycles`` — the search/
db-collapse implementer owns the registry; this module is handed off for
integration, per ``_verify_client_all_commands_lifecycle_fulltext_seeded.py``'s
own "unregistered groundwork" precedent).

Flow: seed a file, index it (baseline: not stale), edit its content through
the live CA write path (``universal_file_open`` -> ``universal_file_edit`` ->
``universal_file_write`` commit — the exact write path ``mark_file_content_stale``
hooks into, see ``code_analysis.commands.universal_file_edit.write_command``),
confirm ``search`` now reports ``content_stale: true`` for that file's hits,
then run ``update_indexes`` and confirm the SAME search reports
``content_stale: false`` again (reindex-success clear).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step_with_data

CHECK_NAME = "search_content_stale_write_then_reindex_roundtrip"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


def _content_stale_for_path(
    items: List[Any], relative_path: str
) -> Optional[bool]:
    """Return the ``content_stale`` flag of the seeded path's hit, or None if absent."""
    wanted = relative_path.replace("\\", "/").lstrip("./")
    for row in items:
        if not isinstance(row, dict):
            continue
        candidate = str(
            row.get("file_path") or row.get("path") or row.get("relative_path") or ""
        ).replace("\\", "/").lstrip("./")
        if candidate == wanted:
            return bool(row.get("content_stale"))
    return None


async def _search_for_token(
    client: CodeAnalysisAsyncClient, project_id: str, token: str
) -> tuple[CommandOutcome, List[Any], str]:
    """Run one fresh fulltext-only ``search`` job for ``token``."""
    outcome, data = await call_step_with_data(
        client,
        "search",
        {
            "project_id": project_id,
            "query": token,
            "enable_semantic": False,
            "enable_grep": False,
        },
        ok_reason="content_stale roundtrip search completed",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return outcome, [], ""
    payload = data or {}
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    return outcome, items, str(payload.get("job_id") or "")


async def _best_effort_close(client: CodeAnalysisAsyncClient, job_id: str) -> None:
    """Close a search job without letting cleanup failures affect the verdict."""
    if not job_id:
        return
    try:
        await client.call_validated("search_close", {"job_id": job_id})
    except Exception:  # noqa: BLE001 - cleanup only
        pass


async def run_content_stale_roundtrip_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Seed+index a file, edit it through CA, confirm stale->clear roundtrip.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME: outcome}`` - :attr:`Status.EXECUTED_OK` only when the
        post-write search shows ``content_stale: true`` for the seeded file
        AND the post-reindex search shows ``content_stale: false`` again.
    """
    if not fixtures.session_id:
        return _outcome(
            Status.EXPECTED_ERROR, "skipped: no fixture session_id available"
        )

    token = f"verifystale{uuid.uuid4().hex}"
    relative_path = f"verify_content_stale_{uuid.uuid4().hex[:8]}.py"
    original_content = (
        f'"""Seeded fixture for the content_stale roundtrip check.\n\n'
        f"Baseline token (not searched for): {uuid.uuid4().hex}\n"
        f'"""\n'
    )

    try:
        file_id = await client.file_sessions.upload_new(
            fixtures.session_id,
            original_content.encode("utf-8"),
            fixtures.project_id,
            relative_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(Status.FAILED, truncate(f"seed upload failed: {exc!r}"))
    if not file_id:
        return _outcome(Status.FAILED, "seed upload returned no file_id")

    index_outcome, _data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": fixtures.project_id},
        ok_reason="update_indexes completed after seeding the baseline file",
    )
    if index_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            index_outcome.status,
            f"skipped: baseline update_indexes did not succeed ({index_outcome.reason})",
        )

    open_outcome, open_data = await call_step_with_data(
        client,
        "universal_file_open",
        {"project_id": fixtures.project_id, "file_path": relative_path},
        ok_reason="universal_file_open completed for the seeded file",
    )
    if open_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            open_outcome.status,
            f"skipped: universal_file_open did not succeed ({open_outcome.reason})",
        )
    write_session_id = str((open_data or {}).get("session_id") or "")
    if not write_session_id:
        return _outcome(Status.FAILED, "universal_file_open returned no session_id")

    edit_outcome, _edit_data = await call_step_with_data(
        client,
        "universal_file_edit",
        {
            "project_id": fixtures.project_id,
            "session_id": write_session_id,
            "operations": [
                {
                    "type": "replace",
                    "start_line": 3,
                    "end_line": 3,
                    "new_lines": [f"Rewritten with live token: {token}"],
                }
            ],
        },
        ok_reason="universal_file_edit staged the content_stale-triggering change",
    )
    if edit_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            edit_outcome.status,
            f"skipped: universal_file_edit did not succeed ({edit_outcome.reason})",
        )

    write_outcome, _write_data = await call_step_with_data(
        client,
        "universal_file_write",
        {
            "project_id": fixtures.project_id,
            "session_id": write_session_id,
            "write_mode": "commit",
        },
        ok_reason="universal_file_write committed the content_stale-triggering change",
    )
    if write_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            write_outcome.status,
            f"skipped: universal_file_write did not succeed ({write_outcome.reason})",
        )

    try:
        await client.call_validated(
            "universal_file_close",
            {"project_id": fixtures.project_id, "session_id": write_session_id},
        )
    except Exception:  # noqa: BLE001 - cleanup only
        pass

    stale_outcome, stale_items, stale_job_id = await _search_for_token(
        client, fixtures.project_id, token
    )
    if stale_outcome.status is not Status.EXECUTED_OK:
        await _best_effort_close(client, stale_job_id)
        return _outcome(
            stale_outcome.status,
            f"post-write search call itself failed: {stale_outcome.reason}",
        )
    stale_flag = _content_stale_for_path(stale_items, relative_path)
    await _best_effort_close(client, stale_job_id)
    if stale_flag is None:
        return _outcome(
            Status.FAILED,
            f"post-write search found no hit for {relative_path} with token "
            f"{token} among {len(stale_items)} result(s) - cannot assert the flag",
        )
    if stale_flag is not True:
        return _outcome(
            Status.FAILED,
            f"post-write search hit for {relative_path} has content_stale="
            f"{stale_flag!r}, expected True (mark_file_content_stale did not fire "
            "on the universal_file_write commit path)",
        )

    reindex_outcome, _reindex_data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": fixtures.project_id},
        ok_reason="update_indexes completed after the content_stale-triggering write",
    )
    if reindex_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            reindex_outcome.status,
            f"post-write update_indexes did not succeed ({reindex_outcome.reason}) "
            "- content_stale left set, roundtrip incomplete",
        )

    clear_outcome, clear_items, clear_job_id = await _search_for_token(
        client, fixtures.project_id, token
    )
    if clear_outcome.status is not Status.EXECUTED_OK:
        await _best_effort_close(client, clear_job_id)
        return _outcome(
            clear_outcome.status,
            f"post-reindex search call itself failed: {clear_outcome.reason}",
        )
    clear_flag = _content_stale_for_path(clear_items, relative_path)
    await _best_effort_close(client, clear_job_id)
    if clear_flag is None:
        return _outcome(
            Status.FAILED,
            f"post-reindex search found no hit for {relative_path} among "
            f"{len(clear_items)} result(s) - cannot assert the flag cleared",
        )
    if clear_flag is not False:
        return _outcome(
            Status.FAILED,
            f"post-reindex search hit for {relative_path} still has "
            f"content_stale={clear_flag!r}, expected False (reindex-success clear "
            "did not fire)",
        )

    return _outcome(
        Status.EXECUTED_OK,
        f"{relative_path}: content_stale=true immediately after universal_file_write "
        "commit, content_stale=false after update_indexes - full roundtrip confirmed",
    )
