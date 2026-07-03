"""Guarded git reset operation for the project-scoped git block (T-002 hard-reset-guard).

Implements C-011 HardResetGuard for the discarding (hard) reset mode: a hard
reset requires an explicit mode selection of "hard" together with an explicit
confirm=True. Without confirmation, the operation performs a dry-run only: it
reports what would be lost (uncommitted changes via `git status --porcelain`
and commits that would be dropped via `git rev-list <target>..HEAD`) and moves
nothing. The preserving modes ("soft", "mixed") are never guarded. This module
never contacts a remote and treats `target` as an opaque ref (not path-confined).
"""

from __future__ import annotations

from code_analysis.core.git_ops.common import run_git

MODE_SOFT = "soft"
MODE_MIXED = "mixed"
MODE_HARD = "hard"
VALID_MODES = (MODE_SOFT, MODE_MIXED, MODE_HARD)


def _build_would_lose_report(root_dir: str, target: str) -> dict:
    """Build a report of what a hard reset to `target` would discard.

    Runs two read-only git inspections against the repository at `root_dir`:
    - `git status --porcelain` to list uncommitted working-tree/staged changes.
    - `git rev-list <target>..HEAD` to list commits on HEAD that are not
      reachable from `target` (i.e. commits that would be dropped by moving
      the current branch to `target`).

    :param root_dir: str - absolute path to the project's resolved repository root.
    :param target: str - opaque ref or revision the reset would move the current
        branch to. Not validated or path-confined; passed to git as-is.
    :return: dict - {"uncommitted_changes": list[str], "commits_to_drop": list[str]}.
        "uncommitted_changes" is the list of non-empty lines from the stdout of
        `git status --porcelain` (each line exactly as returned by git, with
        surrounding whitespace preserved, empty lines dropped).
        "commits_to_drop" is the list of non-empty lines from the stdout of
        `git rev-list <target>..HEAD` (each line is one commit hash, empty
        lines dropped).
        If a git command fails (non-zero return code), the corresponding list
        is an empty list.
    """
    would_lose: dict = {"uncommitted_changes": [], "commits_to_drop": []}

    status_code, status_out, _status_err = run_git(root_dir, ["status", "--porcelain"])
    if status_code == 0:
        would_lose["uncommitted_changes"] = [
            line for line in status_out.splitlines() if line.strip()
        ]

    revlist_code, revlist_out, _revlist_err = run_git(
        root_dir, ["rev-list", f"{target}..HEAD"]
    )
    if revlist_code == 0:
        would_lose["commits_to_drop"] = [
            line for line in revlist_out.splitlines() if line.strip()
        ]

    return would_lose
