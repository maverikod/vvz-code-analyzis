"""
Global search (project_id=None) lifecycle check (cross-search removal;
USER: search(project_id=None) = all projects).

Registered in ``realsrv_test.core.sweep.run_lifecycles``.

Flow: resolve a live ``watch_dir_id`` via ``list_watch_dirs`` (required by
``create_project`` — verified live: ``create_project`` schema is
``{watch_dir_id, project_name, description}`` all required,
``additionalProperties: false``; the old seeder's ``{"name": ...}`` shape was
never valid), seed two disposable throwaway projects each with one file
containing a distinct globally-unique token, index both, then run
search(project_id=None, query=<shared marker>) and confirm hits from BOTH
projects come back with project attribution (project_id/project_name on each
result). Also confirms enable_grep=true + project_id=None fails loud with a
validation error instead of silently scanning zero/one project.

Every seed sub-step's failure reason is threaded back to the caller verbatim
(never swallowed to an opaque "seed step failed") — including a second latent
schema mismatch found while fixing this check: ``session_create`` only
accepts ``comment`` (+ optional ``role_ids``), also ``additionalProperties:
false`` live; it does not take ``project_id``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.lifecycle_common import call_step_with_data

CHECK_NAME = "search_global_project_id_none_finds_all_projects"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns."""
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


def _project_ids_in_hits(items: List[Any]) -> set:
    """Return the set of project_id attribution values seen across hits."""
    seen = set()
    for row in items:
        if isinstance(row, dict) and row.get("project_id"):
            seen.add(str(row["project_id"]))
    return seen


async def _resolve_watch_dir_id(
    client: CodeAnalysisAsyncClient,
) -> Tuple[Optional[str], str]:
    """Resolve a live ``watch_dir_id`` for ``create_project`` via ``list_watch_dirs``.

    Returns ``(watch_dir_id, reason)`` — ``watch_dir_id`` is ``None`` on any
    failure, in which case ``reason`` carries the verbatim failing detail.
    """
    outcome, data = await call_step_with_data(
        client,
        "list_watch_dirs",
        {},
        ok_reason="list_watch_dirs completed",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return None, f"list_watch_dirs: {outcome.reason}"
    watch_dirs = (data or {}).get("watch_dirs")
    if not isinstance(watch_dirs, list) or not watch_dirs:
        return None, f"list_watch_dirs returned no watch directories: {data!r}"
    first = watch_dirs[0]
    watch_dir_id = str(first.get("id") or "") if isinstance(first, dict) else ""
    if not watch_dir_id:
        return None, f"list_watch_dirs first row missing id: {first!r}"
    return watch_dir_id, ""


async def _seed_throwaway_project(
    client: CodeAnalysisAsyncClient, *, watch_dir_id: str, token: str, label: str
) -> Tuple[Optional[str], Optional[str], str]:
    """Create a disposable project with one file containing ``token``.

    Returns ``(project_id, session_id, reason)`` — ``project_id`` is ``None``
    on any failure (a broken seed step must not raise), in which case
    ``reason`` carries the verbatim failing step's outcome/exception so the
    caller never reports an opaque "seed step failed".
    """
    outcome, data = await call_step_with_data(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": f"verify-global-search-{label}-{uuid.uuid4().hex[:8]}",
            "description": (
                f"Disposable fixture for global-search attribution check ({label})"
            ),
            "create_venv": False,
            "apply_template": False,
        },
        ok_reason=f"throwaway project created for {label}",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return None, None, f"create_project: {outcome.reason}"
    project_id = str((data or {}).get("project_id") or "")
    if not project_id:
        return None, None, f"create_project succeeded but returned no project_id: {data!r}"

    session_outcome, session_data = await call_step_with_data(
        client,
        "session_create",
        {"comment": f"verify-global-search-{label}"},
        ok_reason=f"session opened for {label}",
    )
    if session_outcome.status is not Status.EXECUTED_OK:
        return None, None, f"session_create: {session_outcome.reason}"
    session_id = str((session_data or {}).get("session_id") or "")
    if not session_id:
        return (
            None,
            None,
            f"session_create succeeded but returned no session_id: {session_data!r}",
        )

    content = (
        f'"""Seeded fixture for the global-search attribution check ({label}).\n\n'
        f"Shared marker token: {token}\n"
        f'"""\n'
    )
    try:
        file_id = await client.file_sessions.upload_new(
            session_id,
            content.encode("utf-8"),
            project_id,
            f"verify_global_{label}.py",
        )
    except Exception as exc:  # noqa: BLE001 - a broken seed step must not abort the sweep
        return None, None, f"file_sessions.upload_new: {exc!r}"
    if not file_id:
        return None, None, "file_sessions.upload_new returned no file_id"

    index_outcome, _data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": project_id},
        ok_reason=f"update_indexes completed for {label}",
    )
    if index_outcome.status is not Status.EXECUTED_OK:
        return None, None, f"update_indexes: {index_outcome.reason}"
    return project_id, session_id, ""


async def run_global_search_attribution_check(
    client: CodeAnalysisAsyncClient, fixtures: Any
) -> Dict[str, CommandOutcome]:
    """Seed 2 throwaway projects, confirm search(project_id=None) finds both.

    Args:
        client: Connected async client.
        fixtures: Unused (this check seeds its own disposable projects rather
            than reusing the shared fixture project, since the whole point is
            searching ACROSS multiple projects).

    Returns:
        ``{CHECK_NAME: outcome}`` - :attr:`Status.EXECUTED_OK` only when both
        seeded projects' hits are present WITH project_id attribution, and the
        separate grep+None validation-error check also passes.
    """
    _ = fixtures
    token = f"verifyglobal{uuid.uuid4().hex}"

    watch_dir_id, watch_dir_reason = await _resolve_watch_dir_id(client)
    if watch_dir_id is None:
        return _outcome(
            Status.FAILED, f"could not resolve watch_dir_id: {watch_dir_reason}"
        )

    project_a, _session_a, reason_a = await _seed_throwaway_project(
        client, watch_dir_id=watch_dir_id, token=token, label="a"
    )
    if project_a is None:
        return _outcome(
            Status.FAILED, f"seed step failed for throwaway project A: {reason_a}"
        )

    project_b, _session_b, reason_b = await _seed_throwaway_project(
        client, watch_dir_id=watch_dir_id, token=token, label="b"
    )
    if project_b is None:
        return _outcome(
            Status.FAILED, f"seed step failed for throwaway project B: {reason_b}"
        )

    search_outcome, data = await call_step_with_data(
        client,
        "search",
        {
            "query": token,
            "enable_semantic": False,
            "enable_grep": False,
        },
        ok_reason="global search (project_id omitted) completed",
    )
    if search_outcome.status is not Status.EXECUTED_OK:
        return _outcome(
            search_outcome.status,
            f"global search call itself failed: {search_outcome.reason}",
        )
    payload = data or {}
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    job_id = str(payload.get("job_id") or "")
    try:
        found_project_ids = _project_ids_in_hits(items)
        missing = {project_a, project_b} - found_project_ids
        if missing:
            return _outcome(
                Status.FAILED,
                f"global search for shared token {token} found "
                f"{len(items)} hit(s) but missing project attribution for "
                f"{len(missing)} of the 2 seeded throwaway projects "
                f"(found project_ids: {sorted(found_project_ids)})",
            )
    finally:
        if job_id:
            try:
                await client.call_validated("search_close", {"job_id": job_id})
            except Exception:  # noqa: BLE001 - cleanup only
                pass

    grep_outcome, _grep_data = await call_step_with_data(
        client,
        "search",
        {"query": token, "enable_grep": True},
        ok_reason="global search + enable_grep=true call completed",
    )
    if grep_outcome.status is not Status.EXPECTED_ERROR and grep_outcome.status is not Status.FAILED:
        return _outcome(
            Status.FAILED,
            "search(project_id=None, enable_grep=true) unexpectedly succeeded "
            "(expected a fail-loud validation error: 'grep requires project_id')",
        )
    if "grep requires project_id" not in truncate(grep_outcome.reason, 500):
        return _outcome(
            Status.FAILED,
            "search(project_id=None, enable_grep=true) failed, but not with the "
            f"expected 'grep requires project_id' message: {grep_outcome.reason}",
        )

    return _outcome(
        Status.EXECUTED_OK,
        f"global search for shared token {token} found both seeded projects "
        f"({project_a}, {project_b}) with attribution among {len(items)} hit(s); "
        "enable_grep=true + project_id=None correctly fails loud",
    )
