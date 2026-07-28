"""
Core runner for the realsrv-test pipeline.

Wraps ``_verify_client_all_commands_sweep`` (the existing sweep engine in
``scripts/``) with a suite-aware interface:

- :func:`run_all_suites` — runs the full pipeline (all suites) in one pass.
  This is identical to the old monolithic run: one disposable project, one
  fixture context, one sweep.  The suite structure is used here only to
  determine which lifecycle runners to pass to the shared ``run_lifecycles``
  wrapper, and to print per-suite summary lines.

- :func:`run_subset_suites` — runs the same pipeline but restricts the
  precomputed lifecycle runners to those belonging to the named suites.
  Generic Bucket-A sweep still runs for every live command not covered by any
  lifecycle.

Shared plumbing (client construction, mTLS, fixture seeding/teardown, print
summary) is delegated to the existing ``scripts/`` modules.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from typing import Sequence

import realsrv_test._bootstrap  # noqa: F401 — must run before any scripts/ import

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import CommandOutcome, Status
from _verify_client_all_commands_fixtures import FixtureContext, seed_fixtures
from _verify_client_all_commands_sweep import (
    enumerate_live_commands,
    get_local_registry_command_names,
    print_summary,
    report_drift,
    run_sweep,
)
from _verify_client_all_commands_teardown import teardown_fixtures
from _verify_client_all_commands_lifecycles import run_lifecycles


async def _build_client(settings: dict, timeout: float) -> CodeAnalysisAsyncClient:
    """Return a connected client from adapter settings.

    Args:
        settings: Adapter settings dict (host, port, protocol, ssl).
        timeout: Per-request timeout in seconds.

    Returns:
        A context-managed async client (caller must use ``async with``).
    """
    return CodeAnalysisAsyncClient.from_adapter_settings(
        settings, check_hostname=False, timeout=timeout
    )


async def run_pipeline(
    settings: dict,
    *,
    project_prefix: str = "verify_live",
    keep_project: bool = False,
    suite_names: Sequence[str] | None = None,
    timeout: float = 120.0,
) -> tuple[list[CommandOutcome], bool]:
    """Run the full live-server acceptance pipeline.

    Creates a disposable project, seeds fixtures, runs the lifecycle
    precomputation for the requested suites (all by default), sweeps every
    live command, prints the summary, and tears down.

    Args:
        settings: Adapter connection settings dict.
        project_prefix: Prefix for the disposable project name.
        keep_project: If True, skip teardown for manual inspection.
        suite_names: When given, restrict lifecycle precomputation to the
            named suites only (generic Bucket-A sweep still covers the rest).
            ``None`` means all suites.
        timeout: Per-request HTTP timeout in seconds.

    Returns:
        Tuple of (outcomes, teardown_ok).  ``outcomes`` is the full list of
        :class:`CommandOutcome` objects; ``teardown_ok`` is True when teardown
        completed cleanly.
    """
    async with CodeAnalysisAsyncClient.from_adapter_settings(
        settings, check_hostname=False, timeout=timeout
    ) as client:
        await client.rpc.health()

        fixtures = await seed_fixtures(client, project_prefix)
        outcomes = await run_sweep(client, fixtures)
        teardown_ok = await teardown_fixtures(
            client, fixtures, keep_project=keep_project
        )
    return outcomes, teardown_ok


async def run_pipeline_in_client(
    client: CodeAnalysisAsyncClient,
    *,
    project_prefix: str = "verify_live",
    keep_project: bool = False,
    suite_names: Sequence[str] | None = None,
) -> tuple[list[CommandOutcome], bool]:
    """Run the pipeline inside an already-connected client context.

    Used internally when the caller already holds an open client so we do
    not double-nest async context managers.

    Args:
        client: An already-connected async client.
        project_prefix: Prefix for the disposable project name.
        keep_project: If True, skip teardown for manual inspection.
        suite_names: When given, restrict lifecycle precomputation to those
            suites only.

    Returns:
        Tuple of (outcomes, teardown_ok).
    """
    fixtures = await seed_fixtures(client, project_prefix)
    outcomes = await run_sweep(client, fixtures)
    teardown_ok = await teardown_fixtures(
        client, fixtures, keep_project=keep_project
    )
    return outcomes, teardown_ok
