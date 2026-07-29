"""
API-surface smoke checks for three command-surface TODOs (1b6cc124, 9c2018a3,
a7091850): ``get_ast`` bounded pagination + node projection, ``read_only_batch``
paginated inline retrieval, and ``get_file_lines`` removal.

Each check is reported under its own synthetic outcome name, mirroring the
conventions of ``realsrv_test.core.lifecycle_list_projects_fast.py`` /
``lifecycle_list_files_fast.py``: purely additive, one more precomputed
outcome merged into the same table every other lifecycle module contributes
to. None of the three replaces the generic alphabetical sweep's own call to
``get_ast`` / ``read_only_batch`` elsewhere.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from code_analysis_client import CodeAnalysisAsyncClient, QueuedJob

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME_GET_AST_PAGINATION = "get_ast_paginated_node_listing"
CHECK_NAME_READ_ONLY_BATCH_PAGINATION = "read_only_batch_paginated_inline"
CHECK_NAME_GET_FILE_LINES_ABSENT = "get_file_lines_absent_from_catalog"


def _outcome(
    check_name: str, status: Status, reason: str
) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns.

    Args:
        check_name: Synthetic outcome name for this check.
        status: Outcome status for this check.
        reason: Human-readable explanation.

    Returns:
        ``{check_name: CommandOutcome(...)}``.
    """
    return {check_name: CommandOutcome(check_name, Bucket.BUCKET_A, status, reason)}


async def run_get_ast_pagination_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert ``get_ast`` honors bounded pagination and node-kind projection (TODO 1b6cc124).

    Requests page 1 with ``page_size=1`` and ``node_types=["FunctionDef"]``
    against the seeded ``.py`` fixture (defines one module-level function and
    one method -- both ``FunctionDef`` nodes). Records :attr:`Status.FAILED`
    unless the response is paginated, bounded to the requested page size, and
    every returned node matches the requested node-kind projection.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_GET_AST_PAGINATION: outcome}``.
    """
    if not fixtures.py_file_path:
        return _outcome(
            CHECK_NAME_GET_AST_PAGINATION,
            Status.EXPECTED_ERROR,
            "skipped: seeded .py fixture file_path unavailable",
        )

    try:
        page1 = await client.call_validated(
            "get_ast",
            {
                "project_id": fixtures.project_id,
                "file_path": fixtures.py_file_path,
                "node_types": ["FunctionDef"],
                "page_size": 1,
                "block_position": 1,
            },
            auto_poll=False,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        # Today (pre-fix): get_ast's schema has no page_size/node_types
        # properties (additionalProperties: false) -- client-side schema
        # validation rejects this call before it ever reaches the server.
        return _outcome(
            CHECK_NAME_GET_AST_PAGINATION,
            Status.FAILED,
            truncate(f"paginated/projected call raised: {exc!r}"),
        )

    if isinstance(page1, QueuedJob):
        return _outcome(
            CHECK_NAME_GET_AST_PAGINATION,
            Status.FAILED,
            f"queued-job handoff instead of a plain paginated result "
            f"(job_id={page1.job_id!r})",
        )
    if not page1.get("success"):
        return _outcome(
            CHECK_NAME_GET_AST_PAGINATION,
            Status.FAILED,
            truncate(f"call failed: {page1.get('error')!r}"),
        )

    data1: Dict[str, Any] = page1.get("data") or {}
    if data1.get("paginated") is not True:
        return _outcome(
            CHECK_NAME_GET_AST_PAGINATION,
            Status.FAILED,
            truncate(
                f"response is not paginated (paginated={data1.get('paginated')!r}) "
                "-- looks like the unbounded whole-tree ast payload"
            ),
        )

    nodes1 = data1.get("nodes") or data1.get("items") or []
    if len(nodes1) > 1:
        return _outcome(
            CHECK_NAME_GET_AST_PAGINATION,
            Status.FAILED,
            truncate(
                f"page 1 returned {len(nodes1)} nodes, more than the requested "
                "page_size=1 -- pagination is not actually slicing the result"
            ),
        )
    if "has_more" not in data1 or "total" not in data1:
        return _outcome(
            CHECK_NAME_GET_AST_PAGINATION,
            Status.FAILED,
            "page 1 payload is missing 'has_more'/'total'",
        )
    bad_kinds = [
        n.get("node_type") for n in nodes1 if n.get("node_type") != "FunctionDef"
    ]
    if bad_kinds:
        return _outcome(
            CHECK_NAME_GET_AST_PAGINATION,
            Status.FAILED,
            truncate(
                f"node_types=['FunctionDef'] projection not honored: {bad_kinds!r}"
            ),
        )

    return _outcome(
        CHECK_NAME_GET_AST_PAGINATION,
        Status.EXECUTED_OK,
        f"page 1 paginated=true, count={len(nodes1)} total={data1.get('total')!r} "
        f"has_more={data1.get('has_more')!r}, node projection honored",
    )


async def run_read_only_batch_pagination_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert ``read_only_batch`` supports paginated inline retrieval (TODO 9c2018a3).

    Runs 3 whitelisted read-only invocations with ``page_size=1``, paging
    through all 3 result pages inline (never touching the filesystem).
    Records :attr:`Status.FAILED` unless every page is bounded, ``inline``
    stays true throughout, and the 3 pages together cover every invocation
    exactly once (in order).

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_READ_ONLY_BATCH_PAGINATION: outcome}``.
    """
    if not fixtures.py_file_path:
        return _outcome(
            CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
            Status.EXPECTED_ERROR,
            "skipped: seeded .py fixture file_path unavailable",
        )

    invocations = [
        {"command": "get_class_hierarchy", "params": {"project_id": fixtures.project_id}},
        {"command": "list_code_entities", "params": {"project_id": fixtures.project_id}},
        {
            "command": "universal_file_preview",
            "params": {
                "project_id": fixtures.project_id,
                "file_path": fixtures.py_file_path,
            },
        },
    ]

    seen_commands: list[str] = []
    for block_position in (1, 2, 3):
        try:
            page = await client.call_validated(
                "read_only_batch",
                {
                    "invocations": invocations,
                    "page_size": 1,
                    "block_position": block_position,
                },
                auto_poll=False,
            )
        except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
            # Today (pre-fix): read_only_batch's schema has no page_size
            # property (additionalProperties: false) -- client-side schema
            # validation rejects this call before it ever reaches the server.
            return _outcome(
                CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
                Status.FAILED,
                truncate(f"block_position={block_position} call raised: {exc!r}"),
            )
        if isinstance(page, QueuedJob):
            return _outcome(
                CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
                Status.FAILED,
                f"block_position={block_position} queued-job handoff instead of "
                f"a plain paginated inline result (job_id={page.job_id!r})",
            )
        if not page.get("success"):
            return _outcome(
                CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
                Status.FAILED,
                truncate(
                    f"block_position={block_position} call failed: {page.get('error')!r}"
                ),
            )
        data: Dict[str, Any] = page.get("data") or {}
        if data.get("inline") is not True or data.get("paginated") is not True:
            return _outcome(
                CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
                Status.FAILED,
                truncate(
                    f"block_position={block_position} not inline+paginated "
                    f"(inline={data.get('inline')!r} paginated={data.get('paginated')!r}) "
                    "-- looks like the pre-fix inline-or-file-only behavior"
                ),
            )
        items = data.get("items") or data.get("results") or []
        if len(items) > 1:
            return _outcome(
                CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
                Status.FAILED,
                truncate(
                    f"block_position={block_position} returned {len(items)} "
                    "results, more than the requested page_size=1"
                ),
            )
        if "output_file" in data:
            return _outcome(
                CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
                Status.FAILED,
                "paginated inline retrieval still touched the filesystem "
                "(output_file present)",
            )
        seen_commands.extend(
            entry.get("command", "") for entry in items if isinstance(entry, dict)
        )

    expected_commands = [inv["command"] for inv in invocations]
    if seen_commands != expected_commands:
        return _outcome(
            CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
            Status.FAILED,
            truncate(
                f"pages did not cover all 3 invocations in order: "
                f"expected {expected_commands!r}, got {seen_commands!r}"
            ),
        )

    return _outcome(
        CHECK_NAME_READ_ONLY_BATCH_PAGINATION,
        Status.EXECUTED_OK,
        f"3 pages of page_size=1 covered all invocations in order inline, "
        f"never touching the filesystem: {seen_commands!r}",
    )


async def run_get_file_lines_absent_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert ``get_file_lines`` is absent from the live command catalog (TODO a7091850).

    Confirms the command's schema cannot be fetched (equivalent to
    ``realsrv_test.core.classifiers.check_removed_command`` for a
    ``REMOVED_COMMANDS``-listed name, but self-contained here so this suite
    also RED/GREENs the removal directly without depending on the sweep
    engine having reached it).

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run
            (unused; kept for lifecycle-runner signature parity).

    Returns:
        ``{CHECK_NAME_GET_FILE_LINES_ABSENT: outcome}``.
    """
    del fixtures  # not needed: this check is catalog-only, not project-scoped
    try:
        await client.get_command_schema("get_file_lines", refresh=True)
    except Exception as exc:  # noqa: BLE001 - absence surfaces as an exception
        return _outcome(
            CHECK_NAME_GET_FILE_LINES_ABSENT,
            Status.EXECUTED_OK,
            f"get_file_lines schema fetch failed as expected (absent): {truncate(repr(exc))}",
        )
    return _outcome(
        CHECK_NAME_GET_FILE_LINES_ABSENT,
        Status.FAILED,
        "get_file_lines schema fetch succeeded -- command is still live-registered",
    )
