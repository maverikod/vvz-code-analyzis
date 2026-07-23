"""
Global search (project_id=None) lifecycle check (cross-search removal;
USER: search(project_id=None) = all projects).

UNREGISTERED groundwork module (intentionally not wired into
_verify_client_all_commands_lifecycles.run_lifecycles - see
_verify_client_all_commands_lifecycle_content_stale.py's own "unregistered
groundwork" precedent; owner: the search/db-collapse implementer who owns the
registry).

Flow: seed two disposable throwaway projects, each with one file containing a
distinct globally-unique token, index both, then run
search(project_id=None, query=<shared marker>) and confirm hits from BOTH
projects come back with project attribution (project_id/project_name on each
result). Also confirms enable_grep=true + project_id=None fails loud with a
validation error instead of silently scanning zero/one project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_lifecycle_common import call_step_with_data

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


async def _seed_throwaway_project(
    client: CodeAnalysisAsyncClient, *, token: str, label: str
) -> Optional[Tuple[str, str]]:
    """Create a disposable project with one file containing ``token``.

    Returns (project_id, session_id) or None on any failure (caller marks the
    whole check FAILED with the reason - a broken seed step must not raise).
    """
    outcome, data = await call_step_with_data(
        client,
        "create_project",
        {"name": f"verify-global-search-{label}-{uuid.uuid4().hex[:8]}"},
        ok_reason=f"throwaway project created for {label}",
    )
    if outcome.status is not Status.EXECUTED_OK:
        return None
    project_id = str((data or {}).get("project_id") or "")
    if not project_id:
        return None

    session_outcome, session_data = await call_step_with_data(
        client,
        "session_create",
        {"project_id": project_id},
        ok_reason=f"session opened for {label}",
    )
    if session_outcome.status is not Status.EXECUTED_OK:
        return None
    session_id = str((session_data or {}).get("session_id") or "")
    if not session_id:
        return None

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
    except Exception:  # noqa: BLE001 - a broken seed step must not abort the sweep
        return None
    if not file_id:
        return None

    index_outcome, _data = await call_step_with_data(
        client,
        "update_indexes",
        {"project_id": project_id},
        ok_reason=f"update_indexes completed for {label}",
    )
    if index_outcome.status is not Status.EXECUTED_OK:
        return None
    return project_id, session_id


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

    seeded_a = await _seed_throwaway_project(client, token=token, label="a")
    if seeded_a is None:
        return _outcome(Status.FAILED, "seed step failed for throwaway project A")
    project_a, _session_a = seeded_a

    seeded_b = await _seed_throwaway_project(client, token=token, label="b")
    if seeded_b is None:
        return _outcome(Status.FAILED, "seed step failed for throwaway project B")
    project_b, _session_b = seeded_b

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
