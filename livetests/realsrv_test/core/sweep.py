"""
Sweep engine for the live-server all-commands verifier.

Enumerates every command the live server currently exposes (via the ``help``
adapter command with no ``cmdname``), cross-checks that catalog against the
local in-process command registry for a drift report, then delegates each
command to ``realsrv_test.core.classifiers.classify_command`` and
prints a final summary/table.

The list of ordered lifecycle runners is NOT hardcoded here: it is passed in
by the caller, derived from the auto-discovered suite modules in
``realsrv_test.suites`` — that discovery is the single source of truth for
what runs.  (``realsrv_test.core.watcher_config_load_check`` is a deliberate
exception: a standalone CLI regression check with its own ~10s stall, never
part of a suite — see its module docstring.)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Awaitable, Callable, Dict, List, Sequence, Set

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.classifiers import classify_command
from realsrv_test.core.fixtures import FixtureContext
from realsrv_test.core.lifecycle_fs import run_change_project_id_last

# One ordered lifecycle: an async (client, fixtures) -> {command_name: outcome}.
LifecycleRunner = Callable[
    [CodeAnalysisAsyncClient, FixtureContext],
    Awaitable[Dict[str, CommandOutcome]],
]

# Executed last, outside the alphabetical loop, because it mutates
# fixtures.project_id — running it in alphabetical position would invalidate
# project_id for every command that sorts after "change_project_id".
_DEFERRED_LAST = ("change_project_id",)


async def run_lifecycles(
    client: CodeAnalysisAsyncClient,
    fixtures: FixtureContext,
    runners: Sequence[LifecycleRunner],
) -> Dict[str, CommandOutcome]:
    """Run the given ordered lifecycles once and merge their outcomes.

    A lifecycle crashing outright (as opposed to one of its own steps
    failing, which each module already contains) is caught here so it cannot
    abort the remaining lifecycles or the sweep.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.
        runners: Ordered lifecycle runners collected from the auto-discovered
            suite modules (``realsrv_test.suites``).

    Returns:
        Mapping of every lifecycle-covered command name to its outcome, plus
        ``create_project`` credited from the fixture-setup phase.
    """
    outcomes: Dict[str, CommandOutcome] = {}
    for runner in runners:
        try:
            outcomes.update(await runner(client, fixtures))
        except Exception as exc:  # noqa: BLE001 - one lifecycle must not abort the rest
            print(f"WARN  lifecycle {runner.__name__} crashed: {exc!r}")

    outcomes["create_project"] = CommandOutcome(
        "create_project",
        Bucket.BUCKET_A,
        Status.EXECUTED_OK,
        "executed during fixture setup (disposable project); not re-executed standalone",
    )
    return outcomes


async def run_suite_subset(
    client: CodeAnalysisAsyncClient,
    fixtures: FixtureContext,
    runners: Sequence[LifecycleRunner],
) -> List[CommandOutcome]:
    """Run only the given lifecycle runners — no generic alphabetical sweep.

    Used by the CLI's positional suite selection: a subset run exercises only
    the named suites' ordered lifecycles (plus the fixture-credited
    ``create_project``), skipping the full live-catalog sweep that a no-args
    run performs.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.
        runners: Lifecycle runners from the selected suites only.

    Returns:
        One :class:`CommandOutcome` per command those lifecycles covered.
    """
    precomputed = await run_lifecycles(client, fixtures, runners)
    return [precomputed[name] for name in sorted(precomputed)]


async def enumerate_live_commands(client: CodeAnalysisAsyncClient) -> Dict[str, str]:
    """Fetch the full live command catalog via ``help`` with no ``cmdname``.

    Args:
        client: Connected async client.

    Returns:
        Mapping of command name to its one-line description.

    Raises:
        RuntimeError: If the ``help`` catalog call fails or has an unexpected shape.
    """
    resp = await client.rpc.help()
    if not resp.get("success"):
        raise RuntimeError(f"help() catalog fetch failed: {resp!r}")
    data = resp.get("data") or {}
    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise RuntimeError(f"help() response missing 'commands' map: {data!r}")
    return commands


def get_local_registry_command_names() -> Set[str]:
    """Build the ground-truth local in-process command registry name set.

    Mirrors the pattern used by ``scripts/command_inventory.py``.

    Returns:
        Set of every command name registered in a fresh local registry.
    """
    from mcp_proxy_adapter.commands.command_registry import CommandRegistry
    from code_analysis.hooks import register_code_analysis_commands

    reg = CommandRegistry()
    register_code_analysis_commands(reg)
    return set(reg._commands.keys())


def report_drift(live_names: Set[str], local_names: Set[str]) -> None:
    """Print any mismatch between the live catalog and the local registry.

    Args:
        live_names: Command names reported by the live server.
        local_names: Command names in the local in-process registry.
    """
    only_live = sorted(live_names - local_names)
    only_local = sorted(local_names - live_names)
    if only_live:
        print(f"DRIFT  live-only ({len(only_live)}): {only_live}")
    if only_local:
        print(f"DRIFT  local-only ({len(only_local)}): {only_local}")


async def run_sweep(
    client: CodeAnalysisAsyncClient,
    fixtures: FixtureContext,
    runners: Sequence[LifecycleRunner],
) -> List[CommandOutcome]:
    """Enumerate, drift-check, and classify every live command.

    Runs every ordered lifecycle once up front (see
    ``realsrv_test.core.sweep.run_lifecycles``) to build a
    precomputed outcomes table that ``classify_command`` consults first, then
    classifies every remaining live command in alphabetical order.
    ``change_project_id`` is deferred to run last (outside the alphabetical
    order) since it mutates ``fixtures.project_id``. As a completeness safety
    net, any live command name that still has no outcome after both passes
    (which should not happen — every branch below is wrapped to guarantee one
    outcome per name) is recorded as :attr:`Status.FAILED` so a dispatcher bug
    cannot silently drop a command from the matrix.

    This function does not print the per-command outcome table itself —
    :func:`print_summary` is the single place that prints the full matrix, so
    it appears exactly once in stdout. Only anomalies (drift, lifecycle
    crashes, dispatcher-missed commands) are printed here as they occur.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.
        runners: Ordered lifecycle runners collected from the auto-discovered
            suite modules (``realsrv_test.suites``) — the single source of
            execution truth for the lifecycle phase.

    Returns:
        One :class:`CommandOutcome` per live command name.
    """
    live_catalog = await enumerate_live_commands(client)
    live_names = set(live_catalog.keys())

    try:
        local_names = get_local_registry_command_names()
        report_drift(live_names, local_names)
    except Exception as exc:
        print(f"WARN  could not build local registry for drift check: {exc!r}")

    precomputed = await run_lifecycles(client, fixtures, runners)

    deferred = [name for name in _DEFERRED_LAST if name in live_names]
    ordered_names = sorted(live_names - set(deferred)) + deferred

    outcomes: List[CommandOutcome] = []
    for name in ordered_names:
        try:
            if name == "change_project_id":
                outcome = await run_change_project_id_last(client, fixtures)
            else:
                outcome = await classify_command(client, name, fixtures, precomputed)
        except (
            Exception
        ) as exc:  # a single command's classifier must never abort the sweep
            # Bucket.BUCKET_A fallback: a crashed classifier was almost always
            # attempting a project-scoped call, the most common path.
            outcome = CommandOutcome(
                name,
                Bucket.BUCKET_A,
                Status.FAILED,
                f"classifier crashed: {truncate(repr(exc))}",
            )
        outcomes.append(outcome)

    covered_names = {outcome.name for outcome in outcomes}
    for missing_name in sorted(live_names - covered_names):
        outcomes.append(
            CommandOutcome(
                missing_name,
                Bucket.BUCKET_A,
                Status.FAILED,
                "missing from the sweep matrix — dispatcher bug, never classified",
            )
        )
        print(f"MISSING command never classified: {missing_name}")

    # Synthetic lifecycle checks (e.g. list_project_files_exact_path_fast,
    # list_projects_paginated_fast) are precomputed by run_lifecycles but
    # name a check, not a live server command, so they never appear in
    # live_names and would otherwise be silently dropped here -- merge any
    # precomputed-only outcome not already covered so it is still printed
    # and still affects the FAILED exit code like every other outcome.
    for extra_name in sorted(set(precomputed) - covered_names):
        outcomes.append(precomputed[extra_name])
    return outcomes


def print_summary(outcomes: List[CommandOutcome]) -> int:
    """Print status counts and a full sorted outcome table.

    Args:
        outcomes: All outcomes collected by :func:`run_sweep`.

    Returns:
        Count of commands with :attr:`Status.FAILED` (used by the caller to
        decide the process exit code; expected-error and verify-only never
        affect it).
    """
    counts: Dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status.value] = counts.get(outcome.status.value, 0) + 1

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    for status_name in sorted(counts):
        print(f"  {status_name:16} {counts[status_name]}")

    print("-" * 100)
    print(f"{'STATUS':16} {'COMMAND':40} {'BUCKET':10} REASON")
    for outcome in sorted(outcomes, key=lambda o: (o.status.value, o.name)):
        print(
            f"{outcome.status.value:16} {outcome.name:40} {outcome.bucket.value:10} {outcome.reason}"
        )

    return sum(1 for outcome in outcomes if outcome.status is Status.FAILED)
