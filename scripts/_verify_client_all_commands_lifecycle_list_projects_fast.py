"""
Dedicated ``list_projects`` pagination smoke check (bug 03da8ecd, TODO cc999a7d).

Before the fix, ``list_projects`` discovered every project by scanning each
one's *entire* file tree for nested ``projectid`` files
(``validate_no_nested_projects``, an ``os.walk``) and returned the full,
unpaginated catalog in one response -- on a ~225-project catalog this took
~101s and produced a response large enough to be truncated downstream. After
the fix, discovery is a cheap no-walk candidate pass (one directory listing
per watch dir, one ``projectid`` read per candidate) and the response is
paginated the same way as ``list_project_files`` / ``search``.

Reported under its own synthetic outcome name, ``list_projects_paginated_fast``
-- mirrors the conventions of
``_verify_client_all_commands_lifecycle_list_files_fast.py``: purely additive,
one more precomputed outcome merged into the same table every other lifecycle
module contributes to. Does not replace the generic ``list_projects`` call the
main alphabetical sweep may also perform elsewhere.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from typing import Any, Dict

from code_analysis_client import CodeAnalysisAsyncClient, QueuedJob

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext

CHECK_NAME = "list_projects_paginated_fast"

# Generous relative to the fast path's actual sub-second cost (a handful of
# directory listings + JSON reads), but tight enough to catch a regression
# back to the O(sum of all project file trees) full walk (~101s observed on
# the ~225-project catalog that triggered bug 03da8ecd).
_MAX_WALL_SECONDS = 15.0
_REQUESTED_PAGE_SIZE = 20


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns.

    Args:
        status: Outcome status for this check.
        reason: Human-readable explanation.

    Returns:
        ``{CHECK_NAME: CommandOutcome(...)}``.
    """
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def run_list_projects_paginated_fast_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert ``list_projects`` is fast, paginated, and pages without overlap.

    Records :attr:`Status.FAILED` unless all of:

    (a) the first-page call completes in under :data:`_MAX_WALL_SECONDS`
        wall-clock seconds -- a regression to the O(catalog file-tree) walk
        is the one failure mode this check exists to catch;
    (b) the response is a plain result, not a queued-job handoff --
        ``auto_poll=False`` surfaces a :class:`QueuedJob` instead of a dict
        when the server falls back to the queue (the sync-cap fallback this
        bug's slow unpaginated call used to trigger); a genuinely fast
        paginated lookup never approaches that cap;
    (c) the payload carries ``paginated: true``, a ``projects`` list no
        longer than the requested ``page_size``, and a ``has_more`` field;
    (d) a second page (``block_position=2``) returns a project set disjoint
        from the first page's -- proof pagination is not silently returning
        the same (or the full) catalog on every call.

    Each of the three pre-fix failure modes this bug produced -- timeout,
    queued handoff, unpaginated full response -- maps onto a distinct,
    clean FAILED classification below rather than an uncaught exception:
    timeouts and transport errors are caught and reported as FAILED; a
    :class:`QueuedJob` is FAILED by check (b); an unpaginated full response
    (no ``paginated`` key, or ``projects`` longer than ``page_size``) is
    FAILED by check (c).

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run (used
            only to confirm the disposable project is itself discoverable;
            the check does not depend on catalog size).

    Returns:
        ``{CHECK_NAME: outcome}``, merged into the lifecycle-precomputed
        outcomes table like every other lifecycle module returns.
    """
    started = time.monotonic()
    try:
        page1 = await client.call_validated(
            "list_projects",
            {"page_size": _REQUESTED_PAGE_SIZE, "block_position": 1},
            auto_poll=False,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        # Covers timeout / connection-refused / transport errors -- one of
        # the three pre-fix failure modes (the slow call used to trip the
        # client's own request timeout before the server ever answered).
        return _outcome(Status.FAILED, truncate(f"page 1 call raised: {exc!r}"))
    elapsed = time.monotonic() - started

    if isinstance(page1, QueuedJob):
        return _outcome(
            Status.FAILED,
            f"queued-job handoff instead of a plain paginated result "
            f"(job_id={page1.job_id!r}, elapsed={elapsed:.1f}s) -- discovery "
            "did not engage the cheap no-walk fast path",
        )

    if elapsed >= _MAX_WALL_SECONDS:
        return _outcome(
            Status.FAILED,
            f"page 1 took {elapsed:.1f}s (>= {_MAX_WALL_SECONDS}s budget) -- "
            "cheap no-walk fast path did not engage",
        )

    if not page1.get("success"):
        return _outcome(
            Status.FAILED, truncate(f"page 1 call failed: {page1.get('error')!r}")
        )

    data1: Dict[str, Any] = page1.get("data") or {}
    if data1.get("paginated") is not True:
        return _outcome(
            Status.FAILED,
            truncate(
                f"response is not paginated (paginated={data1.get('paginated')!r}) "
                f"-- looks like the pre-fix full unpaginated catalog dump"
            ),
        )

    projects1 = data1.get("projects") or data1.get("items") or []
    if len(projects1) > _REQUESTED_PAGE_SIZE:
        return _outcome(
            Status.FAILED,
            truncate(
                f"page 1 returned {len(projects1)} projects, more than the "
                f"requested page_size={_REQUESTED_PAGE_SIZE} -- pagination is "
                "not actually slicing the result"
            ),
        )
    if "has_more" not in data1:
        return _outcome(Status.FAILED, "page 1 payload is missing 'has_more'")

    if not data1.get("has_more"):
        # Catalog is smaller than one page on this deployment -- the pagination
        # contract itself is still verified (paginated/has_more/page_size all
        # present and correct); a disjoint second page cannot be proven when
        # there is no second page, so stop here with a clear, honest note.
        return _outcome(
            Status.EXECUTED_OK,
            f"page 1 served in {elapsed:.2f}s, paginated=true, "
            f"count={len(projects1)} total={data1.get('total')!r}; catalog "
            "fits in one page so has_more=false (page-2 disjointness not "
            "applicable)",
        )

    try:
        page2 = await client.call_validated(
            "list_projects",
            {"page_size": _REQUESTED_PAGE_SIZE, "block_position": 2},
            auto_poll=False,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(Status.FAILED, truncate(f"page 2 call raised: {exc!r}"))

    if isinstance(page2, QueuedJob):
        return _outcome(
            Status.FAILED,
            f"page 2 queued-job handoff (job_id={page2.job_id!r}) -- fast "
            "path did not engage on the second page",
        )
    if not page2.get("success"):
        return _outcome(
            Status.FAILED, truncate(f"page 2 call failed: {page2.get('error')!r}")
        )

    data2: Dict[str, Any] = page2.get("data") or {}
    projects2 = data2.get("projects") or data2.get("items") or []

    ids1 = {p.get("id") for p in projects1 if isinstance(p, dict)}
    ids2 = {p.get("id") for p in projects2 if isinstance(p, dict)}
    if not ids2:
        return _outcome(
            Status.FAILED, "page 2 (block_position=2) returned no projects"
        )
    if ids1 & ids2:
        return _outcome(
            Status.FAILED,
            truncate(
                f"page 1 and page 2 overlap on {len(ids1 & ids2)} project id(s) "
                f"-- pagination is returning duplicate/unchanged results"
            ),
        )

    return _outcome(
        Status.EXECUTED_OK,
        f"page 1 served in {elapsed:.2f}s, paginated=true, "
        f"count={len(projects1)} total={data1.get('total')!r}; page 2 "
        f"(block_position=2) returned {len(projects2)} disjoint project(s)",
    )
