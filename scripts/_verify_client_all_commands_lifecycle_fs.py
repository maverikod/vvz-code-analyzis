"""
Filesystem copy/move lifecycle and the deferred ``change_project_id`` step.

``fs_copy`` / ``fs_move`` operate on a throwaway copy of the seeded ``.py``
fixture, never the original — the original stays available (under its
original name) for every other command in the sweep that references
``fixtures.py_file_path`` generically. ``fs_remove`` is included in this
lifecycle's outcome table (targeting the throwaway moved copy) precisely so
the generic alphabetical Bucket A sweep never runs it against the primary
seeded file with the generic ``file_path`` provider — ``fs_remove`` sorts
alphabetically before many commands (``get_ast``, ``get_file_lines``,
``lint_code``, ...) that still need the primary fixture file to exist.

``change_project_id`` gets a real UUID4 and, on success, mutates
``fixtures.project_id`` in place so every later fixture use (including final
teardown) targets the renamed project. The sweep engine
(``_verify_client_all_commands_sweep.run_sweep``) must call
:func:`run_change_project_id_last` after every other command has run, not as
part of the precomputed lifecycle map, since renaming the disposable project
mid-sweep would invalidate ``project_id`` for every command that follows it
alphabetically.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step

_COPY_PATH = "verify_module_copy.py"
_MOVED_PATH = "verify_module_moved.py"


async def run_fs_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run ``fs_copy`` then ``fs_move`` on a throwaway copy, then clean it up.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of ``fs_copy``, ``fs_move``, and ``fs_remove`` to their
        outcomes — see module docstring for why ``fs_remove`` is covered here
        rather than left to the generic alphabetical sweep.
    """
    outcomes: Dict[str, CommandOutcome] = {}
    project_id = fixtures.project_id

    copy_outcome = await call_step(
        client,
        "fs_copy",
        {
            "project_id": project_id,
            "source_path": fixtures.py_file_path,
            "dest_path": _COPY_PATH,
        },
        ok_reason="copied the seeded .py file to a throwaway path",
    )
    outcomes["fs_copy"] = copy_outcome

    if copy_outcome.status is Status.EXECUTED_OK:
        outcomes["fs_move"] = await call_step(
            client,
            "fs_move",
            {
                "project_id": project_id,
                "source_path": _COPY_PATH,
                "dest_path": _MOVED_PATH,
            },
            ok_reason="moved the throwaway copy to a second throwaway path",
        )
        cleanup_path = _MOVED_PATH
    else:
        outcomes["fs_move"] = CommandOutcome(
            "fs_move",
            Bucket.BUCKET_A,
            copy_outcome.status,
            "skipped: fs_copy did not create the throwaway file to move",
        )
        cleanup_path = None

    if cleanup_path is not None:
        try:
            remove_resp = await client.call_validated(
                "fs_remove", {"project_id": project_id, "file_path": cleanup_path}
            )
        except Exception as exc:  # noqa: BLE001 - real rejection, still genuine
            outcomes["fs_remove"] = CommandOutcome(
                "fs_remove", Bucket.BUCKET_A, Status.FAILED, truncate(repr(exc))
            )
        else:
            if remove_resp.get("success") is True:
                outcomes["fs_remove"] = CommandOutcome(
                    "fs_remove",
                    Bucket.BUCKET_A,
                    Status.EXECUTED_OK,
                    "removed the throwaway moved copy at lifecycle cleanup",
                )
            else:
                outcomes["fs_remove"] = CommandOutcome(
                    "fs_remove",
                    Bucket.BUCKET_A,
                    Status.EXPECTED_ERROR,
                    truncate(str(remove_resp.get("error"))),
                )
    else:
        outcomes["fs_remove"] = CommandOutcome(
            "fs_remove",
            Bucket.BUCKET_A,
            copy_outcome.status,
            "skipped: fs_copy did not create the throwaway file to remove",
        )
    return outcomes


async def run_change_project_id_last(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> CommandOutcome:
    """Run ``change_project_id`` as the final sweep step and update the fixture.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run; its
            ``project_id`` is mutated in place on success.

    Returns:
        The outcome of the ``change_project_id`` call.
    """
    old_id = fixtures.project_id
    new_id = str(uuid.uuid4())
    try:
        resp = await client.call_validated(
            "change_project_id",
            {
                "project_id": old_id,
                "new_project_id": new_id,
                "old_project_id": old_id,
            },
        )
    except Exception as exc:  # noqa: BLE001 - one bad step must not abort the sweep
        return CommandOutcome(
            "change_project_id", Bucket.BUCKET_A, Status.FAILED, truncate(repr(exc))
        )
    if resp.get("success") is True:
        fixtures.project_id = new_id
        return CommandOutcome(
            "change_project_id",
            Bucket.BUCKET_A,
            Status.EXECUTED_OK,
            f"executed last; disposable project_id updated {old_id} -> {new_id}",
        )
    return CommandOutcome(
        "change_project_id",
        Bucket.BUCKET_A,
        Status.EXPECTED_ERROR,
        truncate(str(resp.get("error"))),
    )
