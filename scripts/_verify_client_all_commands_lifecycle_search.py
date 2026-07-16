"""
Ordered search-job lifecycle for the live-server all-commands verifier.

``search`` always runs paginated and returns a ``job_id`` immediately (fulltext
runs synchronously first; semantic/grep continue in the background) — the
remaining ``search_*`` commands all key off that ``job_id``. ``search_get_page``
for ``block_position=1`` can reject with ``BLOCK_NOT_READY`` if block 1 has not
been written yet, so this lifecycle polls ``search_get_status`` (its
``block_ready_count`` field) in a bounded loop before calling
``search_get_page``, rather than calling it once immediately after ``search``
returns.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import CommandOutcome, Status
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import (
    call_step,
    call_step_with_data,
    skip_outcome,
)

_DEPENDENT_NAMES = (
    "search_get_status",
    "search_get_page",
    "search_cancel",
    "search_close",
)

_BLOCK_WAIT_TIMEOUT_SECONDS = 30.0
_BLOCK_WAIT_INTERVAL_SECONDS = 1.0


async def _wait_for_first_block(
    client: CodeAnalysisAsyncClient, job_id: str
) -> CommandOutcome:
    """Poll ``search_get_status`` until block 1 is ready or the job stops running.

    Args:
        client: Connected async client.
        job_id: The search job id returned by ``search``.

    Returns:
        The ``search_get_status`` outcome from the final poll (the one used to
        decide whether to call ``search_get_page``).
    """
    deadline = time.monotonic() + _BLOCK_WAIT_TIMEOUT_SECONDS
    outcome: Optional[CommandOutcome] = None
    data: Optional[Dict[str, Any]] = None
    while True:
        outcome, data = await call_step_with_data(
            client, "search_get_status", {"job_id": job_id}
        )
        if outcome.status is not Status.EXECUTED_OK:
            return outcome
        payload = data or {}
        block_ready_count = payload.get("block_ready_count") or 0
        status = str(payload.get("status") or "").lower()
        if block_ready_count >= 1 or status != "running":
            return outcome
        if time.monotonic() >= deadline:
            return outcome
        await asyncio.sleep(_BLOCK_WAIT_INTERVAL_SECONDS)


async def run_search_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run ``search`` -> status -> page -> cancel -> close as one job lifecycle.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    outcomes: Dict[str, CommandOutcome] = {}

    search_outcome, search_data = await call_step_with_data(
        client,
        "search",
        {"project_id": fixtures.project_id, "query": "Sample"},
        ok_reason="search job started against the disposable project",
    )
    outcomes["search"] = search_outcome
    job_id = str((search_data or {}).get("job_id") or "").strip()

    if not job_id:
        for name in _DEPENDENT_NAMES:
            outcomes[name] = skip_outcome(
                name,
                "skipped: search did not return a job_id",
                status=search_outcome.status,
            )
        return outcomes

    status_outcome = await _wait_for_first_block(client, job_id)
    outcomes["search_get_status"] = status_outcome
    if status_outcome.status is Status.EXECUTED_OK:
        outcomes["search_get_page"] = await call_step(
            client, "search_get_page", {"job_id": job_id, "block_position": 1}
        )
    else:
        outcomes["search_get_page"] = skip_outcome(
            "search_get_page",
            "skipped: search_get_status never succeeded during the block-1 wait",
            status=status_outcome.status,
        )
    outcomes["search_cancel"] = await call_step(
        client,
        "search_cancel",
        {"job_id": job_id},
        ok_reason="search job cancelled (or already finished)",
    )
    outcomes["search_close"] = await call_step(
        client,
        "search_close",
        {"job_id": job_id},
        ok_reason="search job closed",
    )
    return outcomes
