"""
The ``git_remote_branch_*`` command group (TODO 487773a8).

Six commands that operate on the branch as it exists ON THE REMOTE. Beyond each
happy path, the properties pinned here are the ones whose absence would be
silent or destructive:

* ``list`` must work on a repository with NO COMMITS -- ls-remote reads no local
  history, so the shared read gate would refuse it for the wrong reason.
* ``create`` must apply the protected-branch guard to the name being WRITTEN on
  the remote, not the local source name. Guarding the source is what
  ``git_branch_push`` does, and it would wave through publishing local ``tmp``
  as remote ``main``.
* ``delete`` must not read the ordinary branch name ``feature/x`` as branch
  ``x`` on a remote called ``feature``; only a configured remote may claim that
  prefix. This one was caught by the tests below, not by review.
* ``track`` must pick between create-tracking and set-upstream on its own, and
  must not move the working tree as a side effect.
* ``compare`` must refresh the remote ref before counting, because a comparison
  against a stale cache is a confident wrong answer (defect d05492ef), and must
  refuse rather than report zero when the count cannot be parsed.
* ``prune`` must never report removing something it did not.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import pytest

from code_analysis.commands.git_remote_branch_commands import (
    GIT_CONFIRMATION_REQUIRED,
    GIT_REMOTE_BRANCH_COMPARE_FAILED,
    GIT_REMOTE_BRANCH_CREATE_FAILED,
    GIT_REMOTE_BRANCH_DELETE_FAILED,
    GIT_REMOTE_BRANCH_LIST_FAILED,
    GIT_REMOTE_BRANCH_NOT_FOUND,
    GIT_REMOTE_BRANCH_PRUNE_FAILED,
    GitRemoteBranchCompareCommand,
    GitRemoteBranchCreateCommand,
    GitRemoteBranchDeleteCommand,
    GitRemoteBranchListCommand,
    GitRemoteBranchPruneCommand,
    GitRemoteBranchTrackCommand,
    parse_ahead_behind,
    parse_pruned_refs,
    split_remote_branch,
)
from code_analysis.core.git_remote_ops import (
    GIT_NOT_A_REPO,
    GIT_PROTECTED_BRANCH,
    GIT_REMOTE_NOT_CONFIGURED,
    GIT_REMOTE_TIMEOUT,
)

_ALL_COMMANDS = (
    GitRemoteBranchListCommand,
    GitRemoteBranchCreateCommand,
    GitRemoteBranchDeleteCommand,
    GitRemoteBranchTrackCommand,
    GitRemoteBranchCompareCommand,
    GitRemoteBranchPruneCommand,
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
        protected_branches: List[str] | None = None,
        allow_force_push: bool = True,
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
                "protected_branches": list(protected_branches or []),
                "allow_force_push": allow_force_push,
            },
        )
        monkeypatch.setattr(
            f"{_MODULE}.build_full_subprocess_env", lambda _cfg: ({}, None)
        )
        for command in _ALL_COMMANDS:
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


# --- git_remote_branch_create -----------------------------------------------


@pytest.mark.asyncio
async def test_create_publishes_under_the_requested_remote_name(wired) -> None:
    """The capability git_branch_push lacks: a branch under a different name."""
    recorder = wired(
        {"branch --show-current": (0, "local\n", "", False), "push": (0, "", "", False)}
    )

    data = _payload(
        await GitRemoteBranchCreateCommand().execute(
            project_id="p", branch="local", remote_branch="review/local"
        )
    )

    assert data["refspec"] == "local:refs/heads/review/local"
    push = next(call for call in recorder.calls if "push" in call)
    assert push[-1] == "local:refs/heads/review/local"


@pytest.mark.asyncio
async def test_create_defaults_the_remote_name_to_the_local_one(wired) -> None:
    """The common case must not require repeating the name."""
    wired({"push": (0, "", "", False)})

    data = _payload(
        await GitRemoteBranchCreateCommand().execute(project_id="p", branch="feature/x")
    )

    assert data["remote_branch"] == "feature/x"
    assert data["refspec"] == "feature/x:refs/heads/feature/x"


@pytest.mark.asyncio
async def test_create_guards_the_remote_name_not_the_local_one(wired) -> None:
    """Publishing local 'tmp' as remote 'main' is a write to main.

    Guarding the SOURCE name -- which is what git_branch_push checks -- would
    wave this through, because 'tmp' is not protected.
    """
    recorder = wired({"push": (0, "", "", False)}, protected_branches=["main"])

    result = await GitRemoteBranchCreateCommand().execute(
        project_id="p", branch="tmp", remote_branch="main"
    )

    assert _error(result)["code"] == GIT_PROTECTED_BRANCH
    assert recorder.calls == [], "nothing may be pushed once the guard fires"


@pytest.mark.asyncio
async def test_create_allows_a_protected_name_with_an_explicit_override(wired) -> None:
    """The guard is a speed bump for the deliberate case, not a wall."""
    wired({"push": (0, "", "", False)}, protected_branches=["main"])

    result = await GitRemoteBranchCreateCommand().execute(
        project_id="p", branch="tmp", remote_branch="main", protected_override=True
    )

    assert _payload(result)["remote_branch"] == "main"


@pytest.mark.asyncio
async def test_create_honours_the_force_push_configuration(wired) -> None:
    """A force push stays refused when configuration disallows it."""
    wired({"push": (0, "", "", False)}, allow_force_push=False)

    result = await GitRemoteBranchCreateCommand().execute(
        project_id="p", branch="x", force=True
    )

    assert _error(result)["code"] == "GIT_FORCE_PUSH_DISABLED"


@pytest.mark.asyncio
async def test_create_reports_a_rejected_push(wired) -> None:
    """A non-fast-forward rejection must not be reported as a publish."""
    wired({"push": (1, "", "! [rejected] non-fast-forward", False)})

    error = _error(
        await GitRemoteBranchCreateCommand().execute(project_id="p", branch="x")
    )

    assert error["code"] == GIT_REMOTE_BRANCH_CREATE_FAILED
    assert "non-fast-forward" in error["details"]["stderr"]


@pytest.mark.asyncio
async def test_create_refuses_a_detached_head_without_a_branch(wired) -> None:
    """There is no current branch to publish; say so instead of guessing."""
    wired({"branch --show-current": (0, "\n", "", False)})

    result = await GitRemoteBranchCreateCommand().execute(project_id="p")

    assert _error(result)["code"] == "VALIDATION_ERROR"


# --- git_remote_branch_delete -----------------------------------------------


@pytest.mark.asyncio
async def test_delete_requires_explicit_confirmation(wired) -> None:
    """Deleting a remote branch removes it for everyone."""
    recorder = wired(
        {"git remote": (0, "origin\n", "", False), "push": (0, "", "", False)}
    )

    result = await GitRemoteBranchDeleteCommand().execute(
        project_id="p", remote_branch="feature/x", force_confirm=False
    )

    assert _error(result)["code"] == GIT_CONFIRMATION_REQUIRED
    assert not any("push" in call for call in recorder.calls)


@pytest.mark.asyncio
async def test_delete_pushes_the_delete_refspec(wired) -> None:
    """The happy path, and the exact argv git is given."""
    recorder = wired(
        {
            "git remote": (0, "origin\n", "", False),
            "push": (0, "", "- [deleted]  feature/x", False),
        }
    )

    data = _payload(
        await GitRemoteBranchDeleteCommand().execute(
            project_id="p", remote_branch="feature/x", force_confirm=True
        )
    )

    assert data["deleted"] is True
    assert ["git", "push", "origin", "--delete", "feature/x"] in recorder.calls


@pytest.mark.asyncio
async def test_delete_infers_the_remote_from_a_qualified_name(wired) -> None:
    """'upstream/feature/x' means feature/x on upstream, when upstream is a remote."""
    recorder = wired(
        {
            "git remote": (0, "origin\nupstream\n", "", False),
            "push": (0, "", "", False),
        }
    )

    data = _payload(
        await GitRemoteBranchDeleteCommand().execute(
            project_id="p", remote_branch="upstream/feature/x", force_confirm=True
        )
    )

    assert data["remote"] == "upstream"
    assert data["remote_branch"] == "feature/x"
    assert ["git", "push", "upstream", "--delete", "feature/x"] in recorder.calls


@pytest.mark.asyncio
async def test_delete_does_not_mistake_a_slashed_branch_for_a_remote(wired) -> None:
    """'feature/x' is one branch name, not branch 'x' on a remote 'feature'.

    Splitting on the first slash unconditionally would delete the wrong ref the
    moment a remote happened to be called 'feature' -- and quietly target the
    wrong remote even when one did not.
    """
    recorder = wired(
        {"git remote": (0, "origin\n", "", False), "push": (0, "", "", False)}
    )

    data = _payload(
        await GitRemoteBranchDeleteCommand().execute(
            project_id="p", remote_branch="feature/x", force_confirm=True
        )
    )

    assert data["remote"] == "origin"
    assert data["remote_branch"] == "feature/x"
    assert ["git", "push", "origin", "--delete", "feature/x"] in recorder.calls


@pytest.mark.asyncio
async def test_an_explicit_remote_is_never_second_guessed(wired) -> None:
    """When the caller names the remote, the branch name is taken verbatim."""
    recorder = wired(
        {
            "git remote": (0, "origin\nfeature\n", "", False),
            "push": (0, "", "", False),
        }
    )

    data = _payload(
        await GitRemoteBranchDeleteCommand().execute(
            project_id="p",
            remote_branch="feature/x",
            remote="origin",
            force_confirm=True,
        )
    )

    assert data["remote"] == "origin"
    assert data["remote_branch"] == "feature/x"
    assert ["git", "push", "origin", "--delete", "feature/x"] in recorder.calls


@pytest.mark.asyncio
async def test_delete_refuses_a_protected_branch(wired) -> None:
    """force_confirm alone must not be enough for a protected name."""
    recorder = wired(
        {"git remote": (0, "origin\n", "", False), "push": (0, "", "", False)},
        protected_branches=["main"],
    )

    result = await GitRemoteBranchDeleteCommand().execute(
        project_id="p", remote_branch="main", force_confirm=True
    )

    assert _error(result)["code"] == GIT_PROTECTED_BRANCH
    assert not any("push" in call for call in recorder.calls)


@pytest.mark.asyncio
async def test_delete_reports_a_missing_remote_branch(wired) -> None:
    """Deleting something that is not there is a failure, not a silent success."""
    wired(
        {
            "git remote": (0, "origin\n", "", False),
            "push": (
                1,
                "",
                "error: unable to delete 'nope': remote ref does not exist",
                False,
            ),
        }
    )

    error = _error(
        await GitRemoteBranchDeleteCommand().execute(
            project_id="p", remote_branch="nope", force_confirm=True
        )
    )

    assert error["code"] == GIT_REMOTE_BRANCH_DELETE_FAILED
    assert "does not exist" in error["details"]["stderr"]


# --- git_remote_branch_track ------------------------------------------------


@pytest.mark.asyncio
async def test_track_creates_a_local_branch_when_there_is_none(wired) -> None:
    """The git_branch_track_remote case, chosen automatically."""
    recorder = wired(
        {
            "git remote": (0, "origin\n", "", False),
            "show-ref --verify --quiet refs/remotes/origin/cas": (0, "", "", False),
            "show-ref --verify --quiet refs/heads/cas": (1, "", "", False),
            "branch --track": (0, "", "", False),
        }
    )

    data = _payload(
        await GitRemoteBranchTrackCommand().execute(
            project_id="p", remote_branch="origin/cas"
        )
    )

    assert data["action"] == "created"
    assert data["upstream"] == "origin/cas"
    assert ["git", "branch", "--track", "cas", "origin/cas"] in recorder.calls


@pytest.mark.asyncio
async def test_track_sets_the_upstream_when_the_branch_exists(wired) -> None:
    """The git_branch_set_upstream case, chosen automatically."""
    recorder = wired(
        {
            "git remote": (0, "origin\n", "", False),
            "show-ref --verify --quiet refs/remotes/origin/cas": (0, "", "", False),
            "show-ref --verify --quiet refs/heads/cas": (0, "", "", False),
            "--set-upstream-to": (0, "", "", False),
        }
    )

    data = _payload(
        await GitRemoteBranchTrackCommand().execute(
            project_id="p", remote_branch="origin/cas"
        )
    )

    assert data["action"] == "upstream_set"
    assert [
        "git",
        "branch",
        "--set-upstream-to=origin/cas",
        "cas",
    ] in recorder.calls


@pytest.mark.asyncio
async def test_track_does_not_move_the_working_tree_by_default(wired) -> None:
    """Tracking a branch is not a request to check it out."""
    recorder = wired(
        {
            "git remote": (0, "origin\n", "", False),
            "show-ref --verify --quiet refs/remotes/origin/cas": (0, "", "", False),
            "show-ref --verify --quiet refs/heads/cas": (1, "", "", False),
            "branch --track": (0, "", "", False),
        }
    )

    data = _payload(
        await GitRemoteBranchTrackCommand().execute(
            project_id="p", remote_branch="origin/cas"
        )
    )

    assert data["checked_out"] is False
    assert not any("checkout" in call for call in recorder.calls)


@pytest.mark.asyncio
async def test_track_reports_a_missing_remote_ref_actionably(wired) -> None:
    """This command reads local refs only; say so rather than failing obscurely."""
    wired({"show-ref": (1, "", "", False)})

    error = _error(
        await GitRemoteBranchTrackCommand().execute(
            project_id="p", remote_branch="origin/never-fetched"
        )
    )

    assert error["code"] == GIT_REMOTE_BRANCH_NOT_FOUND
    assert "fetch" in error["message"].lower()


# --- git_remote_branch_compare ----------------------------------------------


@pytest.mark.asyncio
async def test_compare_refreshes_the_ref_before_counting(wired) -> None:
    """Defect d05492ef: counts computed against a stale cache are wrong.

    A comparison that does not refresh is a confident wrong answer, so the
    fetch is the default and the response says it happened.
    """
    recorder = wired(
        {
            "show-ref --verify --quiet refs/heads/local": (0, "", "", False),
            "fetch": (0, "", "", False),
            "show-ref --verify --quiet refs/remotes/origin/local": (0, "", "", False),
            "rev-list": (0, "2\t5\n", "", False),
            "log": (0, "abc123 one\ndef456 two\n", "", False),
        }
    )

    data = _payload(
        await GitRemoteBranchCompareCommand().execute(project_id="p", branch="local")
    )

    assert data["fetched"] is True
    assert data["ahead"] == 2
    assert data["behind"] == 5
    assert data["in_sync"] is False
    assert any("fetch" in call for call in recorder.calls)


@pytest.mark.asyncio
async def test_compare_can_be_asked_for_the_cached_answer(wired) -> None:
    """Deliberately offline is legitimate -- but must be reported as such."""
    recorder = wired(
        {
            "show-ref --verify --quiet refs/heads/local": (0, "", "", False),
            "show-ref --verify --quiet refs/remotes/origin/local": (0, "", "", False),
            "rev-list": (0, "0\t0\n", "", False),
        }
    )

    data = _payload(
        await GitRemoteBranchCompareCommand().execute(
            project_id="p", branch="local", fetch_first=False, max_commits=0
        )
    )

    assert data["fetched"] is False
    assert data["in_sync"] is True
    assert not any("fetch" in call for call in recorder.calls)


@pytest.mark.asyncio
async def test_compare_reports_which_side_is_missing(wired) -> None:
    """ "Something is missing" is not actionable; naming the side is."""
    wired({"show-ref --verify --quiet refs/heads/nope": (1, "", "", False)})

    error = _error(
        await GitRemoteBranchCompareCommand().execute(
            project_id="p", branch="nope", fetch_first=False
        )
    )

    assert error["code"] == GIT_REMOTE_BRANCH_NOT_FOUND
    assert error["details"]["missing"] == "local"


@pytest.mark.asyncio
async def test_compare_does_not_answer_from_an_unparsable_count(wired) -> None:
    """Garbled rev-list output must fail, not silently become zero."""
    wired(
        {
            "show-ref --verify --quiet refs/heads/local": (0, "", "", False),
            "show-ref --verify --quiet refs/remotes/origin/local": (0, "", "", False),
            "rev-list": (0, "not-a-count\n", "", False),
        }
    )

    error = _error(
        await GitRemoteBranchCompareCommand().execute(
            project_id="p", branch="local", fetch_first=False
        )
    )

    assert error["code"] == GIT_REMOTE_BRANCH_COMPARE_FAILED


@pytest.mark.asyncio
async def test_compare_rejects_a_negative_max_commits(wired) -> None:
    """A nonsense page size is a validation error, not a clamped guess."""
    wired({})

    error = _error(
        await GitRemoteBranchCompareCommand().execute(project_id="p", max_commits=-1)
    )

    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["field"] == "max_commits"


# --- shared parsing ---------------------------------------------------------


def test_ahead_behind_parsing_accepts_only_two_integers() -> None:
    """rev-list --left-right --count emits exactly two counts, left first."""
    assert parse_ahead_behind("3\t7\n") == (3, 7)
    assert parse_ahead_behind("0 0") == (0, 0)
    assert parse_ahead_behind("") is None
    assert parse_ahead_behind("3") is None
    assert parse_ahead_behind("a\tb") is None


def test_remote_branch_splitting_only_honours_a_real_remote_prefix() -> None:
    """A prefix is a remote only if a remote by that name exists."""
    remotes = {"origin", "upstream"}

    assert split_remote_branch("origin/feature/x", "origin", remotes) == (
        "origin",
        "feature/x",
    )
    assert split_remote_branch("upstream/main", "origin", remotes) == (
        "upstream",
        "main",
    )
    assert split_remote_branch("bare", "origin", remotes) == ("origin", "bare")
    # 'feature' is not a remote here, so this is one branch name.
    assert split_remote_branch("feature/x", "origin", remotes) == (
        "origin",
        "feature/x",
    )
    # With no remotes known at all, nothing may be claimed as a remote.
    assert split_remote_branch("origin/main", "origin", set()) == (
        "origin",
        "origin/main",
    )


# --- registration and contract ---------------------------------------------


def test_every_command_declares_the_schema_the_registry_expects() -> None:
    """A command whose schema drifts from its signature fails only in production."""
    for command in _ALL_COMMANDS:
        schema = command.get_schema()
        assert schema["additionalProperties"] is False
        assert "project_id" in schema["properties"]
        assert "project_id" in schema["required"]
        assert command.get_name() == command.name
        assert command.metadata()["name"] == command.name


def test_the_group_is_complete() -> None:
    """TODO 487773a8 asked for six; all six must be registrable by name."""
    assert {command.name for command in _ALL_COMMANDS} == {
        "git_remote_branch_list",
        "git_remote_branch_create",
        "git_remote_branch_delete",
        "git_remote_branch_track",
        "git_remote_branch_compare",
        "git_remote_branch_prune",
    }


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
