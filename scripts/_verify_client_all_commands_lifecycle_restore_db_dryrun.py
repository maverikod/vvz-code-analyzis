"""
Live pipeline check: restore_database dry_run watch_dirs-table fallback (bug b9b36e13).

``restore_database`` used to return ``NO_DIRS`` whenever the active server
config had no ``code_analysis.dirs`` / ``code_analysis.worker.watch_dirs``
entries, even though the server may already have watch directories
registered that could rebuild the restore plan. The fix adds a fallback
sourced from the ``watch_dirs`` table
(``extract_restore_dirs_from_watch_dirs_table`` / ``list_watch_dir_path_pairs``),
applied before the ``dry_run`` gate.

This check calls ``restore_database`` with ``dry_run=true`` only (a real,
non-dry-run restore is destructive -- see
``_verify_client_all_commands_catalog.BUCKET_B_REASONS['restore_database']`` --
and stays out of scope for every other command in this verifier; this is a
narrow, additive, read-only exception carved out specifically to cover the
b9b36e13 regression without ever touching a real rebuild). Asserts the call
succeeds, ``plan.dirs`` is non-empty, and every entry is a subset of the live
``list_watch_dirs`` absolute paths -- proving the fallback sourced real,
currently-registered watch directories rather than fabricating paths.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext

CHECK_NAME = "restore_database_dry_run_watch_dirs_fallback"


def _outcome(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as the single-entry map every lifecycle returns.

    Args:
        status: Outcome status for this check.
        reason: Human-readable explanation.

    Returns:
        ``{CHECK_NAME: CommandOutcome(...)}``.
    """
    return {CHECK_NAME: CommandOutcome(CHECK_NAME, Bucket.BUCKET_A, status, reason)}


def _unwrap(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap a successful ``{"success": True, "data": {...}}`` envelope.

    Args:
        resp: Raw JSON-RPC command response.

    Returns:
        The ``data`` payload.

    Raises:
        RuntimeError: If ``resp`` does not report success.
    """
    if resp.get("success") is not True:
        raise RuntimeError(resp.get("error") or resp)
    data = resp.get("data")
    return data if isinstance(data, dict) else resp


async def run_restore_database_dry_run_watch_dirs_fallback_check(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Assert ``restore_database(dry_run=true)`` plans from live watch dirs.

    Args:
        client: Connected async client.
        fixtures: The sweep-wide fixture context (unused directly here --
            this check is server-wide, not project-scoped -- kept only to
            match the lifecycle-check signature every module exposes).

    Returns:
        ``{CHECK_NAME: outcome}``, merged into the lifecycle-precomputed
        outcomes table like every other lifecycle module returns.
    """
    del fixtures  # server-wide check, no disposable-project fixture needed
    try:
        watch_dirs_data = _unwrap(
            await client.call_validated("list_watch_dirs", {})
        )
        live_paths = {
            str(w.get("absolute_path"))
            for w in (watch_dirs_data.get("watch_dirs") or [])
            if isinstance(w, dict) and w.get("absolute_path")
        }
        if not live_paths:
            return _outcome(
                Status.EXPECTED_ERROR,
                "skipped: no live watch directories registered to plan against",
            )

        restore_resp = await client.call_validated(
            "restore_database", {"dry_run": True}, auto_poll=False
        )
    except Exception as exc:  # noqa: BLE001 - a broken check must not abort the sweep
        return _outcome(Status.FAILED, truncate(repr(exc)))

    if not restore_resp.get("success"):
        return _outcome(
            Status.FAILED,
            truncate(f"restore_database(dry_run=true) failed: {restore_resp.get('error')!r}"),
        )

    data = restore_resp.get("data") or {}
    plan = data.get("plan") or {}
    dirs = plan.get("dirs") or []
    if not dirs:
        return _outcome(
            Status.FAILED,
            truncate(
                "restore_database(dry_run=true) returned empty plan.dirs even "
                f"though live watch dirs exist: {sorted(live_paths)!r}"
            ),
        )

    not_live = [d for d in dirs if d not in live_paths]
    if not_live:
        return _outcome(
            Status.FAILED,
            truncate(
                f"plan.dirs contains entries outside the live watch_dirs set: "
                f"{not_live!r} (live={sorted(live_paths)!r})"
            ),
        )

    return _outcome(
        Status.EXECUTED_OK,
        f"restore_database(dry_run=true) plan.dirs={dirs!r} "
        f"(dirs_source={plan.get('dirs_source')!r}) is a non-empty subset of "
        f"the live watch_dirs set ({sorted(live_paths)!r})",
    )
