"""
Aggregator for every ordered command lifecycle used by the live-server verifier.

Runs each ``_verify_client_all_commands_lifecycle_*`` module once, before the
main alphabetical command sweep, and merges their ``{command_name:
CommandOutcome}`` maps into one precomputed table. ``classify_command``
(``_verify_client_all_commands_classifiers.py``) consults this table first, so
any command covered by a lifecycle is reported from its real, ordered
execution here rather than re-executed generically (and out of order) by the
main sweep loop.

``change_project_id`` is intentionally excluded — it is handled as a separate
deferred final step by ``_verify_client_all_commands_sweep.run_sweep`` because
it mutates ``fixtures.project_id`` and must run after every other command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_entities import run_entity_lifecycle
from _verify_client_all_commands_lifecycle_fs import run_fs_lifecycle
from _verify_client_all_commands_lifecycle_git import run_git_lifecycle
from _verify_client_all_commands_lifecycle_github import run_github_lifecycle
from _verify_client_all_commands_lifecycle_list_files_fast import (
    run_list_project_files_exact_path_fast_check,
)
from _verify_client_all_commands_lifecycle_queue import run_queue_lifecycle
from _verify_client_all_commands_lifecycle_search import run_search_lifecycle
from _verify_client_all_commands_lifecycle_session import run_session_lifecycle
from _verify_client_all_commands_lifecycle_transfer import run_transfer_lifecycle
from _verify_client_all_commands_lifecycle_workers import run_worker_lifecycle

_LIFECYCLE_RUNNERS = (
    run_session_lifecycle,
    run_transfer_lifecycle,
    run_search_lifecycle,
    run_git_lifecycle,
    run_github_lifecycle,
    run_entity_lifecycle,
    run_fs_lifecycle,
    run_worker_lifecycle,
    run_queue_lifecycle,
    run_list_project_files_exact_path_fast_check,
)


async def run_lifecycles(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run every ordered lifecycle once and merge their outcomes.

    A lifecycle module crashing outright (as opposed to one of its own steps
    failing, which each module already contains) is caught here so it cannot
    abort the remaining lifecycles or the sweep.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of every lifecycle-covered command name to its outcome, plus
        ``create_project`` credited from the fixture-setup phase.
    """
    outcomes: Dict[str, CommandOutcome] = {}
    for runner in _LIFECYCLE_RUNNERS:
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
