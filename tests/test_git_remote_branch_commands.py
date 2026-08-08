"""
Remote-branch inspection commands (TODO 487773a8).

``git_branch_list(scope="remote")`` reads ``refs/remotes`` -- the refs cached by
the last fetch -- so it answers what the remote looked like when we last looked,
and answers nothing at all before the first fetch. Deciding whether to publish or
track a branch needs the live answer. ``git_remote_branch_list`` asks the remote
itself, and ``git_remote_branch_prune`` drops tracking refs for branches that are
gone from it -- previously reachable only as a side effect of
``git_branch_fetch(prune=True)``.

Two properties matter enough to pin here beyond the happy path: the list command
must work on a repository with NO COMMITS (ls-remote never touches local
history, so the shared read gate would refuse it for the wrong reason), and
prune must never be reported as having removed something it did not.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import pytest

from code_analysis.commands.git_remote_branch_commands import (
    GIT_REMOTE_BRANCH_LIST_FAILED,
    GIT_REMOTE_BRANCH_PRUNE_FAILED,
    GitRemoteBranchListCommand,
    GitRemoteBranchPruneCommand,
    parse_pruned_refs,
)
from code_analysis.core.git_remote_ops import (
    GIT_NOT_A_REPO,
    GIT_REMOTE_NOT_CONFIGURED,
    GIT_REMOTE_TIMEOUT,
)

_LS_REMOTE_OUTPUT = (
    "1111111111111111111111111111111111111111\trefs/heads/main\n"
    "2222222222222222222222222222222222222222\trefs/heads/cas\n"
    "3333333333333333333333333333333333333333\trefs/heads/feature/x\n"
)
_FOR_EACH_REF_OUTPUT = "origin/main\norigin/HEAD\n"

_MODULE = "code_analysis.commands.git_remote_branch_commands"


class _Recorder:
    """Scripted stand-in for ``run_git_subprocess`` that records every call."""

    def __init__(self, responses: Dict[str, Tuple[int, str, str, bool]]) -> None:
        """Map a matching token in the argv to the response it should produce."""
        self.responses = responses
        self.calls: List[Sequence[str]] = []

    def __call__(
        self, args: Sequence[str], *, cwd: Any, env: Any, timeout_seconds: Any
    ) -> Tuple[int, str, str, bool]:
        """Return the scripted response for the first matching token."""
        self.calls.append(list(args))
        joined = " ".join(args)
        for token, response in self.responses.items():
            if token in joined:
                return response
        return (0, "", "", False)


@pytest.fixture()
def wired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Wire both commands to a temp repo with remote operations enabled."""

    def _wire(
        responses: Dict[str, Tuple[int, str, str, bool]],
        *,
        is_repo: bool = True,
        remote_enabled: bool = True,
    ) -> _Recorder:
        recorder = _Recorder(responses)
        monkeypatch.setattr(f"{_MODULE}.run_git_subprocess", recorder)
        monkeypatch.setattr(f"{_MODULE}.is_git_available", lambda: True)
        monkeypatch.setattr(f"{_MODULE}.is_git_repository", lambda _root: is_repo)
        monkeypatch.setattr(
            f"{_MODULE}.load_git_remote_config",
            lambda _cfg: {
                "remote_enabled": remote_enabled,
                "remote_timeout_seconds": 30,
            },
        )
        monkeypatch.setattr(
            f"{_MODULE}.build_full_subprocess_env", lambda _cfg: ({}, None)
        )
        for command in (GitRemoteBranchListCommand, GitRemoteBranchPruneCommand):
            monkeypatch.setattr(
                command, "_resolve_project_root", lambda self, _pid: tmp_path
            )
            monkeypatch.setattr(command, "_get_raw_config", lambda self: {})
        return recorder

    return _wire


def _payload(result: Any) -> Dict[str, Any]:
    """Extract the data payload from a command result."""
    return dict(getattr(result, "data", {}) or {})


def _error(result: Any) -> Dict[str, Any]:
    """Extract code/message/details from an error result."""
    return {
        "code": getattr(result, "code", None),
        "message": getattr(result, "message", ""),
        "details": getattr(result, "details", {}) or {},
    }


# --- git_remote_branch_list -------------------------------------------------


@pytest.mark.asyncio
async def test_it_reports_the_branches_the_remote_actually_has(wired) -> None:
    """The point of the command: ask the remote, not the fetch cache."""
    recorder = wired(
        {
            "ls-remote": (0, _LS_REMOTE_OUTPUT, "", False),
            "for-each-ref": (0, _FOR_EACH_REF_OUTPUT, "", False),
        }
    )

    result = await GitRemoteBranchListCommand().execute(project_id="p")
    data = _payload(result)

    assert data["count"] == 3
    assert [branch["name"] for branch in data["branches"]] == [
        "main",
        "cas",
        "feature/x",
    ]
    assert data["branches"][0]["commit"] == "1" * 40
    assert any("ls-remote" in " ".join(call) for call in recorder.calls)


@pytest.mark.asyncio
async def test_each_branch_says_whether_it_is_tracked_locally(wired) -> None:
    """'What am I not tracking' should be one call, not a manual diff."""
    wired(
        {
            "ls-remote": (0, _LS_REMOTE_OUTPUT, "", False),
            "for-each-ref": (0, _FOR_EACH_REF_OUTPUT, "", False),
        }
    )

    data = _payload(await GitRemoteBranchListCommand().execute(project_id="p"))

    tracked = {b["name"]: b["tracked_locally"] for b in data["branches"]}
    assert tracked == {"main": True, "cas": False, "feature/x": False}
    assert data["untracked_count"] == 2


@pytest.mark.asyncio
async def test_it_works_on_a_repository_with_no_commits(wired) -> None:
    """The GIT_NO_COMMITS gate is wrong here: ls-remote reads no local history."""
    wired(
        {
            "ls-remote": (0, _LS_REMOTE_OUTPUT, "", False),
            # An unborn repo has no remote-tracking refs at all.
            "for-each-ref": (0, "", "", False),
            "rev-parse": (128, "", "fatal: needed a single revision", False),
        }
    )

    result = await GitRemoteBranchListCommand().execute(project_id="p")
    data = _payload(result)

    assert data["success"] is True
    assert data["count"] == 3
    assert data["untracked_count"] == 3


@pytest.mark.asyncio
async def test_a_pattern_is_passed_through_to_the_remote(wired) -> None:
    """Matching happens on the remote, not by filtering the answer here."""
    recorder = wired(
        {
            "ls-remote": (0, _LS_REMOTE_OUTPUT, "", False),
            "for-each-ref": (0, "", "", False),
        }
    )

    await GitRemoteBranchListCommand().execute(project_id="p", pattern="feature/*")

    ls_call = next(call for call in recorder.calls if "ls-remote" in " ".join(call))
    assert ls_call[-1] == "feature/*"


@pytest.mark.asyncio
async def test_non_branch_refs_are_ignored(wired) -> None:
    """Tags and malformed lines are not branches; do not invent entries."""
    wired(
        {
            "ls-remote": (
                0,
                "4444444444444444444444444444444444444444\trefs/tags/v1\n"
                "garbage-without-a-tab\n"
                "5555555555555555555555555555555555555555\trefs/heads/main\n",
                "",
                False,
            ),
            "for-each-ref": (0, "", "", False),
        }
    )

    data = _payload(await GitRemoteBranchListCommand().execute(project_id="p"))

    assert [branch["name"] for branch in data["branches"]] == ["main"]


@pytest.mark.asyncio
async def test_a_failing_remote_reports_its_stderr(wired) -> None:
    """An unreachable host must say so, not return an empty branch list."""
    wired(
        {
            "ls-remote": (
                128,
                "",
                "fatal: 'origin' does not appear to be a repo",
                False,
            ),
        }
    )

    result = await GitRemoteBranchListCommand().execute(project_id="p")
    error = _error(result)

    assert error["code"] == GIT_REMOTE_BRANCH_LIST_FAILED
    assert "does not appear to be a repo" in error["details"]["stderr"]


@pytest.mark.asyncio
async def test_a_timeout_is_its_own_outcome(wired) -> None:
    """A hung remote is not the same as a remote with no branches."""
    wired({"ls-remote": (1, "", "", True)})

    assert (
        _error(await GitRemoteBranchListCommand().execute(project_id="p"))["code"]
        == GIT_REMOTE_TIMEOUT
    )


@pytest.mark.asyncio
async def test_remote_operations_disabled_is_refused_up_front(wired) -> None:
    """Configuration says no network; do not attempt one."""
    recorder = wired({"ls-remote": (0, "", "", False)}, remote_enabled=False)

    result = await GitRemoteBranchListCommand().execute(project_id="p")

    assert _error(result)["code"] == GIT_REMOTE_NOT_CONFIGURED
    assert recorder.calls == []


@pytest.mark.asyncio
async def test_a_non_repository_is_refused(wired) -> None:
    """Nothing to query if the resolved root is not a repository."""
    wired({"ls-remote": (0, "", "", False)}, is_repo=False)

    assert (
        _error(await GitRemoteBranchListCommand().execute(project_id="p"))["code"]
        == GIT_NOT_A_REPO
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_remote", ["", "   ", "--upload-pack=evil", None, 7])
async def test_a_remote_that_git_would_read_as_an_option_is_rejected(
    wired, bad_remote: Any
) -> None:
    """A leading dash turns the remote argument into a git option."""
    recorder = wired({"ls-remote": (0, "", "", False)})

    result = await GitRemoteBranchListCommand().execute(
        project_id="p", remote=bad_remote
    )

    assert _error(result)["code"] == "VALIDATION_ERROR"
    assert _error(result)["details"]["field"] == "remote"
    assert recorder.calls == []


# --- git_remote_branch_prune ------------------------------------------------


@pytest.mark.asyncio
async def test_prune_reports_every_ref_it_removed(wired) -> None:
    """The caller needs the names, not just a count."""
    wired(
        {
            "remote prune": (
                0,
                "Pruning origin\nURL: git@example.com:x/y.git\n"
                " * [pruned] origin/gone-one\n * [pruned] origin/gone-two\n",
                "",
                False,
            )
        }
    )

    data = _payload(await GitRemoteBranchPruneCommand().execute(project_id="p"))

    assert data["pruned"] == ["origin/gone-one", "origin/gone-two"]
    assert data["pruned_count"] == 2
    assert data["dry_run"] is False


@pytest.mark.asyncio
async def test_a_dry_run_passes_the_flag_and_removes_nothing(wired) -> None:
    """Looking first must not be indistinguishable from doing it."""
    recorder = wired(
        {
            "remote prune": (
                0,
                "Pruning origin\n * [would prune] origin/gone-one\n",
                "",
                False,
            )
        }
    )

    data = _payload(
        await GitRemoteBranchPruneCommand().execute(project_id="p", dry_run=True)
    )

    assert data["dry_run"] is True
    assert data["pruned"] == ["origin/gone-one"]
    assert "--dry-run" in recorder.calls[0]


@pytest.mark.asyncio
async def test_pruning_nothing_is_a_success_with_an_empty_list(wired) -> None:
    """A clean repository is not an error."""
    wired(
        {
            "remote prune": (
                0,
                "Pruning origin\nURL: git@example.com:x/y.git\n",
                "",
                False,
            )
        }
    )

    data = _payload(await GitRemoteBranchPruneCommand().execute(project_id="p"))

    assert data["pruned"] == []
    assert data["pruned_count"] == 0


@pytest.mark.asyncio
async def test_a_failing_prune_reports_its_stderr(wired) -> None:
    """Do not report zero pruned refs when the command did not run."""
    wired({"remote prune": (1, "", "error: No such remote 'nope'", False)})

    error = _error(
        await GitRemoteBranchPruneCommand().execute(project_id="p", remote="nope")
    )

    assert error["code"] == GIT_REMOTE_BRANCH_PRUNE_FAILED
    assert "No such remote" in error["details"]["stderr"]


@pytest.mark.asyncio
async def test_a_non_boolean_dry_run_is_rejected(wired) -> None:
    """ "yes" must not be read as truthy and silently prune for real."""
    recorder = wired({"remote prune": (0, "", "", False)})

    result = await GitRemoteBranchPruneCommand().execute(project_id="p", dry_run="yes")

    assert _error(result)["code"] == "VALIDATION_ERROR"
    assert recorder.calls == []


def test_prune_output_parsing_ignores_everything_that_is_not_a_ref() -> None:
    """Headers, URLs and blank lines are not pruned refs."""
    output = (
        "Pruning origin\n"
        "URL: git@example.com:x/y.git\n"
        "\n"
        " * [pruned] origin/a\n"
        "some unexpected line\n"
        " * [would prune] origin/b\n"
    )

    assert parse_pruned_refs(output) == ["origin/a", "origin/b"]


def test_prune_output_parsing_survives_empty_output() -> None:
    """Git prints nothing at all in some versions when there is nothing to do."""
    assert parse_pruned_refs("") == []


# --- registration and contract ---------------------------------------------


def test_both_commands_declare_the_schema_the_registry_expects() -> None:
    """A command whose schema drifts from its signature fails only in production."""
    for command in (GitRemoteBranchListCommand, GitRemoteBranchPruneCommand):
        schema = command.get_schema()
        assert schema["required"] == ["project_id"]
        assert schema["additionalProperties"] is False
        assert "remote" in schema["properties"]
        assert command.get_name() == command.name
        assert command.metadata()["name"] == command.name


def test_the_metadata_points_at_the_commands_that_cover_the_rest() -> None:
    """Discovery via the group name must lead to the whole remote-branch set.

    Publishing, deleting and tracking already had commands under git_branch_*
    names; the value of naming this pair git_remote_branch_* is only realised if
    finding one of them finds the others too.
    """
    related = GitRemoteBranchListCommand.metadata()["related_commands"]

    for expected in (
        "git_branch_push",
        "git_branch_delete_remote",
        "git_branch_track_remote",
        "git_remote_branch_prune",
    ):
        assert expected in related
