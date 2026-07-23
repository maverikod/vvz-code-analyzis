"""
Seeded-literal-token fulltext read-after-write race check (bug 67e50972 groundwork).

Groundwork only — this module does NOT claim bug 67e50972 fixed. It exists to
bisect the suspected race between a file write (``upload_new`` + ``update_indexes``)
and that same file becoming visible to ``fulltext_search`` immediately afterward:
seed a file whose content contains one freshly-generated, globally-unique token
(so a hit can only come from this run's own write, never a stale/leftover
index row), run ``update_indexes``, then IMMEDIATELY call
``search(query=<token>, enable_semantic=false, enable_grep=false)`` and check
for >=1 hit that includes the seeded path. If (and only if) that immediate
attempt comes back empty, retry once more after a fixed delay with a brand
new ``search`` call for the same token, and report which attempt (if either)
found the seeded file — that split is the bisection signal an integrator
needs to confirm or rule out the race, not a verdict on the underlying bug.

Conventions follow ``_verify_client_all_commands_lifecycle_list_files_fast.py``
(a single-check, catalog-shaped module returning ``{CHECK_NAME: CommandOutcome}``,
not one of the ordered command lifecycles in
``_verify_client_all_commands_lifecycle_common.py``/``call_step_with_data``
reused directly here for the ``update_indexes`` step, but this module owns its
own ``search`` calls and result parsing since ``search``'s own response already
carries the first result block inline (see ``SearchMCPCommand.execute`` -
it blocks server-side for up to ``first_block_wait_seconds`` and returns
``items`` directly), so no extra ``search_get_status``/``search_get_page``
polling round-trip is needed to read the immediate result.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step_with_data

CHECK_NAME = "search_fulltext_seeded_literal_immediate"

# Fixed, deliberately short delay for the single diagnostic retry - long
# enough to clear a plausible async-indexing lag, short enough to keep the
# sweep fast when there is no race at all (the common case).
_RETRY_DELAY_SECONDS = 3.0


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


def _seeded_path_in_hits(items: List[Any], relative_path: str) -> bool:
    """True if any fulltext hit's file_path matches the seeded relative path."""
    wanted = relative_path.replace("\\", "/").lstrip("./")
    for row in items:
        if not isinstance(row, dict):
            continue
        candidate = str(
            row.get("file_path") or row.get("path") or row.get("relative_path") or ""
        ).replace("\\", "/").lstrip("./")
        if candidate == wanted:
            return True
    return False


async def _search_for_token(
    client: CodeAnalysisAsyncClient, project_id: str, token: str
) -> Tuple[CommandOutcome, List[Any], str]:
    """Run one fresh fulltext-only ``search`` job for ``token``.

    Returns:
        (outcome, items, job_id) - ``items`` is ``[]`` and ``job_id`` is ``""``
        when the call itself did not succeed.
    """
    outcome, data = await call_step_with_data(
        client,
        "search",
        {
            "project_id": project_id,
            "query": token,
            "enable_semantic": False,
            "enable_grep": False,
        },
        ok_reason="fulltext seeded-token search completed",
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


async def run_search_fulltext_seeded_literal_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Seed a unique-token file, index it, then race-check immediate fulltext visibility.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME: outcome}`` - :attr:`Status.EXECUTED_OK` only when the
        IMMEDIATE (attempt 1, no delay) search found the seeded file;
        :attr:`Status.FAILED` when attempt 1 missed but the delayed retry
        found it (race observed) or when neither attempt found it.
    """
    if not fixtures.session_id:
        return _outcome(
            Status.EXPECTED_ERROR, "skipped: no fixture session_id available"
        )

    token = f"verifyseeded{uuid.uuid4().hex}"
    relative_path = f"verify_seeded_{uuid.uuid4().hex[:8]}.py"
    content = (
        f'"""Seeded fixture for the fulltext read-after-write race check.\n\n'
        f"Unique token: {token}\n"
        f'"""\n'
    )

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

    index_outcome, _index_data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": fixtures.project_id},
        ok_reason="update_indexes completed after seeding the token file",
    )
    if index_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            index_outcome.status,
            f"skipped: update_indexes did not succeed ({index_outcome.reason})",
        )

    first_outcome, first_items, first_job_id = await _search_for_token(
        client, fixtures.project_id, token
    )
    if first_outcome.status is not Status.EXECUTED_OK:
        await _best_effort_close(client, first_job_id)
        return _outcome(
            first_outcome.status,
            f"attempt 1 (immediate) search call itself failed: {first_outcome.reason}",
        )

    if _seeded_path_in_hits(first_items, relative_path):
        await _best_effort_close(client, first_job_id)
        return _outcome(
            Status.EXECUTED_OK,
            f"attempt 1 (immediate, no delay) found the seeded token in "
            f"{relative_path} among {len(first_items)} hit(s) - no read-after-write "
            "race observed this run",
        )
    await _best_effort_close(client, first_job_id)

    await asyncio.sleep(_RETRY_DELAY_SECONDS)
    second_outcome, second_items, second_job_id = await _search_for_token(
        client, fixtures.project_id, token
    )
    await _best_effort_close(client, second_job_id)

    if second_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            Status.FAILED,
            f"attempt 1 (immediate) found 0 hits for the seeded token; the "
            f"{_RETRY_DELAY_SECONDS}s retry's search call itself then failed: "
            f"{second_outcome.reason}",
        )

    if _seeded_path_in_hits(second_items, relative_path):
        return _outcome(
            Status.FAILED,
            f"attempt 1 (immediate) found 0 hits for the seeded token in "
            f"{relative_path}; attempt 2 (after a {_RETRY_DELAY_SECONDS}s delay) "
            f"found it among {len(second_items)} hit(s) - read-after-write race "
            "bisected to bug 67e50972 (not fixed by this check; groundwork only)",
        )

    return _outcome(
        Status.FAILED,
        f"seeded token for {relative_path} never appeared in fulltext search "
        f"results across both attempts (immediate and after "
        f"{_RETRY_DELAY_SECONDS}s) - not necessarily the same race; investigate "
        "the indexing path separately",
    )
