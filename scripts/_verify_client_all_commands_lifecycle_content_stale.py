"""
Content-stale flag read-after-write lifecycle check (bug 56c23bd9).

Registered in ``_verify_client_all_commands_lifecycles.run_lifecycles``.

CHECK-SIDE FIX (bug N1 / 0d632d0e). The original version of this module was
an unsatisfiable false positive, live-reproduced against 192.168.254.26:15010
(1.6.80) before this rewrite, for two independent reasons plus one further
finding from re-verifying this rewrite's own first design:

Cause A (path mismatch, real bug, fixed here): ``_content_stale_for_path``
matched ``candidate == wanted`` against a project-RELATIVE ``wanted``, but
fulltext ``search`` rows always carry an ABSOLUTE ``file_path``
(``file_disk_registration.py`` resolves+stores ``str(path.resolve())``;
``core/database_driver_pkg/domain/search.py``'s SQL selects
``f.path AS file_path``) — a real hit could never match. The identical
helper in the sibling ``_verify_client_all_commands_lifecycle_fulltext_
seeded.py`` module has the same bug and is fixed the same way there (that
module's own deeper 0-hit finding is bug 67e50972, separate and NOT touched
by this fix).

Cause B (test design flaw): the original check used a ``.py`` fixture and
overwrote it through ``project_file_transfer_upload_save``. Every write to a
``.py`` file goes through ``PythonFileHandler`` -> a synchronous full
AST/CST reindex -> ``update_file_data_atomic_batch``
(``core/database_client/file_data_batch.py:392-408``), which
UNCONDITIONALLY clears ``content_stale=FALSE`` inside that very same write.
A ``.py`` write can therefore never observe ``content_stale=True``.

Cause C, as originally proposed for this rewrite (a TEXT_SUFFIXES ``.md``
fixture through ``persist_plain_text_file_metadata``,
``core/file_handlers/text_handler.py:307-310``): the "set" half checks out
live (that UPDATE branch really does set ``content_stale=TRUE`` without
reindexing). The "clear on the next ``update_indexes``" half does not:
``update_indexes``'s own file discovery
(``commands/code_mapper_mcp_command.py`` ->
``core/venv_path_policy.collect_python_files_for_indexing`` ->
``iter_project_python_files_excluding_venv``, filtering strictly on
``f.endswith(".py")``) never walks TEXT_SUFFIXES files, so a ``.md`` file's
``code_content`` row is never populated by any client-reachable command —
live-confirmed: even the BASELINE "findable, content_stale=False" step
returns 0 fulltext hits, including after a 90s wait with no intervening
write. This looks like a second, separate, pre-existing gap outside this
check's scope (worth its own bug report against ``update_indexes``/text-file
fulltext indexing) — it is NOT fixed here per this task's explicit
instruction not to touch server behavior just to make a check pass.

REWRITTEN DESIGN (this file): exercise the OTHER live, registered
``content_stale=TRUE`` setter — ``git_pull_safe``'s own per-file mark
(``commands/git_admin_commands.py::_mark_pull_changed_files_stale``, which
diffs ``pre_head..post_head`` of the pull and marks exactly the files that
changed). Satisfiable, deterministic, needs no server change, and is the
second of the two real ``content_stale=TRUE`` setters bug 56c23bd9 covers:

1. Seed a ``.py`` fixture with a BASELINE token, ``git_identity_set`` (a
   fresh disposable project has no configured git author), ``git_add`` +
   ``git_commit`` it on the project's default branch. The seed write already
   did a synchronous reindex, so the baseline token is fulltext-findable
   with ``content_stale=False`` here — asserted.
2. Via ``_verify_client_all_commands_lifecycle_content_stale_git.
   stage_stale_content_via_git_pull``: branch off, overwrite the same file
   with NEW-token content (normal write, synchronous reindex — DB
   ``code_content`` now holds the NEW content) and commit it there; switch
   back to the default branch (raw checkout, reverts on-disk bytes to
   BASELINE without touching the DB row); add a SELF remote (the project's
   own ``root_path``) and ``git_pull_safe`` from the throwaway branch. This
   fast-forwards the default branch (disk -> NEW content again) and, via the
   pull's own pre/post-HEAD diff, marks the file ``content_stale=TRUE`` —
   independently of DB ``code_content`` already holding that same NEW
   content.
3. Search the NEW token -> ASSERT found AND ``content_stale is True`` (the
   flag-visible assertion this check exists to prove).
4. ``update_indexes`` -> the file is ``.py``, so this time it IS walked and
   reindexed (the pull changed its mtime) -> ``content_stale`` clears.
5. Search the NEW token again -> ASSERT found AND ``content_stale is False``
   (reindex-success clear).

Live-verified GREEN against 192.168.254.26:15010 (1.6.80) before this file
was committed.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step_with_data
from _verify_client_all_commands_lifecycle_content_stale_git import (
    GIT_IDENTITY_EMAIL,
    GIT_IDENTITY_NAME,
    best_effort_remote_remove,
    require_step,
    stage_stale_content_via_git_pull,
)

CHECK_NAME = "search_content_stale_write_then_reindex_roundtrip"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


def _content_stale_for_path(
    items: List[Any], relative_path: str
) -> Optional[bool]:
    """Return the ``content_stale`` flag of the seeded path's hit, or None if absent.

    Tolerates both the ABSOLUTE ``file_path`` fulltext/semantic hits carry
    (``.../<project_root>/<relative_path>``) and a plain relative form other
    search sources may return, instead of requiring an exact match against a
    project-relative path (bug N1 / 0d632d0e, Cause A).
    """
    wanted = relative_path.replace("\\", "/").lstrip("./")
    wanted_suffix = "/" + wanted
    for row in items:
        if not isinstance(row, dict):
            continue
        candidate = str(
            row.get("file_path") or row.get("path") or row.get("relative_path") or ""
        ).replace("\\", "/")
        if candidate == wanted or candidate.endswith(wanted_suffix):
            return bool(row.get("content_stale"))
    return None


async def _search_for_token(
    client: CodeAnalysisAsyncClient, project_id: str, token: str
) -> Tuple[CommandOutcome, List[Any], str]:
    """Run one fresh fulltext-only ``search`` job for ``token``."""
    outcome, data = await call_step_with_data(
        client,
        "search",
        {
            "project_id": project_id,
            "query": token,
            "enable_semantic": False,
            "enable_grep": False,
        },
        ok_reason="content_stale roundtrip search completed",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return outcome, [], ""
    payload = data or {}
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    return outcome, items, str(payload.get("job_id") or "")


async def _best_effort_close(client: CodeAnalysisAsyncClient, job_id: str) -> None:
    """Close a search job without letting cleanup failures affect the verdict."""
    if not job_id:
        return
    try:
        await client.call_validated("search_close", {"job_id": job_id})
    except Exception:  # noqa: BLE001 - cleanup only
        pass


async def _seed_baseline(
    client: CodeAnalysisAsyncClient,
    fixtures: FixtureContext,
    relative_path: str,
    baseline_content: str,
) -> Tuple[Optional[str], Optional[Dict[str, CommandOutcome]]]:
    """Upload the baseline file and give it a real git commit on the default branch.

    Returns:
        ``(file_id, None)`` on success, or ``(None, outcome_map)`` on the
        first failure.
    """
    try:
        file_id = await client.file_sessions.upload_new(
            fixtures.session_id,
            baseline_content.encode("utf-8"),
            fixtures.project_id,
            relative_path,
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return None, _outcome(Status.FAILED, truncate(f"seed upload failed: {exc!r}"))
    if not file_id:
        return None, _outcome(Status.FAILED, "seed upload returned no file_id")

    for name, params, ok_reason in (
        (
            "git_identity_set",
            {
                "project_id": fixtures.project_id,
                "name": GIT_IDENTITY_NAME,
                "email": GIT_IDENTITY_EMAIL,
            },
            "git identity configured for the disposable project",
        ),
        (
            "git_add",
            {"project_id": fixtures.project_id, "all": True},
            "baseline file staged",
        ),
        (
            "git_commit",
            {
                "project_id": fixtures.project_id,
                "message": "content_stale check: baseline",
            },
            "baseline commit created",
        ),
    ):
        ok, _data, reason = await require_step(
            client, name, params, ok_reason, fail_prefix="setup"
        )
        if not ok:
            return None, _outcome(Status.FAILED, reason or f"{name} failed")

    return file_id, None


async def run_content_stale_roundtrip_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Seed a ``.py`` file, mark it stale via a real ``git_pull_safe``, confirm the roundtrip.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        ``{CHECK_NAME: outcome}`` — :attr:`Status.EXECUTED_OK` only when the
        post-pull search shows ``content_stale: true`` for the touched file
        AND the post-reindex search shows ``content_stale: false`` again.
    """
    if not fixtures.session_id:
        return _outcome(
            Status.EXPECTED_ERROR, "skipped: no fixture session_id available"
        )

    project_id = fixtures.project_id
    baseline_token = f"verifystalebase{uuid.uuid4().hex}"
    new_token = f"verifystalenew{uuid.uuid4().hex}"
    relative_path = f"verify_content_stale_{uuid.uuid4().hex[:8]}.py"
    baseline_content = (
        f'"""Seeded fixture for the content_stale roundtrip check.\n\n'
        f"Baseline token: {baseline_token}\n"
        f'"""\n'
    )
    new_content = (
        f'"""Seeded fixture for the content_stale roundtrip check.\n\n'
        f"Rewritten with live token: {new_token}\n"
        f'"""\n'
    )

    file_id, seed_err = await _seed_baseline(
        client, fixtures, relative_path, baseline_content
    )
    if seed_err is not None:
        return seed_err
    assert file_id is not None  # narrows for mypy; seed_err is None here

    baseline_outcome, baseline_items, baseline_job_id = await _search_for_token(
        client, project_id, baseline_token
    )
    if baseline_outcome.status is not Status.EXECUTED_OK:
        await _best_effort_close(client, baseline_job_id)
        return _outcome(
            baseline_outcome.status,
            f"baseline search call itself failed: {baseline_outcome.reason}",
        )
    baseline_flag = _content_stale_for_path(baseline_items, relative_path)
    await _best_effort_close(client, baseline_job_id)
    if baseline_flag is None:
        return _outcome(
            Status.FAILED,
            f"baseline search found no hit for {relative_path} with token "
            f"{baseline_token} among {len(baseline_items)} result(s) - cannot "
            "assert the pre-pull baseline",
        )
    if baseline_flag is not False:
        return _outcome(
            Status.FAILED,
            f"baseline search hit for {relative_path} has content_stale="
            f"{baseline_flag!r}, expected False right after the seed write",
        )

    status_outcome, status_data = await call_step_with_data(
        client,
        "git_status",
        {"project_id": project_id},
        ok_reason="default branch discovered",
    )
    default_branch = (status_data or {}).get("branch")
    if status_outcome.status is not Status.EXECUTED_OK or not default_branch:
        return _outcome(
            status_outcome.status,
            f"could not determine the default branch via git_status ({status_outcome.reason})",
        )

    try:
        stage_err = await stage_stale_content_via_git_pull(
            client,
            project_id=project_id,
            project_root=str(fixtures.project_root),
            session_id=fixtures.session_id,
            file_id=file_id,
            relative_path=relative_path,
            default_branch=default_branch,
            new_content=new_content.encode("utf-8"),
        )
        if stage_err is not None:
            return _outcome(Status.FAILED, stage_err)

        stale_outcome, stale_items, stale_job_id = await _search_for_token(
            client, project_id, new_token
        )
        if stale_outcome.status is not Status.EXECUTED_OK:
            await _best_effort_close(client, stale_job_id)
            return _outcome(
                stale_outcome.status,
                f"post-pull search call itself failed: {stale_outcome.reason}",
            )
        stale_flag = _content_stale_for_path(stale_items, relative_path)
        await _best_effort_close(client, stale_job_id)
        if stale_flag is None:
            return _outcome(
                Status.FAILED,
                f"post-pull search found no hit for {relative_path} with token "
                f"{new_token} among {len(stale_items)} result(s) - cannot assert "
                "the flag",
            )
        if stale_flag is not True:
            return _outcome(
                Status.FAILED,
                f"post-pull search hit for {relative_path} has content_stale="
                f"{stale_flag!r}, expected True (git_pull_safe's per-file mark "
                "did not fire)",
            )

        reindex_outcome, _reindex_data = await call_step_with_data(
            client,
            "update_indexes",
            {"project_id": project_id},
            ok_reason="update_indexes completed after the content_stale-triggering pull",
        )
        if reindex_outcome.status is not Status.EXECUTED_OK:
            return _outcome(
                reindex_outcome.status,
                f"post-pull update_indexes did not succeed ({reindex_outcome.reason}) "
                "- content_stale left set, roundtrip incomplete",
            )

        clear_outcome, clear_items, clear_job_id = await _search_for_token(
            client, project_id, new_token
        )
        if clear_outcome.status is not Status.EXECUTED_OK:
            await _best_effort_close(client, clear_job_id)
            return _outcome(
                clear_outcome.status,
                f"post-reindex search call itself failed: {clear_outcome.reason}",
            )
        clear_flag = _content_stale_for_path(clear_items, relative_path)
        await _best_effort_close(client, clear_job_id)
        if clear_flag is None:
            return _outcome(
                Status.FAILED,
                f"post-reindex search found no hit for {relative_path} among "
                f"{len(clear_items)} result(s) - cannot assert the flag cleared",
            )
        if clear_flag is not False:
            return _outcome(
                Status.FAILED,
                f"post-reindex search hit for {relative_path} still has "
                f"content_stale={clear_flag!r}, expected False (reindex-success "
                "clear did not fire)",
            )

        return _outcome(
            Status.EXECUTED_OK,
            f"{relative_path}: content_stale=true immediately after "
            "git_pull_safe's per-file mark, content_stale=false after "
            "update_indexes - full roundtrip confirmed",
        )
    finally:
        await best_effort_remote_remove(client, project_id)
