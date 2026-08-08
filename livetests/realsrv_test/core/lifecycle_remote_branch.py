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
from uuid import uuid4

from code_analysis_client import CodeAnalysisAsyncClient
from code_analysis_client.exceptions import JobFailedError

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME_LIST_LIVE = "remote_branch_list_reads_the_remote"
CHECK_NAME_LIST_REJECTS_OPTION = "remote_branch_list_rejects_option_like_remote"
CHECK_NAME_PRUNE_LIVE = "remote_branch_prune_reports_what_it_pruned"
CHECK_NAME_WRITE_CYCLE = "remote_branch_create_track_compare_delete"

#: A repository is a valid remote for itself, which is how these checks get a
#: reachable remote without any infrastructure.
_SELF_REMOTE = "."
_SELF_REMOTE_NAME = "selfremote"


async def _call(
    client: CodeAnalysisAsyncClient, name: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Call a command and always return a response dict, never raise.

    Queued and non-queued commands report a rejection differently, and the
    difference is invisible at the call site: a command with ``use_queue=False``
    returns ``{"success": False, "error": {...}}``, while a queued one raises
    ``JobFailedError`` carrying that same payload. Every command in this group
    is queued except track, so a suite that only handled the dict form crashed
    on the first negative case instead of asserting on it. Normalising here
    means each check reads one shape.
    """
    try:
        response = await client.call_validated(name, params)
    except JobFailedError as exc:
        error = exc.error if isinstance(exc.error, dict) else {"message": str(exc)}
        return {"success": False, "error": error}
    except Exception as exc:  # noqa: BLE001 - transport failures are results too
        return {"success": False, "error": {"message": truncate(repr(exc))}}
    if isinstance(response, dict):
        return response
    return {
        "success": bool(getattr(response, "success", False)),
        "data": getattr(response, "data", None),
    }


async def _quiet(
    client: CodeAnalysisAsyncClient, name: str, params: Dict[str, Any]
) -> None:
    """Best-effort cleanup call whose failure must never mask the real result."""
    await _call(client, name, params)


def _outcome(name: str, status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as a single-entry outcome map."""
    return {name: CommandOutcome(name, Bucket.BUCKET_A, status, reason)}


def _succeeded(response: Any) -> bool:
    """Whether a normalised response (see :func:`_call`) reports success."""
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


async def _ensure_a_commit(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> bool:
    """Give the disposable project at least one commit, and say whether it has one.

    The sweep's fixture project is a git repository with NO commits -- its
    git_commit step is one of the known expected-errors. An empty repository has
    no refs, so ls-remote correctly returns nothing and there is nothing to
    publish: every check here would report a defect that is really just an empty
    fixture. So the suite makes its own commit, and reports INCONCLUSIVE rather
    than FAILED if it cannot.

    Args:
        client: Connected async client.
        fixtures: The disposable project fixture.

    Returns:
        True when the repository has at least one branch with a commit.
    """
    await _quiet(
        client,
        "git_identity_set",
        {
            "project_id": fixtures.project_id,
            "name": "realsrv-test",
            "email": "realsrv-test@example.invalid",
        },
    )
    await _quiet(client, "git_add", {"project_id": fixtures.project_id, "all": True})
    await _quiet(
        client,
        "git_commit",
        {
            "project_id": fixtures.project_id,
            "message": "realsrv-test: seed a commit for remote-branch checks",
        },
    )
    listed = await _call(
        client, "git_branch_list", {"project_id": fixtures.project_id, "scope": "local"}
    )
    if not _succeeded(listed):
        return False
    return bool(_data_of(listed).get("branches"))


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
    has_commit = await _ensure_a_commit(client, fixtures)

    response = await _call(
        client,
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
                    Status.FAILED if has_commit else Status.INCONCLUSIVE,
                    (
                        (
                            "the project's own repository reported zero branches; "
                            "ls-remote output is not being parsed"
                        )
                        if has_commit
                        else (
                            "the fixture repository has no commits, so it has no refs "
                            "to list -- an empty answer proves nothing here"
                        )
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
    rejected = await _call(
        client,
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
    await _quiet(
        client,
        "git_remote_remove",
        {"project_id": fixtures.project_id, "name": _SELF_REMOTE_NAME},
    )
    added = await _call(
        client,
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
        response = await _call(
            client,
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
        await _call(
            client,
            "git_remote_remove",
            {"project_id": fixtures.project_id, "name": _SELF_REMOTE_NAME},
        )


async def run_remote_branch_write_cycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """TODO 487773a8: publish, track, compare and delete a branch on a remote.

    One ordered chain rather than four independent checks, because each step is
    the only realistic way to set up the next: you cannot track a remote branch
    that was never published, and deleting one proves nothing unless it was
    there. A break anywhere is reported against this single check with the step
    that failed named.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME_WRITE_CYCLE: CommandOutcome(...)}``.
    """
    if not await _ensure_a_commit(client, fixtures):
        return _outcome(
            CHECK_NAME_WRITE_CYCLE,
            Status.INCONCLUSIVE,
            "the fixture repository has no commits, so there is nothing to publish",
        )

    suffix = uuid4().hex[:8]
    published = f"review/{suffix}"
    local_copy = f"track_{suffix}"
    steps: list[str] = []

    await _quiet(
        client,
        "git_remote_remove",
        {"project_id": fixtures.project_id, "name": _SELF_REMOTE_NAME},
    )
    added = await _call(
        client,
        "git_remote_add",
        {
            "project_id": fixtures.project_id,
            "name": _SELF_REMOTE_NAME,
            "url": str(fixtures.project_root),
        },
    )
    if not _succeeded(added):
        return _outcome(
            CHECK_NAME_WRITE_CYCLE,
            Status.INCONCLUSIVE,
            (
                "could not configure a reachable remote, so nothing downstream "
                f"proves anything: {truncate(repr(_error_of(added)))}"
            ),
        )

    try:
        created = await _call(
            client,
            "git_remote_branch_create",
            {
                "project_id": fixtures.project_id,
                "remote": _SELF_REMOTE_NAME,
                "remote_branch": published,
            },
        )
        if not _succeeded(created):
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                f"create failed: {truncate(repr(_error_of(created)))}",
            )
        create_data = _data_of(created)
        if create_data.get("remote_branch") != published:
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                (
                    "create did not publish under the requested name: "
                    f"{truncate(repr(create_data))}"
                ),
            )
        steps.append(f"created {published} via refspec {create_data.get('refspec')}")

        # The tracking ref has to exist on disk before track/compare can use it.
        fetched = await _call(
            client,
            "git_fetch",
            {"project_id": fixtures.project_id, "remote": _SELF_REMOTE_NAME},
        )
        if not _succeeded(fetched):
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.INCONCLUSIVE,
                (
                    "published, but the remote could not be fetched, so track and "
                    f"compare had no ref to use: {truncate(repr(_error_of(fetched)))}"
                ),
            )

        tracked = await _call(
            client,
            "git_remote_branch_track",
            {
                "project_id": fixtures.project_id,
                "remote": _SELF_REMOTE_NAME,
                "remote_branch": published,
                "local_branch": local_copy,
            },
        )
        if not _succeeded(tracked):
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                f"track failed: {truncate(repr(_error_of(tracked)))}",
            )
        track_data = _data_of(tracked)
        if track_data.get("action") != "created":
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                (
                    "track of a branch that does not exist locally should report "
                    f"action='created', got {truncate(repr(track_data))}"
                ),
            )
        if track_data.get("checked_out") is not False:
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                "track moved the working tree without being asked to",
            )
        steps.append(f"tracked as {local_copy} (action=created, tree untouched)")

        compared = await _call(
            client,
            "git_remote_branch_compare",
            {
                "project_id": fixtures.project_id,
                "branch": local_copy,
                "remote": _SELF_REMOTE_NAME,
                "remote_branch": published,
            },
        )
        if not _succeeded(compared):
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                f"compare failed: {truncate(repr(_error_of(compared)))}",
            )
        compare_data = _data_of(compared)
        if compare_data.get("fetched") is not True:
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                (
                    "compare reported fetched=false by default, so its counts "
                    "came from a cache that may be stale (defect d05492ef)"
                ),
            )
        if not compare_data.get("in_sync"):
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                (
                    "a branch created from the remote one should be in sync, got "
                    f"ahead={compare_data.get('ahead')} "
                    f"behind={compare_data.get('behind')}"
                ),
            )
        steps.append("compared: fetched=True, ahead=0, behind=0")

        refused = await _call(
            client,
            "git_remote_branch_delete",
            {
                "project_id": fixtures.project_id,
                "remote": _SELF_REMOTE_NAME,
                "remote_branch": published,
                "force_confirm": False,
            },
        )
        if _succeeded(refused):
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                "delete without force_confirm removed the branch anyway",
            )
        steps.append("delete without force_confirm refused")

        deleted = await _call(
            client,
            "git_remote_branch_delete",
            {
                "project_id": fixtures.project_id,
                "remote": _SELF_REMOTE_NAME,
                "remote_branch": published,
                "force_confirm": True,
            },
        )
        if not _succeeded(deleted):
            return _outcome(
                CHECK_NAME_WRITE_CYCLE,
                Status.FAILED,
                f"delete failed: {truncate(repr(_error_of(deleted)))}",
            )

        # Prove the delete rather than trusting the exit code.
        remaining = await _call(
            client,
            "git_remote_branch_list",
            {"project_id": fixtures.project_id, "remote": _SELF_REMOTE_NAME},
        )
        if _succeeded(remaining):
            names = [
                b.get("name")
                for b in (_data_of(remaining).get("branches") or [])
                if isinstance(b, dict)
            ]
            if published in names:
                return _outcome(
                    CHECK_NAME_WRITE_CYCLE,
                    Status.FAILED,
                    (
                        f"delete reported success but {published} is still on the "
                        "remote"
                    ),
                )
            steps.append(f"deleted, and {published} is gone from ls-remote")

        return _outcome(CHECK_NAME_WRITE_CYCLE, Status.EXECUTED_OK, "; ".join(steps))
    finally:
        await _call(
            client,
            "git_branch_delete",
            {
                "project_id": fixtures.project_id,
                "name": local_copy,
                "force": True,
            },
        )
        await _call(
            client,
            "git_remote_remove",
            {"project_id": fixtures.project_id, "name": _SELF_REMOTE_NAME},
        )
