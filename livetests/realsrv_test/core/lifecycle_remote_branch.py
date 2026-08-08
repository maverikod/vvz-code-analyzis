"""
Remote-branch inspection against a real server (TODO 487773a8).

Registered as suite ``s21`` (``realsrv_test.suites.s21_remote_branch``,
``SUITE_NAME = "remotebranch"``).

``git_remote_branch_list`` and ``git_remote_branch_prune`` talk to a remote, and
the sweep's disposable project has no reachable one -- the existing git checks
show exactly that, every ``origin`` operation coming back "does not appear to be
a git repository". Exercising only that path would prove the error branch and
nothing else.

So this suite gives itself a real remote in the only way that needs no
infrastructure: a git repository can serve as its own remote. ``git ls-remote .``
enumerates the project's own refs over the same code path a network remote would
use, and a configured remote pointing at ``.`` gives prune something real to
operate on. Both checks therefore exercise the success branch, not just the
refusal.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME_LIST_LIVE = "remote_branch_list_reads_the_remote"
CHECK_NAME_LIST_REJECTS_OPTION = "remote_branch_list_rejects_option_like_remote"
CHECK_NAME_PRUNE_LIVE = "remote_branch_prune_reports_what_it_pruned"

#: A repository is a valid remote for itself, which is how these checks get a
#: reachable remote without any infrastructure.
_SELF_REMOTE = "."
_SELF_REMOTE_NAME = "selfremote"


def _outcome(name: str, status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as a single-entry outcome map."""
    return {name: CommandOutcome(name, Bucket.BUCKET_A, status, reason)}


def _succeeded(response: Any) -> bool:
    """Whether a client response reports success.

    ``call_validated`` returns ``{"success": False, "error": {...}}`` for a
    command-level rejection instead of raising, so the absence of an exception
    says nothing.
    """
    if isinstance(response, dict):
        return response.get("success") is True
    return bool(getattr(response, "success", False))


def _data_of(response: Any) -> Dict[str, Any]:
    """Extract the data payload from a client response."""
    if isinstance(response, dict):
        inner = response.get("data")
        if isinstance(inner, dict):
            return inner
        return response
    data = getattr(response, "data", None)
    return data if isinstance(data, dict) else {}


def _error_of(response: Any) -> Dict[str, Any]:
    """Extract the error object from a failed client response."""
    if isinstance(response, dict):
        error = response.get("error")
        if isinstance(error, dict):
            return error
        if error is not None:
            return {"message": str(error)}
    return {}


async def run_remote_branch_list(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """TODO 487773a8: ask the remote what branches it has, right now.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Outcomes for the positive listing and the option-like-remote refusal.
    """
    outcomes: Dict[str, CommandOutcome] = {}

    response = await client.call_validated(
        "git_remote_branch_list",
        {"project_id": fixtures.project_id, "remote": _SELF_REMOTE},
    )
    if not _succeeded(response):
        outcomes.update(
            _outcome(
                CHECK_NAME_LIST_LIVE,
                Status.FAILED,
                (
                    "listing a repository's own refs failed, so the command "
                    f"cannot read any remote: {truncate(repr(_error_of(response)))}"
                ),
            )
        )
    else:
        data = _data_of(response)
        branches = data.get("branches") or []
        missing = [
            key
            for key in ("remote", "branches", "count", "untracked_count")
            if key not in data
        ]
        if missing:
            outcomes.update(
                _outcome(
                    CHECK_NAME_LIST_LIVE,
                    Status.FAILED,
                    f"response is missing contracted fields {missing}: {truncate(repr(data))}",
                )
            )
        elif not branches:
            outcomes.update(
                _outcome(
                    CHECK_NAME_LIST_LIVE,
                    Status.FAILED,
                    (
                        "the project's own repository reported zero branches; "
                        "ls-remote output is not being parsed"
                    ),
                )
            )
        elif not all(
            isinstance(b, dict)
            and isinstance(b.get("name"), str)
            and isinstance(b.get("commit"), str)
            and isinstance(b.get("tracked_locally"), bool)
            for b in branches
        ):
            outcomes.update(
                _outcome(
                    CHECK_NAME_LIST_LIVE,
                    Status.FAILED,
                    f"branch entries have the wrong shape: {truncate(repr(branches[:3]))}",
                )
            )
        else:
            outcomes.update(
                _outcome(
                    CHECK_NAME_LIST_LIVE,
                    Status.EXECUTED_OK,
                    (
                        f"read {data['count']} branch(es) straight from the remote "
                        f"({[b['name'] for b in branches][:5]}), "
                        f"untracked_count={data['untracked_count']}"
                    ),
                )
            )

    # Negative direction: a remote starting with '-' would be read by git as an
    # option, so it must be refused before any subprocess runs.
    rejected = await client.call_validated(
        "git_remote_branch_list",
        {"project_id": fixtures.project_id, "remote": "--upload-pack=evil"},
    )
    if _succeeded(rejected):
        outcomes.update(
            _outcome(
                CHECK_NAME_LIST_REJECTS_OPTION,
                Status.FAILED,
                "an option-like remote was accepted instead of rejected",
            )
        )
    else:
        error = _error_of(rejected)
        code = str(error.get("code") or "")
        if code == "VALIDATION_ERROR":
            outcomes.update(
                _outcome(
                    CHECK_NAME_LIST_REJECTS_OPTION,
                    Status.EXECUTED_OK,
                    f"option-like remote refused with {code}",
                )
            )
        else:
            outcomes.update(
                _outcome(
                    CHECK_NAME_LIST_REJECTS_OPTION,
                    Status.FAILED,
                    (
                        "expected VALIDATION_ERROR for an option-like remote, got "
                        f"{truncate(repr(error))}"
                    ),
                )
            )
    return outcomes


async def run_remote_branch_prune(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """TODO 487773a8: prune stale tracking refs without also fetching.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_PRUNE_LIVE: CommandOutcome(...)}``.
    """
    added = await client.call_validated(
        "git_remote_add",
        {
            "project_id": fixtures.project_id,
            "name": _SELF_REMOTE_NAME,
            "url": str(fixtures.project_root),
        },
    )
    if not _succeeded(added):
        return _outcome(
            CHECK_NAME_PRUNE_LIVE,
            Status.INCONCLUSIVE,
            (
                "could not configure a reachable remote to prune, so nothing "
                f"downstream proves anything: {truncate(repr(_error_of(added)))}"
            ),
        )

    try:
        response = await client.call_validated(
            "git_remote_branch_prune",
            {
                "project_id": fixtures.project_id,
                "remote": _SELF_REMOTE_NAME,
                "dry_run": True,
            },
        )
        if not _succeeded(response):
            return _outcome(
                CHECK_NAME_PRUNE_LIVE,
                Status.FAILED,
                f"prune against a reachable remote failed: {truncate(repr(_error_of(response)))}",
            )
        data = _data_of(response)
        if data.get("dry_run") is not True:
            return _outcome(
                CHECK_NAME_PRUNE_LIVE,
                Status.FAILED,
                (
                    "dry_run was not echoed as true, so a caller cannot tell a "
                    f"preview from a real prune: {truncate(repr(data))}"
                ),
            )
        if not isinstance(data.get("pruned"), list) or not isinstance(
            data.get("pruned_count"), int
        ):
            return _outcome(
                CHECK_NAME_PRUNE_LIVE,
                Status.FAILED,
                f"response is missing the contracted pruned/pruned_count: {truncate(repr(data))}",
            )
        if data["pruned_count"] != len(data["pruned"]):
            return _outcome(
                CHECK_NAME_PRUNE_LIVE,
                Status.FAILED,
                (
                    f"pruned_count={data['pruned_count']} disagrees with the "
                    f"{len(data['pruned'])} refs listed"
                ),
            )
        return _outcome(
            CHECK_NAME_PRUNE_LIVE,
            Status.EXECUTED_OK,
            (
                f"dry-run prune against a reachable remote reported "
                f"pruned_count={data['pruned_count']} with a matching ref list"
            ),
        )
    finally:
        await client.call_validated(
            "git_remote_remove",
            {"project_id": fixtures.project_id, "name": _SELF_REMOTE_NAME},
        )
