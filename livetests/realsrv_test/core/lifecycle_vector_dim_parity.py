"""
Live embedding_vec dimension-parity guard (bug f4dd4039).

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

This check is deliberately MINIMAL and READ-ONLY -- unlike that test-suite
coverage, it cannot open a throwaway schema or force a dimension change
against the live server without disturbing real data, so it does not
reproduce the defect end-to-end. There is also no live command that exposes
the server's configured ``vector_dim`` or the column's declared dimension
for a direct parity assertion (no ``config`` command return field for it as
of this writing), so this check cannot literally compare "configured dim"
against "declared column dim" from outside the server process.

Fallback design (explicitly sanctioned for exactly this gap): target the
disposable, already-fully-vectorized project
``fc6a83b7-07a8-4ce2-8548-1de340168d01`` and assert ``check_vectors`` reports
``vectorization_percentage == 100.0``. This project was fully vectorized at
a known-good dimension; a future dimension-mismatch regression (a mismatched
column dimension causing embedding writes to fail, or a botched retype that
discards embeddings without requeuing them) would freeze or drop that
percentage below 100.0 the next time chunks are re-chunked or the column is
touched. This is a WEAKER signal than the real-PG regression tests -- it can
only catch a live break that actually manifests against this one project's
current state, not every dimension-change path -- so it exists as a
production tripwire alongside the real-PG tests, not a replacement for them.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME = "vector_dim_parity_check_vectors_full"

# Disposable project used elsewhere in this pipeline as a known-fully-vectorized
# fixed target (not the pipeline's own per-run throwaway fixture project).
_TARGET_PROJECT_ID = "fc6a83b7-07a8-4ce2-8548-1de340168d01"


async def run_vector_dim_parity_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert a fixed, fully-vectorized project stays at 100% vectorized.

    Args:
        client: Connected async client.
        fixtures: Unused -- this check deliberately targets a real,
            pre-existing, fully-vectorized project instead of the pipeline's
            own disposable fixture project (see module docstring).

    Returns:
        ``{CHECK_NAME: outcome}`` -- single-entry map, like every check in
        this package.
    """
    try:
        resp = await client.call_validated(
            "check_vectors", {"project_id": _TARGET_PROJECT_ID}
        )
    except Exception as exc:  # noqa: BLE001 - one bad check must not abort the sweep
        return {
            CHECK_NAME: CommandOutcome(
                CHECK_NAME, Bucket.BUCKET_A, Status.FAILED, truncate(repr(exc))
            )
        }

    if resp.get("success") is not True:
        return {
            CHECK_NAME: CommandOutcome(
                CHECK_NAME,
                Bucket.BUCKET_A,
                Status.FAILED,
                f"check_vectors call did not succeed: {truncate(str(resp.get('error')))}",
            )
        }

    data = resp.get("data") or {}
    pct = data.get("vectorization_percentage")
    reason = (
        f"project={_TARGET_PROJECT_ID} vectorization_percentage={pct!r} "
        f"(expected 100.0; a dimension-parity break freezes/drops this)"
    )
    if pct == 100.0:
        status = Status.EXECUTED_OK
    else:
        status = Status.FAILED
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}
