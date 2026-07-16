"""
Ordered git config/remote/branch-tracking lifecycle for the live-server verifier.

Exercises the git commands that need either a second branch to compare
against (``git_branch_compare``) or a configured remote to operate on
(``git_remote_set_url`` / ``set_push_url`` / ``rename`` / ``remove``,
``git_branch_set_upstream`` / ``git_branch_track_remote``). The remote uses an
``.invalid`` URL — ``git_remote_add`` only writes ``.git/config``, it never
contacts the URL, so this stays entirely local. Upstream/tracking commands are
expected to reject an unknown remote-tracking ref; that real server error is
recorded as ``expected-error``, not a skip.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import CommandOutcome
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step

_REMOTE_NAME_1 = "origin_test"
_REMOTE_NAME_2 = "origin_test2"


async def run_git_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run the git show/compare/config/remote/upstream command chain.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    outcomes: Dict[str, CommandOutcome] = {}
    project_id = fixtures.project_id

    outcomes["git_show"] = await call_step(
        client, "git_show", {"project_id": project_id, "rev": "HEAD"}
    )
    outcomes["git_branch_compare"] = await call_step(
        client,
        "git_branch_compare",
        {
            "project_id": project_id,
            "base": "main",
            "head": fixtures.feature_branch_name,
        },
    )
    outcomes["git_identity_set"] = await call_step(
        client,
        "git_identity_set",
        {
            "project_id": project_id,
            "name": "Verify Sweep",
            "email": "verify-sweep@example.invalid",
            "scope": "local",
        },
        ok_reason="local git identity set for the disposable project",
    )
    outcomes["git_config_get"] = await call_step(
        client, "git_config_get", {"project_id": project_id, "key": "user.name"}
    )

    outcomes["git_remote_add"] = await call_step(
        client,
        "git_remote_add",
        {
            "project_id": project_id,
            "name": _REMOTE_NAME_1,
            "url": "https://example.invalid/repo.git",
        },
        ok_reason="local-only remote registered (URL never contacted)",
    )
    outcomes["git_remote_set_url"] = await call_step(
        client,
        "git_remote_set_url",
        {
            "project_id": project_id,
            "name": _REMOTE_NAME_1,
            "url": "https://example.invalid/repo-fetch.git",
        },
    )
    outcomes["git_remote_set_push_url"] = await call_step(
        client,
        "git_remote_set_push_url",
        {
            "project_id": project_id,
            "name": _REMOTE_NAME_1,
            "url": "https://example.invalid/repo-push.git",
        },
    )
    outcomes["git_remote_rename"] = await call_step(
        client,
        "git_remote_rename",
        {
            "project_id": project_id,
            "old_name": _REMOTE_NAME_1,
            "new_name": _REMOTE_NAME_2,
        },
    )

    remote_branch = f"{_REMOTE_NAME_2}/{fixtures.feature_branch_name}"
    outcomes["git_branch_set_upstream"] = await call_step(
        client,
        "git_branch_set_upstream",
        {
            "project_id": project_id,
            "branch": fixtures.feature_branch_name,
            "upstream": remote_branch,
        },
        ok_reason="upstream set (no fetched remote-tracking ref expected)",
    )
    outcomes["git_branch_track_remote"] = await call_step(
        client,
        "git_branch_track_remote",
        {"project_id": project_id, "remote_branch": remote_branch},
        ok_reason="tracking branch created (no fetched remote-tracking ref expected)",
    )

    outcomes["git_remote_remove"] = await call_step(
        client,
        "git_remote_remove",
        {"project_id": project_id, "name": _REMOTE_NAME_2},
        ok_reason="test remote removed at lifecycle teardown",
    )
    return outcomes
