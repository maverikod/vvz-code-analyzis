"""
Live embedding_vec dimension-parity guard (bug f4dd4039), self-contained rewrite
(1.6.113 hardening pass, item C).

Registered in ``realsrv_test.suites.s22_vector_dim_parity`` (SUITE_NAME
"vectorparity").

Root cause under test: ``_ensure_pgvector_embedding_column`` used to only ADD
``code_chunks.embedding_vec`` when the column was missing -- a changed
configured ``vector_dim`` never reached an EXISTING column. On the live
server this bricked all embedding writes with ``psycopg.errors.DataException:
expected 384 dimensions, not 1024`` until the DB was fixed by hand (see
``code_analysis/core/database_driver_pkg/drivers/postgres_migrations.py``
and ``tests/test_postgres_schema_bootstrap_real_pg.py`` for the fix and its
unit-level regression coverage against a real disposable PostgreSQL schema).

Before this pass, this check targeted a hardcoded fixed project id
(``fc6a83b7-07a8-4ce2-8548-1de340168d01``) that had to already exist,
already be fully vectorized, and never be touched by anything else -- a
shared, brittle external dependency the check had no control over. This
rewrite makes the check self-contained: it creates its own small isolated
throwaway project (8 documented functions, well under the embed service's
20-text batch cap so this check exercises normal vectorization, not the
batch-cap path covered by ``lifecycle_vectorization_batch_cap.py``), drives
``update_indexes`` + the real vectorization worker against it, and polls
``check_vectors`` for full vectorization -- the same isolated-project,
fixture-generation, and polling machinery ``lifecycle_vectorization_batch_
cap.py`` uses, now shared via ``realsrv_test.core.vectorization_fixture_
common`` so both lifecycles stay in sync instead of drifting apart. A
mismatched column dimension or a botched retype that discards embeddings
without requeuing them would keep this project below 100% vectorized
indefinitely, which is exactly what this check asserts against.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_common import call_step
from realsrv_test.core.vectorization_fixture_common import (
    create_isolated_vectorization_project,
    poll_check_vectors_fully_vectorized,
    start_and_verify_vectorization_worker,
    stop_vectorization_worker_if_started,
    teardown_vectorization_project,
    upload_fixture_file,
)

CHECK_NAME = "vector_dim_parity_check_vectors_full"

# Small and deliberately well under the embed service's default 20-text batch
# cap -- this check exercises the normal (non-batched-oversized) vectorization
# path; the batch-cap path itself is covered by
# ``lifecycle_vectorization_batch_cap.py`` (bug 16b1abbe).
_TOTAL_FUNCTIONS = 8

_RELATIVE_PATH = "vector_dim_parity_fixture.py"

_POLL_TIMEOUT_SECONDS = 120.0
_POLL_INTERVAL_SECONDS = 5.0

# Best-effort extra signal, not a hard requirement (see module docstring / the
# _semantic_search_hit docstring below): the fixture's first function is a
# stable, deterministic query term scoped to this run's own isolated project.
_SEMANTIC_SEARCH_QUERY = "vectorization_fixture_fn_0"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map this lifecycle returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


async def _semantic_search_hit(
    client: CodeAnalysisAsyncClient, project_id: str
) -> str:
    """Best-effort semantic-search-finds-the-fixture assertion.

    Optional signal only: a fully-vectorized project SHOULD be semantically
    searchable for its own content, but search-index visibility can lag
    embedding completion by a short window, and this check's primary verdict
    is already the ``check_vectors`` percentage. A miss here is reported in
    the reason text but never turns an otherwise-EXECUTED_OK result into a
    failure -- see the module docstring.

    Args:
        client: Connected async client.
        project_id: Isolated project to search within.

    Returns:
        Human-readable fragment describing the search outcome, for inclusion
        in the check's reason text.
    """
    job_id = ""
    try:
        resp = await client.call_validated(
            "search",
            {
                "project_id": project_id,
                "query": _SEMANTIC_SEARCH_QUERY,
                "enable_semantic": True,
                "enable_grep": False,
            },
        )
        if resp.get("success") is not True:
            return f"semantic search call did not succeed: {truncate(str(resp.get('error')))}"
        data = resp.get("data") or {}
        job_id = str(data.get("job_id") or "")
        items = data.get("items")
        if not isinstance(items, list):
            items = []
        hit = _fixture_path_in_hits(items)
        return f"semantic search {'hit' if hit else 'MISS'} for {_RELATIVE_PATH!r} ({len(items)} item(s))"
    except Exception as exc:  # noqa: BLE001 - optional signal must not abort the check
        return f"semantic search raised {truncate(repr(exc))}"
    finally:
        if job_id:
            try:
                await client.call_validated("search_close", {"job_id": job_id})
            except Exception:  # noqa: BLE001 - cleanup only
                pass


def _fixture_path_in_hits(items: List[Any]) -> bool:
    """True if any search hit's path matches the uploaded fixture's relative path."""
    wanted = _RELATIVE_PATH
    wanted_suffix = "/" + wanted
    for row in items:
        if not isinstance(row, dict):
            continue
        candidate = str(
            row.get("file_path") or row.get("path") or row.get("relative_path") or ""
        ).replace("\\", "/")
        if candidate == wanted or candidate.endswith(wanted_suffix):
            return True
    return False


async def run_vector_dim_parity_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Vectorize a small isolated fixture project end-to-end and assert 100%.

    Args:
        client: Connected async client.
        fixtures: Unused -- this check creates its own isolated throwaway
            project instead of the pipeline's shared sweep fixture (see
            module docstring).

    Returns:
        ``{CHECK_NAME: outcome}`` -- single-entry map, like every check in
        this package.
    """
    project_id, _project_root, project_name, create_status, create_reason = (
        await create_isolated_vectorization_project(
            client,
            name_prefix="verify_vecdimparity",
            description="isolated disposable project for the dimension-parity check (bug f4dd4039)",
        )
    )
    if create_status is not Status.EXECUTED_OK:
        return _outcome(Status.FAILED, create_reason)
    assert project_id is not None

    started_fresh = False
    try:
        file_id, upload_status, upload_reason = await upload_fixture_file(
            client,
            project_id=project_id,
            relative_path=_RELATIVE_PATH,
            total_functions=_TOTAL_FUNCTIONS,
            session_comment="vector dimension-parity check (bug f4dd4039)",
        )
        if upload_status is not Status.EXECUTED_OK:
            return _outcome(Status.FAILED, upload_reason)
        assert file_id is not None

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

        start_status, start_reason, started_fresh = (
            await start_and_verify_vectorization_worker(client, project_id)
        )
        if start_status is not Status.EXECUTED_OK:
            return _outcome(start_status, start_reason)

        try:
            poll_status, poll_reason, _final_data = await poll_check_vectors_fully_vectorized(
                client,
                project_id,
                timeout_seconds=_POLL_TIMEOUT_SECONDS,
                interval_seconds=_POLL_INTERVAL_SECONDS,
            )
        finally:
            await stop_vectorization_worker_if_started(client, started_fresh)

        if poll_status is not Status.EXECUTED_OK:
            return _outcome(
                Status.FAILED,
                f"{_RELATIVE_PATH}: not fully vectorized within "
                f"{_POLL_TIMEOUT_SECONDS:.0f}s ({poll_reason}) -- a dimension-parity "
                "break freezes/drops the vectorized percentage",
            )

        search_reason = await _semantic_search_hit(client, project_id)
        return _outcome(
            Status.EXECUTED_OK,
            f"{_RELATIVE_PATH}: fully vectorized ({poll_reason}); {search_reason}",
        )
    finally:
        # bug d5835fbf: this called a non-existent "delete_project" command,
        # silently swallowed by the bare except below -- the isolated
        # disposable project was NEVER deleted by any run of this check
        # (same dead-call defect found and fixed in
        # lifecycle_indexer_correctness.py / lifecycle_vectorization_batch_cap.py).
        # Routed through the shared vectorization teardown helper instead.
        await teardown_vectorization_project(client, project_id, project_name)
