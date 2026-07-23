"""
Dedicated ``list_project_files`` subtree-scoped glob/dir-prefix perf check (bug 25c8d9dd).

Before the fix, ``list_project_files`` walked the WHOLE project tree for
every ``file_pattern``/``glob`` shape that was not the single-file literal
fast path (bug 04cb1578) -- a dir-prefix pattern or any pattern containing
fnmatch metacharacters always paid an O(project size) walk even when the
pattern's own static prefix could bound it to a small subtree. The
disposable per-run fixture project (a handful of files) cannot discriminate
this regression: an O(N) walk over a handful of files is not measurably
slower than a bounded one. This check instead targets the BIG real project
already registered on the deployment -- the code_analysis project's own
server-side mirror (``44a8ce88-b467-42a8-b874-033562b89bd0``, ~2900 files,
the same project bug 04cb1578's fast-path check references) -- since only a
project of that size can actually distinguish "walked a ~20-file subtree" from
"walked the whole tree" in wall-clock terms.

Exercises BOTH pattern shapes the subtree-scoping fix covers:
1. a literal directory-prefix pattern (no fnmatch metacharacters);
2. a nested subdirectory glob (fnmatch metacharacters, static prefix several
   segments deep).

Correctness is checked against a name-filtered CONTROL built independently
of the scoping optimization: one broad, patternless, ``python_only`` listing
of the whole project (paginated through in full), filtered locally with
plain ``str.startswith`` / :func:`fnmatch.fnmatch` -- the exact matching
semantics ``list_project_files`` itself documents for directory-prefix and
glob patterns respectively. The SUT (scoped) call's own returned item set
must equal the control's.

Reported under its own synthetic outcome name, ``list_project_files_glob_fast``
-- mirrors the conventions of
``_verify_client_all_commands_lifecycle_list_files_fast.py``: purely
additive, one more precomputed outcome merged into the same table every
other lifecycle module contributes to. Does not replace the generic
``list_project_files`` classification the main alphabetical sweep performs
elsewhere (that generic call has no reason to target this specific project
and pattern shape).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fnmatch
import time
from typing import Any, Dict, List, Set

from code_analysis_client import CodeAnalysisAsyncClient, QueuedJob

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext

CHECK_NAME = "list_project_files_glob_fast"

# The code_analysis project's own server-side mirror -- the same
# ~2900-file, always-registered project the sibling
# list_project_files_exact_path_fast check's docstring references (bug
# 04cb1578). A small disposable fixture project cannot discriminate an O(N)
# full-tree walk from a bounded subtree walk in wall-clock terms; this
# project's size can.
_BIG_PROJECT_ID = "44a8ce88-b467-42a8-b874-033562b89bd0"

# Generous relative to a subtree-bounded walk's actual sub-second cost on a
# directory this small, but tight enough to catch a regression back to the
# O(whole-project) full walk.
_MAX_WALL_SECONDS = 15.0

# Known-stable subtree of code_analysis's own source layout (present at any
# commit that still ships this file), used as both the dir-prefix and the
# nested-glob target so a stale server-side mirror commit cannot desync the
# fixture from reality.
_DIR_PREFIX_PATTERN = "code_analysis/commands/ast"
_NESTED_GLOB_PATTERN = "code_analysis/core/database_driver_pkg/domain/*.py"

_CONTROL_PAGE_SIZE = 200
_CONTROL_MAX_PAGES = 50


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns.

    Args:
        status: Outcome status for this check.
        reason: Human-readable explanation.

    Returns:
        ``{CHECK_NAME: CommandOutcome(...)}``.
    """
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


def _relative_paths_of(data: Dict[str, Any]) -> List[str]:
    """Extract the ``relative_path`` list from a ``list_project_files`` payload."""
    items = data.get("files") or data.get("items") or []
    return [str(entry.get("relative_path")) for entry in items if isinstance(entry, dict)]


async def _fetch_all_python_relative_paths(
    client: CodeAnalysisAsyncClient, project_id: str
) -> List[str]:
    """Paginate through the WHOLE project's ``.py`` listing (no pattern -- unscoped).

    Independent of the subtree-scoping optimization under test (a
    patternless request never derives a static prefix), so this is a valid
    correctness oracle for the SUT's own filtered item set.

    Args:
        client: Connected async client.
        project_id: Target project UUID.

    Returns:
        Every ``relative_path`` in the project (``python_only=true``).

    Raises:
        RuntimeError: On a queued-job handoff, a non-success response, or
            exceeding the page-count safety cap -- the caller catches this
            and reports a clean FAILED outcome.
    """
    all_paths: List[str] = []
    block_position = 1
    for _ in range(_CONTROL_MAX_PAGES):
        resp = await client.call_validated(
            "list_project_files",
            {
                "project_id": project_id,
                "python_only": True,
                "page_size": _CONTROL_PAGE_SIZE,
                "block_position": block_position,
            },
            auto_poll=False,
        )
        if isinstance(resp, QueuedJob):
            raise RuntimeError(
                f"control listing queued instead of plain (job_id={resp.job_id!r})"
            )
        if not resp.get("success"):
            raise RuntimeError(f"control listing failed: {resp.get('error')!r}")
        data: Dict[str, Any] = resp.get("data") or {}
        all_paths.extend(_relative_paths_of(data))
        if not data.get("has_more"):
            return all_paths
        block_position += 1
    raise RuntimeError(
        f"control listing did not terminate within {_CONTROL_MAX_PAGES} pages"
    )


def _control_dir_prefix_matches(all_paths: List[str], prefix: str) -> Set[str]:
    """Locally filter ``all_paths`` by directory-prefix semantics (no fnmatch)."""
    return {
        rel
        for rel in all_paths
        if rel == prefix or rel.startswith(prefix + "/")
    }


def _control_glob_matches(all_paths: List[str], pattern: str) -> Set[str]:
    """Locally filter ``all_paths`` by :func:`fnmatch.fnmatch` (server's own glob rule)."""
    return {rel for rel in all_paths if fnmatch.fnmatch(rel, pattern)}


async def _run_one_pattern_check(
    client: CodeAnalysisAsyncClient,
    *,
    project_id: str,
    file_pattern: str,
    expected: Set[str],
    label: str,
) -> Dict[str, CommandOutcome]:
    """Run one bounded, non-queued ``list_project_files`` call and check its item set.

    Args:
        client: Connected async client.
        project_id: Target project UUID.
        file_pattern: Pattern under test (dir-prefix or glob shape).
        expected: Control-derived set of relative paths this call must
            return, in full (one large page -- avoids conflating pagination
            correctness with the scoping fix under test).
        label: Short human label for this pattern shape, used in the reason
            string only.

    Returns:
        ``{CHECK_NAME: outcome}`` -- :attr:`Status.FAILED` on timeout, a
        queued handoff, a call failure, or a mismatched item set;
        :attr:`Status.EXECUTED_OK` otherwise (merged by the caller into one
        combined verdict across both pattern shapes).
    """
    started = time.monotonic()
    try:
        resp = await client.call_validated(
            "list_project_files",
            {
                "project_id": project_id,
                "file_pattern": file_pattern,
                "page_size": max(len(expected) + 5, 20),
            },
            auto_poll=False,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(Status.FAILED, truncate(f"{label}: call raised {exc!r}"))
    elapsed = time.monotonic() - started

    if isinstance(resp, QueuedJob):
        return _outcome(
            Status.FAILED,
            f"{label}: queued-job handoff instead of a plain result "
            f"(job_id={resp.job_id!r}, elapsed={elapsed:.1f}s) -- the subtree "
            "scoping fix did not engage",
        )
    if elapsed >= _MAX_WALL_SECONDS:
        return _outcome(
            Status.FAILED,
            f"{label}: took {elapsed:.1f}s (>= {_MAX_WALL_SECONDS}s budget) -- "
            "looks like an unscoped full-project walk",
        )
    if not resp.get("success"):
        return _outcome(
            Status.FAILED, truncate(f"{label}: call failed: {resp.get('error')!r}")
        )

    data: Dict[str, Any] = resp.get("data") or {}
    got = set(_relative_paths_of(data))
    if got != expected:
        missing = expected - got
        extra = got - expected
        return _outcome(
            Status.FAILED,
            truncate(
                f"{label}: item-set mismatch vs control -- missing={sorted(missing)!r} "
                f"extra={sorted(extra)!r}"
            ),
        )

    return _outcome(
        Status.EXECUTED_OK,
        f"{label}: {len(got)} item(s) in {elapsed:.2f}s, matches the name-filtered "
        "control exactly",
    )


async def run_list_project_files_glob_fast_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert subtree-scoped dir-prefix/glob listings are fast, unqueued, and correct.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run (NOT
            used as the target -- see module docstring for why this check
            needs the big real project instead).

    Returns:
        ``{CHECK_NAME: outcome}``, merged into the lifecycle-precomputed
        outcomes table like every other lifecycle module returns.
    """
    del fixtures  # deliberately unused -- this check targets a fixed real project

    try:
        all_paths = await _fetch_all_python_relative_paths(client, _BIG_PROJECT_ID)
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(
            Status.EXPECTED_ERROR,
            truncate(
                f"skipped: could not build the control listing for project "
                f"{_BIG_PROJECT_ID} (not registered on this deployment?): {exc!r}"
            ),
        )
    if not all_paths:
        return _outcome(
            Status.EXPECTED_ERROR,
            f"skipped: project {_BIG_PROJECT_ID} reported zero python files "
            "on this deployment",
        )

    dir_prefix_expected = _control_dir_prefix_matches(all_paths, _DIR_PREFIX_PATTERN)
    glob_expected = _control_glob_matches(all_paths, _NESTED_GLOB_PATTERN)
    if not dir_prefix_expected or not glob_expected:
        return _outcome(
            Status.EXPECTED_ERROR,
            truncate(
                f"skipped: fixture subtree(s) not present in project "
                f"{_BIG_PROJECT_ID}'s current listing (dir_prefix matches="
                f"{len(dir_prefix_expected)}, glob matches={len(glob_expected)}) -- "
                "server-side mirror commit is too far out of sync with this layout"
            ),
        )

    dir_prefix_result = await _run_one_pattern_check(
        client,
        project_id=_BIG_PROJECT_ID,
        file_pattern=_DIR_PREFIX_PATTERN,
        expected=dir_prefix_expected,
        label="dir-prefix",
    )
    glob_result = await _run_one_pattern_check(
        client,
        project_id=_BIG_PROJECT_ID,
        file_pattern=_NESTED_GLOB_PATTERN,
        expected=glob_expected,
        label="nested-glob",
    )

    dir_prefix_outcome = dir_prefix_result[CHECK_NAME]
    glob_outcome = glob_result[CHECK_NAME]
    if (
        dir_prefix_outcome.status is Status.EXECUTED_OK
        and glob_outcome.status is Status.EXECUTED_OK
    ):
        return _outcome(
            Status.EXECUTED_OK,
            f"dir-prefix: {dir_prefix_outcome.reason} | nested-glob: {glob_outcome.reason}",
        )
    worst_status = (
        Status.FAILED
        if Status.FAILED in (dir_prefix_outcome.status, glob_outcome.status)
        else Status.EXPECTED_ERROR
    )
    return _outcome(
        worst_status,
        f"dir-prefix: {dir_prefix_outcome.reason} | nested-glob: {glob_outcome.reason}",
    )
